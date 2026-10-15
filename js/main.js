/* Progressive enhancement only: the page is complete without this file. */
(function () {
  "use strict";

  const $ = (s, c = document) => c.querySelector(s);
  const $$ = (s, c = document) => Array.from(c.querySelectorAll(s));
  const root = document.documentElement;
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const STAGGER = 85;

  /* ---------- reveals: 700ms, 24px travel, siblings cascade 85ms apart ---------- */
  const settle = (el) => {
    el.classList.remove("is-revealing");
    el.style.transitionDelay = "";
  };
  const revealer = new IntersectionObserver((entries) => {
    const groups = new Map();
    entries.forEach((en) => {
      if (!en.isIntersecting) return;
      revealer.unobserve(en.target);
      const p = en.target.parentElement;
      if (!groups.has(p)) groups.set(p, []);
      groups.get(p).push(en.target);
    });
    groups.forEach((els) => {
      els.sort((a, b) => (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1));
      els.forEach((el, i) => {
        el.style.transitionDelay = i * STAGGER + "ms";
        el.classList.add("is-revealing", "is-in");
        el.addEventListener("transitionend", function done(e) {
          if (e.target !== el || e.propertyName !== "transform") return;
          el.removeEventListener("transitionend", done);
          settle(el);
        });
        setTimeout(() => settle(el), 700 + i * STAGGER + 200); // safety net
      });
    });
  }, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });
  $$(".reveal").forEach((el) => (reduceMotion ? el.classList.add("is-in") : revealer.observe(el)));

  /* ---------- header, back-to-top ---------- */
  const header = $("#header");
  const hero = $(".hero");
  const toTop = $("#toTop");
  const onScroll = () => {
    const y = window.scrollY;
    header.classList.toggle("is-stuck", y > hero.offsetHeight * 0.4);
    toTop.classList.toggle("is-shown", y > 900);
  };
  addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  /* ---------- mobile navigation: opens, locks scroll, closes ---------- */
  const toggle = $(".nav-toggle");
  const nav = $("#nav");
  const setNav = (open) => {
    root.classList.toggle("nav-open", open);
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    if (open) $("a", nav).focus({ preventScroll: true });
  };
  toggle.addEventListener("click", () => setNav(!root.classList.contains("nav-open")));
  $$(".main-nav a").forEach((el) => el.addEventListener("click", () => setNav(false)));
  addEventListener("keydown", (e) => {
    if (e.key === "Escape" && root.classList.contains("nav-open")) { setNav(false); toggle.focus(); }
  });
  matchMedia("(min-width: 1025px)").addEventListener("change", (e) => e.matches && setNav(false));

  /* ---------- hero film: skip on Data Saver, pause when off-screen ---------- */
  const film = $(".hero-video");
  if (film) {
    if ((navigator.connection && navigator.connection.saveData) || reduceMotion) {
      film.remove();   // the poster behind it stands in
    } else {
      new IntersectionObserver(([en]) => {
        if (en.isIntersecting) film.play().catch(() => {});
        else film.pause();
      }).observe(hero);
    }
  }

  /* ---------- active nav link ---------- */
  const links = $$(".main-nav > a");
  const spy = new IntersectionObserver((entries) => {
    entries.forEach((en) => {
      if (!en.isIntersecting) return;
      links.forEach((a) => a.classList.toggle("active", a.hash === "#" + en.target.id));
    });
  }, { rootMargin: "-45% 0px -50% 0px" });
  links.forEach((a) => { const s = $(a.hash); if (s) spy.observe(s); });

  /* ---------- count-up numbers ---------- */
  const counter = new IntersectionObserver((entries) => {
    entries.forEach((en) => {
      if (!en.isIntersecting) return;
      counter.unobserve(en.target);
      const el = en.target;
      const end = parseInt(el.dataset.count, 10);
      const t0 = performance.now();
      const tick = (t) => {
        const p = Math.min((t - t0) / 1400, 1);
        el.textContent = Math.round(end * (1 - Math.pow(1 - p, 3)));
        if (p < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
  }, { threshold: 0.6 });
  if (!reduceMotion) $$("[data-count]").forEach((el) => counter.observe(el));

  /* ---------- practice areas: tabs drive a crossfading stage (wide screens) ---------- */
  const tabs = $$(".pa-tab");
  const panels = $$(".pa");
  const activate = (i, focus) => {
    tabs.forEach((t, j) => {
      const on = i === j;
      t.setAttribute("aria-selected", String(on));
      t.tabIndex = on ? 0 : -1;
    });
    panels.forEach((p, j) => p.classList.toggle("is-active", i === j));
    if (focus) tabs[i].focus();
  };
  tabs.forEach((t, i) => {
    t.addEventListener("click", () => activate(i));
    t.addEventListener("keydown", (e) => {
      const n = tabs.length;
      const k = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
      if (k) { e.preventDefault(); activate((i + k + n) % n, true); }
      if (e.key === "Home") { e.preventDefault(); activate(0, true); }
      if (e.key === "End") { e.preventDefault(); activate(n - 1, true); }
    });
  });
  $$("[data-pa]").forEach((a) => a.addEventListener("click", () => activate(parseInt(a.dataset.pa, 10))));

  /* ---------- engagement audience switch ---------- */
  const plans = $("#plans");
  const sw = $(".switch");
  const audBtns = $$("[data-aud-btn]");
  const setAud = (aud) => {
    sw.setAttribute("aria-checked", String(aud === "ind"));
    sw.setAttribute("aria-label", aud === "ind" ? "Show options for businesses" : "Show options for individuals");
    audBtns.forEach((b) => b.classList.toggle("on", b.dataset.audBtn === aud));
    plans.classList.add("is-swapping");
    setTimeout(() => {
      $$("[data-aud]", plans).forEach((el) => {
        const icon = $("svg", el);
        el.textContent = el.dataset[aud];
        if (icon) el.prepend(icon);
      });
      plans.classList.remove("is-swapping");
    }, 350);
  };
  sw.addEventListener("click", () => setAud(sw.getAttribute("aria-checked") === "true" ? "biz" : "ind"));
  audBtns.forEach((b) => b.addEventListener("click", () => setAud(b.dataset.audBtn)));

  /* ---------- vision band parallax (transform only, clamped) ---------- */
  const vision = $(".vision");
  if (!reduceMotion) {
    const parallax = () => {
      const r = vision.getBoundingClientRect();
      if (r.bottom < 0 || r.top > innerHeight) return;
      const off = Math.max(-50, Math.min(50, (r.top + r.height / 2 - innerHeight / 2) * -0.12));
      vision.style.setProperty("--py", off.toFixed(1) + "px");
    };
    addEventListener("scroll", parallax, { passive: true });
    parallax();
  }

  /* ---------- enquiry form: validate, then hand off to the visitor's mail app ---------- */
  const form = $("#enquiry");
  const note = $("#form-note");
  const say = (msg, isError) => {
    note.textContent = msg;
    note.classList.toggle("is-error", isError);
    note.hidden = false;
  };
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(form));
    const missing = ["name", "email", "message"].find((k) => !String(d[k] || "").trim());
    const badEmail = !missing && !/^\S+@\S+\.\S+$/.test(d.email);
    if (missing || badEmail) {
      say(badEmail ? "Please enter a valid email address." : "Please complete all required fields.", true);
      form.elements[missing || "email"].focus();
      return;
    }
    const body = `Name: ${d.name}\nEmail: ${d.email}\nPhone: ${d.phone || "-"}\nPractice area: ${d.area}\n\n${d.message}`;
    location.href = `mailto:reception@rclc.co.zw?subject=${encodeURIComponent("Website enquiry: " + d.area)}&body=${encodeURIComponent(body)}`;
    say("Thank you. Your email app has opened with the enquiry ready to send.", false);
  });

  $("#year").textContent = new Date().getFullYear();
})();
