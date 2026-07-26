"use client";

import { useEffect, useRef } from "react";

/* ──────────────────────────────────────────────
   SphericalSpectrum — earth-like sphere with
   lat/meridian lines that gently pulse and wave.

   Start as clean circles (like a wireframe globe),
   each line oscillates smoothly over time, no
   flower shapes — just breathing, rippling rings.
────────────────────────────────────────────── */

interface SphereLine {
  yBase: number;       // normalized Y on sphere (-1 to 1)
  color: string;       // RGB
  alpha: number;       // base stroke alpha
  lineWidth: number;
  waveFreq: number;    // how fast it pulses
  waveSpeed: number;   // traveling wave speed
  waveAmp: number;     // radial displacement amplitude
}

export function CellAnimation() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animationId: number;
    let time = 0;

    /* ── Config ──────────────────────────────── */
    const SPHERE_RADIUS = 130;
    const FOV = 700;
    const ROTATION_SPEED = 0.004;
    const TILT_X = 0.35;

    // latitude lines (horizontal rings on the sphere)
    const LAT_RINGS: SphereLine[] = [
      { yBase: -0.8, color: "139, 92, 246", alpha: 0.35, lineWidth: 1.2, waveFreq: 0.012, waveSpeed: 0.015, waveAmp: 6 },
      { yBase: -0.55, color: "139, 92, 246", alpha: 0.40, lineWidth: 1.3, waveFreq: 0.014, waveSpeed: -0.012, waveAmp: 7 },
      { yBase: -0.3, color: "139, 92, 246", alpha: 0.45, lineWidth: 1.5, waveFreq: 0.010, waveSpeed: 0.018, waveAmp: 8 },
      { yBase:  0.0, color: "139, 92, 246", alpha: 0.55, lineWidth: 1.8, waveFreq: 0.016, waveSpeed: -0.020, waveAmp: 10 },
      { yBase:  0.3, color: "139, 92, 246", alpha: 0.45, lineWidth: 1.5, waveFreq: 0.013, waveSpeed: 0.014, waveAmp: 8 },
      { yBase:  0.55, color: "139, 92, 246", alpha: 0.40, lineWidth: 1.3, waveFreq: 0.011, waveSpeed: -0.016, waveAmp: 7 },
      { yBase:  0.8, color: "139, 92, 246", alpha: 0.35, lineWidth: 1.2, waveFreq: 0.015, waveSpeed: 0.013, waveAmp: 6 },
    ];

    // meridian lines (vertical arcs from pole to pole)
    const MERIDIAN_COUNT = 6;
    const MERIDIAN_ALPHA = 0.2;
    const MERIDIAN_LINE_WIDTH = 0.8;
    const MERIDIAN_WAVE_FREQ = 0.01;
    const MERIDIAN_WAVE_SPEED = 0.01;
    const MERIDIAN_WAVE_AMP = 5;

    /* ── Rotation helpers ────────────────────── */
    function rotateX(v: [number, number, number], a: number): [number, number, number] {
      const [x, y, z] = v;
      const c = Math.cos(a), s = Math.sin(a);
      return [x, y * c - z * s, y * s + z * c];
    }
    function rotateY(v: [number, number, number], a: number): [number, number, number] {
      const [x, y, z] = v;
      const c = Math.cos(a), s = Math.sin(a);
      return [x * c + z * s, y, -x * s + z * c];
    }

    /* ── Resize ──────────────────────────────── */
    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      canvas.width = canvas.clientWidth * dpr;
      canvas.height = canvas.clientHeight * dpr;
      ctx.scale(dpr, dpr);
    };

    /* ── Draw ────────────────────────────────── */
    const draw = () => {
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      const cx = width / 2;
      const cy = height / 2;

      ctx.clearRect(0, 0, width, height);

      // subtle radial glow
      const bgGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, width * 0.45);
      bgGrad.addColorStop(0, "rgba(139, 92, 246, 0.08)");
      bgGrad.addColorStop(0.5, "rgba(59, 130, 246, 0.03)");
      bgGrad.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = bgGrad;
      ctx.fillRect(0, 0, width, height);

      // global rotation
      const rotY = time * ROTATION_SPEED;
      const rotX = time * ROTATION_SPEED * TILT_X;

      // project 3D → 2D
      function project(px: number, py: number, pz: number) {
        const scale = FOV / (FOV + pz + SPHERE_RADIUS * 2);
        return { sx: cx + px * scale, sy: cy + py * scale, scale, z: pz };
      }

      // ── Latitude rings ───────────────────────
      interface RingPoint {
        sx: number;
        sy: number;
        z: number;
        scale: number;
      }

      const allRings: { pts: RingPoint[]; ring: SphereLine; avgZ: number }[] = [];

      for (const ring of LAT_RINGS) {
        const pts: RingPoint[] = [];
        const SEG = 100;

        for (let i = 0; i <= SEG; i++) {
          const angle = (i / SEG) * Math.PI * 2;

          // base position on sphere at this latitude
          const baseR = Math.sqrt(SPHERE_RADIUS * SPHERE_RADIUS - (ring.yBase * SPHERE_RADIUS) ** 2);
          const by = ring.yBase * SPHERE_RADIUS;

          // gentle traveling wave displacement along radius
          // use sin(angle + t*speed) for a smooth ripple around the ring
          const wave = Math.sin(angle * 3 + time * ring.waveSpeed + ring.waveFreq * time) * ring.waveAmp;
          const r = baseR + wave;

          const wx = Math.cos(angle) * r;
          const wy = by;
          const wz = Math.sin(angle) * r;

          // rotate into scene space
          let v = rotateY([wx, wy, wz], rotY);
          v = rotateX(v, rotX);

          const p = project(v[0], v[1], v[2]);
          pts.push(p);
        }

        allRings.push({ pts, ring, avgZ: pts.reduce((s, p) => s + p.z, 0) / pts.length });
      }

      // sort back-to-front
      allRings.sort((a, b) => a.avgZ - b.avgZ);

      // draw latitude rings
      for (let idx = 0; idx < allRings.length; idx++) {
        const { pts, ring } = allRings[idx];

        const depthFade = 0.4 + 0.6 * ((idx + 1) / allRings.length);
        const alpha = ring.alpha * depthFade;

        ctx.beginPath();
        ctx.moveTo(pts[0].sx, pts[0].sy);
        for (let i = 1; i < pts.length; i++) {
          ctx.lineTo(pts[i].sx, pts[i].sy);
        }
        ctx.closePath();
        ctx.strokeStyle = `rgba(${ring.color}, ${alpha})`;
        ctx.lineWidth = ring.lineWidth;
        ctx.stroke();
      }

      // ── Meridian arcs ────────────────────────
      for (let m = 0; m < MERIDIAN_COUNT; m++) {
        const meridianAngle = (m / MERIDIAN_COUNT) * Math.PI * 2;
        const SEG = 80;
        const pts: RingPoint[] = [];

        for (let i = 0; i <= SEG; i++) {
          const theta = (i / SEG) * Math.PI; // 0 to PI (top to bottom of arc)

          // base point on meridian circle
          const vx = Math.sin(theta) * Math.cos(meridianAngle) * SPHERE_RADIUS;
          const vy = Math.cos(theta) * SPHERE_RADIUS;
          const vz = Math.sin(theta) * Math.sin(meridianAngle) * SPHERE_RADIUS;

          // gentle wave displacement
          const wave = Math.sin(theta * 4 + time * MERIDIAN_WAVE_SPEED + MERIDIAN_WAVE_FREQ * time) * MERIDIAN_WAVE_AMP;
          const len = Math.sqrt(vx * vx + vy * vy + vz * vz);
          const nx = vx / len, ny = vy / len, nz = vz / len;
          const wx = vx + nx * wave;
          const wy = vy + ny * wave;
          const wz = vz + nz * wave;

          // rotate into scene space
          let v = rotateY([wx, wy, wz], rotY);
          v = rotateX(v, rotX);

          const p = project(v[0], v[1], v[2]);
          pts.push(p);
        }

        // sort segments by z for proper layering
        const segs = pts.map((p, i) => ({ ...p, z: pts[i].z }));
        segs.sort((a, b) => a.z - b.z);

        ctx.beginPath();
        ctx.moveTo(segs[0].sx, segs[0].sy);
        for (let i = 1; i < segs.length; i++) {
          ctx.lineTo(segs[i].sx, segs[i].sy);
        }
        ctx.strokeStyle = `rgba(139, 92, 246, ${MERIDIAN_ALPHA})`;
        ctx.lineWidth = MERIDIAN_LINE_WIDTH;
        ctx.stroke();
      }

      time++;
      animationId = requestAnimationFrame(draw);
    };

    resize();
    window.addEventListener("resize", resize);
    draw();

    return () => {
      window.removeEventListener("resize", resize);
      cancelAnimationFrame(animationId);
    };
  }, []);

  return (
    <div className="relative w-full h-[400px] overflow-hidden">
      <canvas
        ref={canvasRef}
        className="absolute inset-0 w-full h-full"
        style={{ display: "block" }}
      />
      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-[var(--bg-base)]" />
    </div>
  );
}
