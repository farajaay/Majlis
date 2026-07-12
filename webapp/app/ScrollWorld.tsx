"use client";
import { useEffect, useRef } from "react";

/**
 * Scroll-World — an ambient, slowly-panning dotted world map rendered behind
 * the council floor. Deliberately subtle: it lives at z-index -1, tinted for
 * the light theme, so the transcript stays fully readable while the world
 * drifts underneath. Honors prefers-reduced-motion (renders a static map).
 *
 * Self-contained: continents are approximated from a small set of lat/long
 * rectangles sampled into dots, then projected equirectangularly and tiled
 * horizontally so the pan wraps seamlessly. No images, no network.
 *
 * See .claude/skills/scroll-world for how to tune / extend this.
 */

// Rough continent boxes: [lonMin, lonMax, latMin, latMax]. Approximate on
// purpose — dotted + jittered + faint reads as a world map, not a diagram.
const LAND: Array<[number, number, number, number]> = [
  // North America
  [-168, -140, 54, 71], [-140, -64, 48, 70], [-128, -96, 30, 49], [-96, -72, 30, 47],
  [-118, -93, 15, 31], [-92, -83, 8, 18],
  [-56, -20, 60, 83], // Greenland
  // South America
  [-81, -50, 0, 12], [-79, -35, -18, 0], [-73, -40, -35, -18], [-75, -65, -52, -35],
  // Europe
  [-10, 30, 40, 60], [4, 30, 58, 71], [-9, 2, 50, 59],
  // Africa
  [-17, 50, 15, 35], [-10, 45, -5, 15], [10, 42, -35, -5],
  // Middle East + Asia
  [34, 60, 12, 42], [40, 180, 50, 75], [60, 120, 34, 52], [95, 140, 22, 45],
  [68, 90, 8, 34], [95, 108, 10, 28],
  [95, 141, -10, 6], // Indonesia
  // Australia + NZ
  [113, 154, -39, -12], [166, 179, -47, -34],
];

const LAT_TOP = 80;
const LAT_BOT = -58;
const STEP = 3; // degrees between sampled dots

type Dot = { lon: number; lat: number; j: number };

function buildDots(): Dot[] {
  const dots: Dot[] = [];
  let i = 0;
  for (const [lo0, lo1, la0, la1] of LAND) {
    for (let lon = lo0; lon <= lo1; lon += STEP) {
      for (let lat = la0; lat <= la1; lat += STEP) {
        // deterministic jitter so edges aren't ruler-straight
        const j = (Math.sin(i * 12.9898) * 43758.5453) % 1;
        dots.push({ lon, lat, j: j - Math.floor(j) });
        i++;
      }
    }
  }
  return dots;
}

export function ScrollWorld() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dots = buildDots();
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let W = 0, H = 0, dpr = 1, worldW = 1200;
    // a few "hot" nodes and arcs for signal-y motion
    const nodes = [3, 97, 220, 355, 480, 610].map((n) => dots[n % dots.length]).filter(Boolean);
    const arcs = [
      [dots[97], dots[480]],
      [dots[220], dots[610]],
      [dots[3], dots[355]],
    ].filter(([a, b]) => a && b) as Array<[Dot, Dot]>;

    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      W = window.innerWidth;
      H = window.innerHeight;
      worldW = Math.max(W * 1.5, 1100);
      canvas!.width = Math.floor(W * dpr);
      canvas!.height = Math.floor(H * dpr);
      canvas!.style.width = W + "px";
      canvas!.style.height = H + "px";
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    const lonToX = (lon: number) => ((lon + 180) / 360) * worldW;
    const latToY = (lat: number) => ((LAT_TOP - lat) / (LAT_TOP - LAT_BOT)) * H;

    function draw(t: number) {
      const offset = reduce ? worldW * 0.18 : (t * 0.012) % worldW;
      ctx!.clearRect(0, 0, W, H);

      // dotted continents, tiled across the wrap — matches --paper (#212a35)
      for (const d of dots) {
        const baseX = lonToX(d.lon);
        const y = latToY(d.lat) + (d.j - 0.5) * 3;
        for (const shift of [-worldW, 0, worldW]) {
          const x = ((baseX - offset) % worldW) + shift;
          if (x < -2 || x > W + 2) continue;
          ctx!.fillStyle = `rgba(33,42,53,${0.1 + d.j * 0.09})`;
          ctx!.fillRect(x, y, 1.4, 1.4);
        }
      }

      // faint arcs between hot nodes — matches --brass-2 (#c2872b)
      for (let k = 0; k < arcs.length; k++) {
        const [a, b] = arcs[k];
        const ax = ((lonToX(a.lon) - offset) % worldW + worldW) % worldW;
        const bx = ((lonToX(b.lon) - offset) % worldW + worldW) % worldW;
        if (Math.abs(ax - bx) > W) continue; // skip when wrapped apart
        const ay = latToY(a.lat), by = latToY(b.lat);
        const cx = (ax + bx) / 2, cy = Math.min(ay, by) - 60 - k * 12;
        ctx!.strokeStyle = "rgba(194,135,43,0.15)";
        ctx!.lineWidth = 1;
        ctx!.beginPath();
        ctx!.moveTo(ax, ay);
        ctx!.quadraticCurveTo(cx, cy, bx, by);
        ctx!.stroke();
        if (!reduce) {
          const p = (t / 3200 + k * 0.33) % 1;
          const mx = (1 - p) * (1 - p) * ax + 2 * (1 - p) * p * cx + p * p * bx;
          const my = (1 - p) * (1 - p) * ay + 2 * (1 - p) * p * cy + p * p * by;
          ctx!.fillStyle = "rgba(194,135,43,0.5)";
          ctx!.beginPath();
          ctx!.arc(mx, my, 1.8, 0, Math.PI * 2);
          ctx!.fill();
        }
      }

      // pulsing hot nodes
      for (let k = 0; k < nodes.length; k++) {
        const n = nodes[k];
        const x = ((lonToX(n.lon) - offset) % worldW + worldW) % worldW;
        if (x > W + 6) continue;
        const y = latToY(n.lat);
        const pulse = reduce ? 0.5 : 0.5 + 0.5 * Math.sin(t / 900 + k);
        ctx!.fillStyle = `rgba(194,135,43,${0.18 + pulse * 0.3})`;
        ctx!.beginPath();
        ctx!.arc(x, y, 1.6 + pulse * 1.6, 0, Math.PI * 2);
        ctx!.fill();
      }
    }

    let raf = 0;
    let last = 0;
    function loop(t: number) {
      // throttle to ~30fps — plenty for an ambient backdrop
      if (t - last > 33) {
        draw(t);
        last = t;
      }
      raf = requestAnimationFrame(loop);
    }

    resize();
    window.addEventListener("resize", resize);
    if (reduce) {
      draw(0);
    } else {
      raf = requestAnimationFrame(loop);
    }

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return <canvas ref={ref} className="scroll-world" aria-hidden="true" />;
}
