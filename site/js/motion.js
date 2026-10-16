export function initMotion() {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const els = document.querySelectorAll(".reveal");
  const motif = document.querySelector(".motif-giant");
  if (!reduced && motif) {
    motif.animate(
      [{ transform: "translateY(-48%) scale(0.92)", opacity: 0.6 }, { transform: "translateY(-48%) scale(1)", opacity: 1 }],
      { duration: 1100, easing: "cubic-bezier(0.22, 1, 0.36, 1)", fill: "forwards" },
    );
  }
  if (reduced) {
    els.forEach((el) => el.classList.add("visible"));
    return;
  }
  els.forEach((el, i) => {
    setTimeout(() => el.classList.add("visible"), 80 + i * 70);
  });
  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((en) => {
        if (en.isIntersecting) {
          en.target.classList.add("visible");
          io.unobserve(en.target);
        }
      });
    },
    { threshold: 0.12, rootMargin: "0px 0px -8% 0px" },
  );
  els.forEach((el) => io.observe(el));
  document.querySelector(".showcase-visual")?.classList.add("shutter");
}

export function initFeatureToggles() {
  document.querySelectorAll(".feature-band").forEach((band) => {
    const btn = band.querySelector(".toggle");
    if (!btn) return;
    const sync = () => {
      const on = btn.getAttribute("aria-checked") === "true";
      band.classList.toggle("on", on);
    };
    btn.addEventListener("click", () => {
      const next = btn.getAttribute("aria-checked") !== "true";
      btn.setAttribute("aria-checked", String(next));
      sync();
    });
    btn.addEventListener("keydown", (e) => {
      if (e.key === " " || e.key === "Enter") {
        e.preventDefault();
        btn.click();
      }
    });
    sync();
  });
}
