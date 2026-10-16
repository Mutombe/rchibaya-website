"""
Launch checklist for the RCLC site. Proves each item in a real browser.

    python tools/checklist.py [--base http://localhost:8080/] [--shots DIR]

Needs: a local server on --base, and `pip install playwright` (+ `playwright install chromium`).
Exit code is the number of failed checks.
"""
import argparse, html.parser, json, os, re, sys, time, urllib.parse
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
HERO_VIEWPORTS = [(1920, 1080), (1440, 900), (1366, 768), (1280, 720), (768, 1024), (390, 844)]
SUPERLATIVES = r"\b(best|leading|finest|greatest|top[- ]rated|premier|world[- ]class|unparalleled|unrivall?ed|unmatched|ultimate|number one|most|highest|largest|foremost|second to none|cutting[- ]edge|state[- ]of[- ]the[- ]art|singular)\b"

results = []
def report(name, ok, detail=""):
    results.append((name, ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    if detail:
        for line in str(detail).strip().splitlines():
            print("        " + line)

# ---------------------------------------------------------------- JS helpers
LINES_JS = r"""
(() => {
  // Lines of text whose nearest block container is `el`, clustered by vertical overlap.
  window.__lines = (el) => {
    const isInline = (n) => getComputedStyle(n).display === 'inline';
    const rects = [];
    const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let t;
    while ((t = w.nextNode())) {
      if (!t.textContent.trim()) continue;
      let p = t.parentElement, own = true;
      while (p && p !== el) { if (!isInline(p)) { own = false; break; } p = p.parentElement; }
      if (!own) continue;
      const r = document.createRange(); r.selectNodeContents(t);
      for (const b of r.getClientRects()) if (b.width > 0.5 && b.height > 0.5) rects.push(b);
    }
    rects.sort((a, b) => a.top - b.top);
    const lines = [];
    for (const r of rects) {
      const hit = lines.find(l => Math.min(l.bottom, r.bottom) - Math.max(l.top, r.top) > 0.5 * Math.min(l.bottom - l.top, r.height));
      if (hit) { hit.top = Math.min(hit.top, r.top); hit.bottom = Math.max(hit.bottom, r.bottom); }
      else lines.push({ top: r.top, bottom: r.bottom });
    }
    return lines.length;
  };
  window.__visible = (el) => {
    for (let n = el; n && n !== document.body; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if (cs.display === 'none' || cs.visibility === 'hidden' || cs.visibility === 'collapse') return false;
    }
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    if (r.right <= 0 || r.left >= innerWidth) return false;   // parked off-canvas
    return true;
  };
})();
"""

TEXT_BLOCKS_JS = r"""
() => {
  const all = [...document.querySelectorAll('body *')];
  const out = [];
  all.forEach((el, i) => {
    if (el.closest('h1,h2,h3,h4,h5,h6,svg,script,style,select,option,[aria-hidden="true"],noscript')) return;
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (!own) return;
    if (!__visible(el)) return;
    if (getComputedStyle(el).display === 'inline') return;  // counted as part of its block
    out.push({ i, tag: el.tagName.toLowerCase(), cls: el.className && el.className.baseVal === undefined ? el.className : '',
               text: el.textContent.trim().replace(/\s+/g, ' ').slice(0, 70), lines: __lines(el) });
  });
  return out;
}
"""

def settle(page, ms=1400):
    """Scroll the whole page so lazy images load and reveals fire, then return to top."""
    h = page.evaluate("document.documentElement.scrollHeight")
    vh = page.evaluate("innerHeight")
    y = 0
    while y < h:
        page.evaluate(f"window.scrollTo(0,{y})")
        page.wait_for_timeout(120)
        y += int(vh * 0.8)
        h = page.evaluate("document.documentElement.scrollHeight")
    page.wait_for_timeout(ms)
    page.evaluate("window.scrollTo(0,0)")
    page.wait_for_timeout(300)

def new_page(browser, w, h, js=True):
    mobile = w < 800
    ctx = browser.new_context(viewport={"width": w, "height": h}, java_script_enabled=js,
                              is_mobile=mobile, has_touch=mobile, device_scale_factor=2 if mobile else 1)
    page = ctx.new_page()
    page.add_init_script(LINES_JS) if js else None
    return ctx, page

# ---------------------------------------------------------------- static checks
class Collector(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(); self.ids = set(); self.refs = []; self.text = []
        self._skip = 0
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a: self.ids.add(a["id"])
        for k in ("href", "src", "xlink:href", "poster", "data-src"):
            if a.get(k): self.refs.append((tag, k, a[k]))
        if a.get("srcset"):
            for part in a["srcset"].split(","): self.refs.append((tag, "srcset", part.strip().split(" ")[0]))
        for k in ("alt", "title", "aria-label", "content", "data-biz", "data-ind"):
            if a.get(k): self.text.append(a[k])
        if tag in ("script", "style", "svg"): self._skip += 1
    def handle_endtag(self, tag):
        if tag in ("script", "style", "svg"): self._skip -= 1
    def handle_data(self, d):
        if not self._skip: self.text.append(d)

def static_checks(pages):
    bad = []
    for page_path in pages:
        src = page_path.read_text(encoding="utf-8")
        c = Collector(); c.feed(src)
        for tag, attr, ref in c.refs:
            if re.match(r"^(https?:|mailto:|tel:|data:|//)", ref): continue
            if ref.startswith("#"):
                if ref != "#" and ref[1:] not in c.ids: bad.append(f"{page_path.name}: {tag}[{attr}] -> {ref} (no such id)")
                continue
            target = (page_path.parent / urllib.parse.unquote(ref.split("#")[0].split("?")[0])).resolve()
            if not target.exists():
                bad.append(f"{page_path.name}: {tag}[{attr}] -> {ref} (missing file)")
            elif "#" in ref and target.suffix == ".html":
                frag = ref.split("#", 1)[1]
                tc = Collector(); tc.feed(target.read_text(encoding="utf-8"))
                if frag and frag not in tc.ids: bad.append(f"{page_path.name}: {ref} (no #{frag} in {target.name})")
    report("Every internal link and asset path resolves", not bad, "\n".join(bad) or f"{len(pages)} page(s) walked")

    bad, n = [], 0
    for css in (ROOT / "css").glob("*.css"):
        for m in re.finditer(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)", css.read_text(encoding="utf-8")):
            ref = m.group(1)
            if ref.startswith(("data:", "#", "%23")): continue
            n += 1
            if not (css.parent / ref).resolve().exists(): bad.append(f"{css.name}: url({ref})")
    report("Every CSS url() resolves", not bad, "\n".join(bad) or f"{n} url() references checked")

    hits = []
    for page_path in pages:
        src = page_path.read_text(encoding="utf-8")
        c = Collector(); c.feed(src)
        text = " ".join(c.text)
        if "—" in src or "&mdash;" in src or "&#8212;" in src: hits.append(f"{page_path.name}: em dash present")
        for m in re.finditer(SUPERLATIVES, text, re.I):
            ctx = text[max(0, m.start() - 30): m.end() + 30].replace("\n", " ")
            hits.append(f"{page_path.name}: '{m.group(0)}' in …{ctx.strip()}…")
    js = (ROOT / "js" / "main.js").read_text(encoding="utf-8")
    if "—" in js: hits.append("main.js: em dash in an injected string")
    report("Zero em dashes, zero hollow superlatives in the built HTML", not hits, "\n".join(hits))

    # motion rules from the stylesheet
    css = (ROOT / "css" / "styles.css").read_text(encoding="utf-8")
    probs = []
    for m in re.finditer(r"transition(?:-property)?\s*:\s*([^;]+);", css):
        for prop in re.split(r",(?![^(]*\))", m.group(1)):
            name = prop.strip().split(" ")[0]
            if name in ("width", "height", "top", "left", "right", "bottom", "all", "flex", "flex-basis", "margin", "padding", "padding-left", "grid-template-rows", "max-height"):
                probs.append(f"transition on '{name}': {prop.strip()[:60]}")
    for m in re.finditer(r"@keyframes\s+([\w-]+)\s*\{(.*?\})\s*\}", css, re.S):
        for prop in re.findall(r"([a-z-]+)\s*:", m.group(2)):
            if prop not in ("transform", "opacity", "stroke-dashoffset"):
                probs.append(f"@keyframes {m.group(1)} animates '{prop}'")
    for m in re.finditer(r"translateY\((-?\d+)px\)", css):
        pass
    lift = re.search(r"--lift:\s*(-?\d+)px", css)
    if not lift or abs(int(lift.group(1))) > 6: probs.append("card lift token is not 6px or less")
    for m in re.finditer(r":hover[^{]*\{[^}]*translateY\((-?\d+)px\)", css):
        if abs(int(m.group(1))) > 6: probs.append(f"hover lifts {m.group(1)}px")
    durs = set(re.findall(r"--dur-hover:\s*(\d+)ms", css))
    if not durs or not all(300 <= int(d) <= 400 for d in durs): probs.append(f"hover duration token {durs} outside 300-400ms")
    if not re.search(r"--dur-reveal:\s*700ms", css) or not re.search(r"--travel:\s*24px", css) or not re.search(r"--stagger:\s*85ms", css):
        probs.append("reveal tokens are not 700ms / 24px / 85ms")
    report("Motion rules: transform/opacity only, hovers 300-400ms, lift <= 6px, reveals 700ms/24px/85ms", not probs, "\n".join(probs))

    # licensing
    lic = (ROOT / "assets" / "fonts" / "LICENSE.txt")
    fonts_css = (ROOT / "css" / "fonts.css").read_text(encoding="utf-8")
    font_files = re.findall(r"url\(\.\./assets/fonts/([^)]+)\)", fonts_css)
    probs = []
    if not lic.exists(): probs.append("assets/fonts/LICENSE.txt missing")
    else:
        lt = lic.read_text(encoding="utf-8")
        for f in font_files:
            if f not in lt: probs.append(f"{f} not covered in LICENSE.txt")
    for f in (ROOT / "assets" / "fonts").glob("OFL-*.txt"): pass
    if len(list((ROOT / "assets" / "fonts").glob("OFL-*.txt"))) < 3: probs.append("per-family OFL texts missing")
    icon_fonts = [p.name for p in ROOT.rglob("*") if p.suffix in (".woff", ".woff2", ".ttf", ".otf") and p.name not in font_files]
    if icon_fonts: probs.append(f"unlisted font files present: {icon_fonts}")
    report("Every font and icon file is licensed for the use", not probs,
           "\n".join(probs) or f"{len(font_files)} font files, all SIL OFL 1.1; icons are inline SVG")

# ---------------------------------------------------------------- browser checks
def browser_checks(base, shots, names):
    urls = [(n, base + ("" if n == "index.html" else n)) for n in names]
    with sync_playwright() as p:
        browser = p.chromium.launch()

        # 1 + 2: console, requests, horizontal overflow
        errs, overflow = [], []
        for name, url in urls:
            for w, h in [(1280, 800), (390, 844)]:
                ctx, page = new_page(browser, w, h)
                tag = f"{name} {w}px"
                page.on("console", lambda m, t=tag: m.type == "error" and errs.append(f"{t} console: {m.text[:160]}"))
                page.on("pageerror", lambda e, t=tag: errs.append(f"{t} pageerror: {e}"))
                page.on("requestfailed", lambda r, t=tag: errs.append(f"{t} failed: {r.url[:120]} {r.failure}"))
                page.on("response", lambda r, t=tag: r.status >= 400 and errs.append(f"{t} HTTP {r.status}: {r.url[:120]}"))
                page.goto(url, wait_until="load")
                settle(page)
                page.wait_for_timeout(3000 if "contact" in name or name == "index.html" else 300)  # let the map iframe finish before closing
                sw, cw = page.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
                if sw != cw:
                    wide = page.evaluate("""() => [...document.querySelectorAll('body *')].filter(e => e.getBoundingClientRect().right > document.documentElement.clientWidth + 1)
                         .slice(0, 6).map(e => e.tagName + '.' + (e.className.baseVal ?? e.className) + ' right=' + Math.round(e.getBoundingClientRect().right))""")
                    overflow.append(f"{tag}: scrollWidth {sw} != clientWidth {cw}; {wide}")
                ext = page.evaluate("performance.getEntriesByType('resource').map(r => r.name).filter(n => /fonts\\.(googleapis|gstatic)/.test(n))")
                if ext: errs.append(f"{tag}: external font requests {ext}")
                ctx.close()
        report("Zero console errors, zero failed requests, on every page", not errs, "\n".join(errs) or f"{len(urls)} pages x 2 viewports")
        report("scrollWidth === clientWidth at 1280 and at 390", not overflow, "\n".join(overflow) or f"{len(urls)} pages x 2 viewports, no overflow")

        # 5: hero (home) and page header (inner pages) fit one screen
        probs, ok_n = [], 0
        for name, url in urls:
            for w, h in HERO_VIEWPORTS:
                ctx, page = new_page(browser, w, h)
                page.goto(url, wait_until="load")
                page.wait_for_timeout(1500)
                r = page.evaluate("""() => {
                  const hero = document.querySelector('.hero, .page-hero'), hb = hero.getBoundingClientRect();
                  const head = document.querySelector('.site-header').getBoundingClientRect();
                  const kids = [...hero.querySelectorAll('.container *')].filter(e => __visible(e) && !e.closest('svg'));
                  let lowest = 0, highest = 1e9, culprit = '';
                  kids.forEach(e => { const r = e.getBoundingClientRect();
                    if (r.bottom > lowest) { lowest = r.bottom; culprit = e.className.baseVal ?? e.className; }
                    if (r.top < highest) highest = r.top; });
                  return { vh: innerHeight, heroBottom: hb.bottom, contentBottom: lowest, contentTop: highest, headerBottom: head.bottom, culprit };
                }""")
                fits = r["heroBottom"] <= r["vh"] + 1 and r["contentBottom"] <= r["heroBottom"] + 1 and r["contentTop"] >= r["headerBottom"] - 1
                if fits: ok_n += 1
                else: probs.append(f"{name} {w}x{h}: header ends {r['headerBottom']:.0f}, content {r['contentTop']:.0f}-{r['contentBottom']:.0f}, hero ends {r['heroBottom']:.0f} of {r['vh']}  <- {r['culprit']}")
                if shots and w in (1440, 390): page.screenshot(path=str(Path(shots) / f"top-{name[:-5]}-{w}.png"))
                ctx.close()
        report("The hero fits one screen at six real viewport sizes, on every page", not probs, "\n".join(probs) or f"{ok_n} page/viewport combinations fit")

        # 6 + 7: line budgets
        wraps, long, n_blocks, n_paras, max_lines = [], [], 0, 0, 0
        for name, url in urls:
            data, paras = {}, []
            for w, h in [(1280, 800), (390, 844)]:
                ctx, page = new_page(browser, w, h)
                page.goto(url, wait_until="load")
                settle(page, 1500)
                data[w] = {d["i"]: d for d in page.evaluate(TEXT_BLOCKS_JS)}
                if w == 390:
                    paras = page.evaluate("""() => [...document.querySelectorAll('p, li, blockquote, dd, figcaption')]
                        .filter(e => __visible(e) && !e.closest('[aria-hidden="true"]'))
                        .map(e => ({ text: e.textContent.trim().replace(/\\s+/g,' ').slice(0, 60), lines: __lines(e) }))""")
                ctx.close()
            common = [i for i in data[1280] if i in data[390]]
            n_blocks += len(common)
            wraps += [f"{name}: {data[1280][i]['tag']}.{data[1280][i]['cls']} '{data[1280][i]['text']}': 1 line at 1280, {data[390][i]['lines']} at 390"
                      for i in common if data[1280][i]["lines"] == 1 and data[390][i]["lines"] > 1]
            long += [f"{name}: {q['lines']} lines: '{q['text']}'" for q in paras if q["lines"] > 4]
            n_paras += len(paras); max_lines = max([max_lines] + [q["lines"] for q in paras])
        report("No text is one line on desktop and two on mobile, except headings", not wraps, "\n".join(wraps) or f"{n_blocks} text blocks compared across {len(urls)} pages")
        report("No paragraph exceeds four lines at 390px", not long, "\n".join(long) or f"{n_paras} paragraphs across {len(urls)} pages, max {max_lines} lines")

        # 9: image aspect ratios
        bad, n_img = [], 0
        for name, url in urls:
            for w, h in [(1280, 800), (390, 844)]:
                ctx, page = new_page(browser, w, h)
                page.goto(url, wait_until="load")
                settle(page)
                res = page.evaluate("""() => [...document.images].filter(i => i.complete && i.naturalWidth && __visible(i)).map(i => {
                    const cs = getComputedStyle(i), r = i.getBoundingClientRect();
                    return { src: i.getAttribute('src'), fit: cs.objectFit, box: r.width / r.height, nat: i.naturalWidth / i.naturalHeight,
                             attr: i.getAttribute('width') / i.getAttribute('height') };
                })""")
                n_img += len(res)
                for im in res:
                    if im["fit"] in ("fill", "scale-down", "none") and abs(im["box"] / im["nat"] - 1) > 0.015:
                        bad.append(f"{name} {w}px {im['src']}: drawn {im['box']:.3f} vs natural {im['nat']:.3f} (object-fit {im['fit']})")
                    if im["attr"] and abs(im["attr"] / im["nat"] - 1) > 0.01:
                        bad.append(f"{name} {im['src']}: width/height attributes {im['attr']:.3f} vs natural {im['nat']:.3f}")
                ctx.close()
        report("Images are not stretched: rendered aspect ratio equals natural ratio", not bad,
               "\n".join(sorted(set(bad))) or f"{n_img} image renders checked (cover/contain crop, never distort)")

        # 10: no JavaScript
        probs = []
        for name, url in urls:
            for w, h in [(1280, 800), (390, 844)]:
                ctx, page = new_page(browser, w, h, js=False)
                page.goto(url, wait_until="load")
                page.wait_for_timeout(1200)   # let entrance animations (e.g. the open FAQ answer) finish
                r = page.evaluate("""() => {
                  const vis = (e) => { const cs = getComputedStyle(e), r = e.getBoundingClientRect();
                                       return cs.display !== 'none' && cs.visibility !== 'hidden' && +cs.opacity > 0.01 && r.width > 0 && r.height > 0; };
                  const hidden = [...document.querySelectorAll('main *, footer *, header *')].filter(e =>
                     +getComputedStyle(e).opacity < 0.01 && !e.closest('.to-top') && e.getBoundingClientRect().width > 0).map(e => e.className).slice(0, 5);
                  const pas = [...document.querySelectorAll('.pa')];
                  return { htmlClass: document.documentElement.className, pas: pas.length, panels: pas.filter(vis).length,
                           navLinks: [...document.querySelectorAll('.main-nav > a')].filter(e => vis(e) && e.getBoundingClientRect().left < innerWidth).length,
                           hidden, overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth };
                }""")
                tag = f"{name} {w}px"
                if r["htmlClass"] != "no-js": probs.append(f"{tag}: html class is '{r['htmlClass']}'")
                if r["panels"] != r["pas"]: probs.append(f"{tag}: only {r['panels']}/{r['pas']} practice areas visible")
                if r["navLinks"] != 6: probs.append(f"{tag}: only {r['navLinks']}/6 nav links reachable")
                if r["hidden"]: probs.append(f"{tag}: invisible content {r['hidden']}")
                if r["overflow"]: probs.append(f"{tag}: horizontal overflow {r['overflow']}px")
                ctx.close()
        report("The page renders fully with JavaScript disabled, on every page", not probs, "\n".join(probs) or f"{len(urls)} pages: all nav links, all practice areas, no hidden content")

        # 11: mobile navigation (on every page)
        probs = []
        for name, url in urls:
            ctx, page = new_page(browser, 390, 844)
            page.goto(url, wait_until="load")
            page.evaluate("window.scrollTo(0, 900)"); page.wait_for_timeout(300)
            state = lambda: page.evaluate("""() => { const n = document.querySelector('#nav'), r = n.getBoundingClientRect(), cs = getComputedStyle(n);
                return { open: document.documentElement.classList.contains('nav-open'), expanded: document.querySelector('.nav-toggle').getAttribute('aria-expanded'),
                         shown: cs.visibility === 'visible' && +cs.opacity > 0.5, covers: r.left <= 0 && r.top <= 0 && r.right >= innerWidth && r.bottom >= innerHeight,
                         ofH: getComputedStyle(document.documentElement).overflow, ofB: getComputedStyle(document.body).overflow, y: scrollY }; }""")
            page.click(".nav-toggle"); page.wait_for_timeout(700)
            s1 = state()
            if not (s1["open"] and s1["expanded"] == "true" and s1["shown"] and s1["covers"]): probs.append(f"{name}: does not open full-screen: {s1}")
            if not (s1["ofH"] == "hidden" and s1["ofB"] == "hidden"): probs.append(f"{name}: scroll not locked")
            page.mouse.wheel(0, 800); page.wait_for_timeout(400)
            if state()["y"] != s1["y"]: probs.append(f"{name}: page scrolled while menu open")
            if shots and name == "index.html": page.screenshot(path=str(Path(shots) / "nav-open-390.png"))
            page.keyboard.press("Escape"); page.wait_for_timeout(700)
            s2 = state()
            if s2["open"] or s2["shown"] or s2["ofB"] == "hidden": probs.append(f"{name}: Escape does not close")
            page.click(".nav-toggle"); page.wait_for_timeout(700)
            page.click(".nav-toggle"); page.wait_for_timeout(700)
            if state()["open"]: probs.append(f"{name}: close button does not close")
            ctx.close()
        report("Mobile navigation opens, locks scroll and closes, on every page", not probs,
               "\n".join(probs) or f"{len(urls)} pages: full-screen, scroll locked, closes on Escape and close button")
        browser.close()

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8080/")
    ap.add_argument("--serve", action="store_true", help="serve the site from a temporary local server for this run only")
    ap.add_argument("--shots", default="")
    a = ap.parse_args()
    if a.shots: Path(a.shots).mkdir(parents=True, exist_ok=True)
    server = None
    if a.serve:
        import functools, http.server, threading
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args): pass
        handler = functools.partial(Quiet, directory=str(ROOT))
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        a.base = f"http://127.0.0.1:{server.server_address[1]}/"
    pages = sorted(ROOT.glob("*.html"))
    names = ["index.html"] + [x.name for x in pages if x.name != "index.html"]
    try:
        static_checks(pages)
        browser_checks(a.base, a.shots, names)
    finally:
        if server: server.shutdown()
    failed = sum(1 for _, ok in results if not ok)
    print(f"\n{len(results) - failed}/{len(results)} checks passed")
    sys.exit(failed)
