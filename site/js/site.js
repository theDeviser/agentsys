import { INSTALL_TARGETS } from "./install.js";

const nav = document.getElementById("nav");
const onScroll = () => nav.classList.toggle("is-scrolled", window.scrollY > 8);
window.addEventListener("scroll", onScroll, { passive: true });
onScroll();

document.querySelectorAll("[data-install]").forEach((el) => {
  el.setAttribute("href", INSTALL_TARGETS[el.dataset.install]);
});

document.querySelectorAll("[data-copy]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const text = document.getElementById(btn.dataset.copy).textContent;
    try {
      await navigator.clipboard.writeText(text);
      btn.textContent = "Copied";
    } catch {
      btn.textContent = "Press ⌘C";
    }
    setTimeout(() => { btn.textContent = "Copy"; }, 1600);
  });
});

const float = document.getElementById("hero-float");
const finePointer = window.matchMedia("(pointer: fine)").matches;
const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
if (float && finePointer && !reduced) {
  window.addEventListener("pointermove", (e) => {
    const x = (e.clientX / window.innerWidth - 0.5) * -24;
    const y = (e.clientY / window.innerHeight - 0.5) * -16;
    float.style.setProperty("--px", `${x.toFixed(1)}px`);
    float.style.setProperty("--py", `${y.toFixed(1)}px`);
  }, { passive: true });
}
