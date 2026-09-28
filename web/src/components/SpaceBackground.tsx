"use client";

import { useEffect, useRef } from "react";

/**
 * Slow-drift starfield with perspective projection: reads as gently
 * moving toward the centre of a galaxy. Draws to a fixed-position
 * <canvas> behind main content.
 *
 * Design:
 * - ~260 stars, each holds (x, y, z) in world space. Every frame z
 *   decreases by SPEED; when a star passes the camera (z < 1) it
 *   respawns far away with fresh random x, y. Perspective projection
 *   x/z, y/z from the viewport centre gives the parallax-warp illusion.
 * - Nebula washes and a galactic-core glow are painted every frame as
 *   radial gradients so the canvas owns the entire background and the
 *   CSS layer stays clean.
 * - A low-alpha black rect is painted every frame *before* the stars,
 *   which leaves a short trail behind each star and sells the drift
 *   without needing full-length streaks.
 * - Respects `prefers-reduced-motion`: stops animating, paints a static
 *   distribution once.
 * - Pauses when the tab is hidden (page visibility) so the loop doesn't
 *   burn cycles or laptop battery in the background.
 * - Reads `body.drawer-open` via CSS (opacity transition on the canvas
 *   element) so the effect fades when the SettingsDrawer takes focus.
 */
export function SpaceBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvasNullable = canvasRef.current;
    if (!canvasNullable) return;
    const ctxNullable = canvasNullable.getContext("2d");
    if (!ctxNullable) return;
    // Explicit non-nullable aliases so TS keeps the narrowing across
    // the nested function declarations below (control-flow analysis
    // drops narrowing at function boundaries in strict mode).
    const canvas: HTMLCanvasElement = canvasNullable;
    const ctx: CanvasRenderingContext2D = ctxNullable;

    const prefersReducedMotion =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const dpr = window.devicePixelRatio || 1;
    let width = window.innerWidth;
    let height = window.innerHeight;

    function resize() {
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      // setTransform (not scale) so repeated resize calls do not
      // compound the scale factor.
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    resize();
    window.addEventListener("resize", resize);

    // Star tints: mostly white, a few blue/yellow/red giants.
    function pickTint(): [number, number, number] {
      const r = Math.random();
      if (r < 0.82) return [255, 255, 255];
      if (r < 0.9) return [190, 210, 255]; // blue-white
      if (r < 0.96) return [255, 240, 210]; // yellow-white
      return [255, 200, 180]; // warm red giant
    }

    const NUM_STARS = 260;
    const Z_MAX = 1000;
    const FOV = 340; // higher = more zoom / more warp feel
    const WORLD = 2000; // half-extent of spawn box in x/y world units

    interface Star {
      x: number;
      y: number;
      z: number;
      tint: [number, number, number];
    }
    const stars: Star[] = Array.from({ length: NUM_STARS }, () => ({
      x: (Math.random() - 0.5) * WORLD,
      y: (Math.random() - 0.5) * WORLD,
      z: Math.random() * Z_MAX + 1,
      tint: pickTint(),
    }));

    // Speed: 0.65 world units per frame @60fps = feels like a slow
    // drift, not warp speed. Tuned by feel; the whole illusion depends
    // on this being slower than the eye's saccade rate.
    const SPEED = prefersReducedMotion ? 0 : 0.65;
    // Motion-trail fade. Lower alpha = longer trails. 0.14 gives short
    // dashes that read as motion without smearing.
    const TRAIL_ALPHA = prefersReducedMotion ? 1 : 0.14;

    let raf = 0;
    let running = true;

    function drawFrame() {
      // Motion-trail wash: paint semi-transparent black over the entire
      // canvas each frame so previous stars fade out gradually.
      ctx.fillStyle = `rgba(0, 0, 0, ${TRAIL_ALPHA})`;
      ctx.fillRect(0, 0, width, height);

      const cx = width / 2;
      const cy = height / 2;

      // Nebula washes, painted every frame so they scale with resize
      // and always match the star centre.
      const nebulaA = ctx.createRadialGradient(
        width * 0.25, height * 0.3, 0,
        width * 0.25, height * 0.3, Math.max(width, height) * 0.55,
      );
      nebulaA.addColorStop(0, "rgba(57, 135, 229, 0.07)");
      nebulaA.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = nebulaA;
      ctx.fillRect(0, 0, width, height);

      const nebulaB = ctx.createRadialGradient(
        width * 0.82, height * 0.2, 0,
        width * 0.82, height * 0.2, Math.max(width, height) * 0.5,
      );
      nebulaB.addColorStop(0, "rgba(144, 133, 233, 0.06)");
      nebulaB.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = nebulaB;
      ctx.fillRect(0, 0, width, height);

      const nebulaC = ctx.createRadialGradient(
        width * 0.65, height * 0.85, 0,
        width * 0.65, height * 0.85, Math.max(width, height) * 0.6,
      );
      nebulaC.addColorStop(0, "rgba(217, 89, 38, 0.04)");
      nebulaC.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = nebulaC;
      ctx.fillRect(0, 0, width, height);

      // Galactic core glow at viewport centre. This is the visual
      // anchor: makes the drift feel like it has a destination.
      const coreRadius = Math.min(width, height) * 0.22;
      const core = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreRadius);
      core.addColorStop(0, "rgba(230, 210, 255, 0.14)");
      core.addColorStop(0.4, "rgba(150, 130, 220, 0.06)");
      core.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = core;
      ctx.fillRect(0, 0, width, height);

      // Stars.
      for (const star of stars) {
        star.z -= SPEED;
        if (star.z < 1) {
          // Respawn far away with new x, y so the field never depletes.
          star.z = Z_MAX;
          star.x = (Math.random() - 0.5) * WORLD;
          star.y = (Math.random() - 0.5) * WORLD;
        }

        const scale = FOV / star.z;
        const sx = cx + star.x * scale;
        const sy = cy + star.y * scale;

        if (sx < -10 || sx > width + 10 || sy < -10 || sy > height + 10) {
          continue;
        }

        // Closer stars get larger and brighter; farther ones fade.
        const depth = 1 - star.z / Z_MAX;
        const size = Math.max(0.3, depth * 2.2);
        const alpha = 0.15 + depth * 0.85;
        const [r, g, b] = star.tint;

        // Glow halo for the closest ~5% of stars: makes them read as
        // bright foreground stars, not dust.
        if (depth > 0.7) {
          const haloGrad = ctx.createRadialGradient(sx, sy, 0, sx, sy, size * 4);
          haloGrad.addColorStop(0, `rgba(${r}, ${g}, ${b}, ${alpha * 0.35})`);
          haloGrad.addColorStop(1, "rgba(0, 0, 0, 0)");
          ctx.fillStyle = haloGrad;
          ctx.beginPath();
          ctx.arc(sx, sy, size * 4, 0, Math.PI * 2);
          ctx.fill();
        }

        ctx.beginPath();
        ctx.arc(sx, sy, size, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${alpha})`;
        ctx.fill();
      }
    }

    function tick() {
      if (!running) return;
      drawFrame();
      raf = requestAnimationFrame(tick);
    }

    if (prefersReducedMotion) {
      // Paint a single static frame.
      drawFrame();
    } else {
      tick();
    }

    function handleVisibility() {
      if (document.hidden) {
        running = false;
        cancelAnimationFrame(raf);
      } else if (!prefersReducedMotion) {
        running = true;
        tick();
      }
    }
    document.addEventListener("visibilitychange", handleVisibility);

    return () => {
      running = false;
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      className="space-bg pointer-events-none fixed inset-0 -z-10 transition-opacity duration-300 ease-out"
    />
  );
}
