"""
Builds the inner pages from index.html, so the header, footer and every section
exist in one place only. Edit index.html, then run:

    python tools/build.py

Each page = shared head/header + a page header (photo, breadcrumb, h1, lead)
+ sections lifted from index.html + an optional closing call to action
+ shared footer. The active nav link is set per page.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = (ROOT / "index.html").read_text(encoding="utf-8")

PRE, rest = SRC.split("<main>\n", 1)
MAIN, POST = rest.split("</main>\n", 1)

def block(pattern, label):
    m = re.search(pattern, MAIN, re.S)
    assert m, f"{label} not found in index.html"
    return m.group(0)

def section(sid):
    return block(rf'<section class="[^"]*" id="{sid}"[^>]*>.*?\n</section>\n', f"section #{sid}")

RIBBON = block(r'<div class="ribbon" aria-hidden="true">.*?\n</div>\n', "ribbon")

CTA = '''<section class="cta-band ground-dark">
  <div class="container cta-grid">
    <div>
      <span class="eyebrow reveal">Start a conversation</span>
      <h2 class="reveal">Talk to a commercial attorney</h2>
    </div>
    <div class="cta-actions reveal">
      <a href="contact.html#enquiry" class="btn"><span class="btn-icon" aria-hidden="true">+</span><span class="btn-label">Book a Consultation</span></a>
      <a href="tel:+263242703505" class="link-arrow">(0242) 703 505/6 <svg width="18" height="18" aria-hidden="true"><use href="#i-arrow"/></svg></a>
    </div>
  </div>
</section>
'''

PAGES = {
    "about.html": dict(
        nav="About", title="About Us", crumb="About",
        h1="A decade of commercial counsel", lead="Who we are, what we stand for, and the people who shaped the firm since 2016.",
        img=("justice-statue.jpg", 1000, 667, "60% center"),
        description="About R. Chibaya Law Chambers: commercial attorneys in Mt Pleasant, Harare since 2016. Our mission, vision, values and credentials.",
        body=["about", RIBBON, "values", "experience", "credentials", "vision"],
    ),
    "practice-areas.html": dict(
        nav="Practice Areas", title="Practice Areas", crumb="Practice Areas",
        h1="Legal services for business and family", lead="Corporate, commercial, finance, mining, property, labour, family and litigation work for Zimbabwe.",
        img=("gavel-dark.jpg", 1800, 995, "center"),
        description="RCLC practice areas: corporate, commercial, banking and finance, mining, conveyancing, real estate, labour, family and litigation.",
        body=[RIBBON, "practice", "engage", ("faq", "ground-alt"), CTA],
    ),
    "team.html": dict(
        nav="Team", title="Our Team", crumb="Team",
        h1="Our attorneys and staff", lead="Partners, professional assistants and the staff who keep chambers running.",
        img=("team-reception.jpg", 1000, 900, "center 30%"),
        description="Meet the RCLC team: Founder and Senior Partner Rachel Chibaya, Managing Partner A.T.T. Mbotshwa and our professional staff.",
        body=[RIBBON, "team", "credentials", CTA],
    ),
    "news.html": dict(
        nav="News", title="News and Insights", crumb="News",
        h1="News and insights", lead="Firm news, professional appointments and commentary from our attorneys on the law in Zimbabwe.",
        img=("architecture.jpg", 1600, 901, "center"),
        description="News and insights from R. Chibaya Law Chambers, commercial attorneys in Harare.",
        body=["insights", CTA],
    ),
    "contact.html": dict(
        nav="Contact", title="Contact Us", crumb="Contact",
        h1="Contact us", lead="First consultations are confidential. Visit, call, email or send an enquiry below.",
        img=("advisory-meeting.jpg", 1600, 1067, "center 35%"),
        description="Contact R. Chibaya Law Chambers: No 7 Avon Rise, Mt Pleasant, Harare. (0242) 703 505/6, reception@rclc.co.zw.",
        body=[RIBBON, "contact", "faq"],
    ),
}

def page_header(cfg):
    src, w, h, pos = cfg["img"]
    return f'''<section class="page-hero" aria-labelledby="page-title">
  <div class="page-hero-media" aria-hidden="true"><img src="assets/img/{src}" alt="" width="{w}" height="{h}" fetchpriority="high" style="object-position: {pos}"></div>
  <div class="container">
    <nav class="crumbs reveal" aria-label="Breadcrumb"><a href="index.html">Home</a><span aria-hidden="true">/</span><span aria-current="page">{cfg["crumb"]}</span></nav>
    <h1 class="reveal" id="page-title">{cfg["h1"]}</h1>
    <p class="reveal">{cfg["lead"]}</p>
  </div>
</section>
'''

def build(name, cfg):
    head = PRE
    head = re.sub(r"<title>.*?</title>", f"<title>{cfg['title']} | R. Chibaya Law Chambers</title>", head)
    head = re.sub(r'<meta name="description" content="[^"]*">', f'<meta name="description" content="{cfg["description"]}">', head)
    head = head.replace('<a href="index.html" class="active" aria-current="page">Home</a>', '<a href="index.html">Home</a>')
    label = cfg["nav"]
    head = re.sub(rf'<a href="([^"]+)">{re.escape(label)}</a>', rf'<a href="\1" class="active" aria-current="page">{label}</a>', head, count=1)
    parts = [page_header(cfg)]
    for item in cfg["body"]:
        if isinstance(item, tuple):
            sid, extra = item
            parts.append(section(sid).replace(f'class="{sid}"', f'class="{sid} {extra}"', 1))
        elif item.lstrip().startswith("<"):
            parts.append(item)
        else:
            parts.append(section(item))
    html = head + "<main>\n" + "".join(parts) + "</main>\n" + POST
    if name == "news.html":   # the news page links onward to the archive instead of to itself
        html = html.replace('<a href="news.html" class="link-arrow reveal">View all news',
                            '<a href="https://www.rclc.co.zw/articles-insights/" target="_blank" rel="noopener" class="link-arrow reveal">Older articles')
    (ROOT / name).write_text(html, encoding="utf-8")
    print(f"built {name}")

if __name__ == "__main__":
    for name, cfg in PAGES.items():
        build(name, cfg)
