"use client";
import { useEffect } from "react";

export function GuideScripts() {
  useEffect(() => {
    function onCopyClick(this: HTMLButtonElement) {
      const id = this.getAttribute("data-copy");
      const target = id && document.getElementById(id);
      if (!target || !navigator.clipboard) return;
      navigator.clipboard.writeText(target.innerText).then(() => {
        this.textContent = "Copied";
        this.classList.add("copied");
        setTimeout(() => {
          this.textContent = "Copy";
          this.classList.remove("copied");
        }, 1600);
      });
    }
    const copyButtons = Array.from(document.querySelectorAll<HTMLButtonElement>(".copy"));
    copyButtons.forEach((btn) => btn.addEventListener("click", onCopyClick));

    const links = Array.from(document.querySelectorAll<HTMLAnchorElement>(".guide-toc a"));
    const sections = links
      .map((a) => document.querySelector(a.getAttribute("href") || ""))
      .filter((el): el is Element => !!el);
    function setActive() {
      const pos = window.scrollY + 120;
      let idx = 0;
      sections.forEach((s, i) => {
        if ((s as HTMLElement).offsetTop <= pos) idx = i;
      });
      links.forEach((a, i) => a.classList.toggle("active", i === idx));
    }
    document.addEventListener("scroll", setActive, { passive: true });
    setActive();

    let io: IntersectionObserver | undefined;
    const steps = Array.from(document.querySelectorAll<HTMLElement>(".guide-step"));
    if (window.matchMedia("(prefers-reduced-motion: no-preference)").matches) {
      io = new IntersectionObserver(
        (entries) => {
          entries.forEach((e) => {
            if (e.isIntersecting) {
              e.target.classList.add("in");
              io?.unobserve(e.target);
            }
          });
        },
        { threshold: 0.12 }
      );
      steps.forEach((s) => io!.observe(s));
    } else {
      steps.forEach((s) => s.classList.add("in"));
    }

    return () => {
      copyButtons.forEach((btn) => btn.removeEventListener("click", onCopyClick));
      document.removeEventListener("scroll", setActive);
      io?.disconnect();
    };
  }, []);

  return null;
}
