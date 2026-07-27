"use client";

import { useEffect, useRef } from "react";
import { useAudioVisualizer } from "@/app/hooks/useAudioVisualizer";

interface WaveformCanvasProps {
  /** The live microphone stream to visualize, or null while not recording. */
  stream: MediaStream | null;
  /** Gate on the caller's recording state, not just stream presence. */
  active: boolean;
  className?: string;
}

// Caps canvas backing resolution on very high-DPI displays so redraw cost
// doesn't scale unbounded with devicePixelRatio.
const MAX_DEVICE_PIXEL_RATIO = 2;

// Bar geometry, in CSS pixels. Bar count is derived from the available width
// so the visualiser stays balanced from a 375px phone to a wide desktop panel.
const BAR_WIDTH = 4;
const BAR_GAP = 6;
const MIN_BAR_HEIGHT = 2;

// Automatic gain control. Speech rarely reaches full scale — a normal voice at
// a normal distance peaks well under 0.2 — so a fixed gain leaves every bar
// pinned near the floor and the visualiser looks dead. Instead the loudest
// recent peak becomes the reference the bars are drawn against, and it decays
// slowly so the display re-scales to how loudly someone is actually speaking.
const AGC_DECAY = 0.995;
// Floor for that reference, so near-silence isn't amplified into fake activity.
const AGC_MIN_REFERENCE = 0.06;
// <1 lifts quiet passages without letting loud ones clip.
const AGC_GAMMA = 0.8;

// How much of the previous frame's height carries into the next one. Raw
// analyser output is jittery frame-to-frame; easing toward the target reads as
// fluid motion instead of strobing, which is most of what separates a polished
// visualiser from a cheap one.
const SMOOTHING = 0.72;

// Gradient stops (emerald family, matching the panel's accent).
const GRADIENT_TOP = "#34D399";
const GRADIENT_MID = "#10B981";
const GRADIENT_BOTTOM = "#047857";

export default function WaveformCanvas({
  stream,
  active,
  className,
}: WaveformCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const dataArrayRef = useRef<Uint8Array<ArrayBuffer> | null>(null);
  const barHeightsRef = useRef<number[]>([]);
  /** Running loudest-peak reference for automatic gain control. */
  const agcRef = useRef(AGC_MIN_REFERENCE);
  const { analyser, isSupported } = useAudioVisualizer(active ? stream : null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !analyser) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = Math.min(window.devicePixelRatio || 1, MAX_DEVICE_PIXEL_RATIO);

    const resize = () => {
      const { clientWidth, clientHeight } = canvas;
      if (clientWidth === 0 || clientHeight === 0) return;
      canvas.width = Math.round(clientWidth * dpr);
      canvas.height = Math.round(clientHeight * dpr);
    };
    resize();

    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(canvas);

    if (
      !dataArrayRef.current ||
      dataArrayRef.current.length !== analyser.frequencyBinCount
    ) {
      dataArrayRef.current = new Uint8Array(analyser.frequencyBinCount);
    }
    const dataArray = dataArrayRef.current;

    let mounted = true;
    let rafId: number;

    const draw = () => {
      if (!mounted) return;

      analyser.getByteTimeDomainData(dataArray);

      const { width, height } = canvas;
      ctx.clearRect(0, 0, width, height);

      const centerY = height / 2;
      const barW = BAR_WIDTH * dpr;
      const gap = BAR_GAP * dpr;
      const step = barW + gap;
      const barCount = Math.max(1, Math.floor(width / step));

      // Keep the smoothing buffer in step with a resized canvas.
      if (barHeightsRef.current.length !== barCount) {
        barHeightsRef.current = new Array(barCount).fill(0);
      }
      const smoothed = barHeightsRef.current;

      // Peak amplitude per bucket. Peak (rather than mean) keeps transients
      // visible — speech looks responsive instead of mushy.
      const bucketSize = Math.floor(dataArray.length / barCount) || 1;
      const maxBarHeight = centerY - 2 * dpr;

      const gradient = ctx.createLinearGradient(0, 0, 0, height);
      gradient.addColorStop(0, GRADIENT_TOP);
      gradient.addColorStop(0.5, GRADIENT_MID);
      gradient.addColorStop(1, GRADIENT_BOTTOM);
      ctx.fillStyle = gradient;

      // Total horizontal run is centred so there's never a ragged right edge.
      const totalWidth = barCount * step - gap;
      const offsetX = (width - totalWidth) / 2;

      // Pass 1: per-bar peak amplitude, plus this frame's overall loudest peak.
      const peaks = new Array<number>(barCount);
      let framePeak = 0;

      for (let i = 0; i < barCount; i++) {
        let peak = 0;
        const start = i * bucketSize;

        for (let j = 0; j < bucketSize; j++) {
          const sample = dataArray[start + j];
          if (sample === undefined) break;
          // Byte samples are centred on 128; distance from centre is amplitude.
          const deviation = Math.abs(sample - 128) / 128;
          if (deviation > peak) peak = deviation;
        }

        peaks[i] = peak;
        if (peak > framePeak) framePeak = peak;
      }

      // Track the recent loudest peak and decay it, so the scale follows the
      // speaker instead of an absolute level they may never reach.
      agcRef.current = Math.max(framePeak, agcRef.current * AGC_DECAY);
      const reference = Math.max(agcRef.current, AGC_MIN_REFERENCE);

      // Pass 2: draw.
      for (let i = 0; i < barCount; i++) {
        const ratio = Math.min(peaks[i] / reference, 1);
        const target = Math.pow(ratio, AGC_GAMMA) * maxBarHeight;
        smoothed[i] = smoothed[i] * SMOOTHING + target * (1 - SMOOTHING);

        const barHeight = Math.max(smoothed[i], MIN_BAR_HEIGHT * dpr);
        const x = offsetX + i * step;
        const y = centerY - barHeight;
        const h = barHeight * 2;
        const radius = barW / 2;

        ctx.beginPath();
        if (typeof ctx.roundRect === "function") {
          ctx.roundRect(x, y, barW, h, radius);
        } else {
          // Older engines: square bars are an acceptable degradation.
          ctx.rect(x, y, barW, h);
        }
        ctx.fill();
      }

      rafId = requestAnimationFrame(draw);
    };

    rafId = requestAnimationFrame(draw);

    return () => {
      mounted = false;
      cancelAnimationFrame(rafId);
      resizeObserver.disconnect();
      barHeightsRef.current = [];
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    };
  }, [analyser]);

  if (!isSupported) return null;

  return (
    <canvas
      ref={canvasRef}
      data-testid="waveform-canvas"
      aria-hidden="true"
      className={className ?? "h-full w-full"}
    />
  );
}
