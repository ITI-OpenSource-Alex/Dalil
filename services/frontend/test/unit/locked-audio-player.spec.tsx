import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, fireEvent } from "@testing-library/react";
import LockedAudioPlayer from "@/components/listening/LockedAudioPlayer";

// jsdom doesn't implement HTMLMediaElement playback, so `.play()`/`.pause()`
// throw "not implemented" unless stubbed.
beforeEach(() => {
  window.HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
  window.HTMLMediaElement.prototype.pause = vi.fn();
});

function getAudio(container: HTMLElement): HTMLAudioElement {
  return container.querySelector("audio") as HTMLAudioElement;
}

// jsdom exposes `currentTime` as an accessor on the prototype; redefining it
// as an own, writable property on the instance lets the test simulate both
// "natural" playback advances (assign + fire timeupdate) and "external"
// jumps (assign directly, then fire seeking) the same way a real browser's
// media element would report them.
function setCurrentTime(audio: HTMLAudioElement, value: number) {
  Object.defineProperty(audio, "currentTime", {
    value,
    configurable: true,
    writable: true,
  });
}

describe("LockedAudioPlayer", () => {

/**
 * Advance playback to `target` the way a browser does: many small steps.
 *
 * These specs used to jump straight to the watermark with a single
 * `setCurrentTime(audio, 10)` + `timeUpdate`. A real `timeupdate` fires about
 * four times a second, so a ten-second advance in one event is not playback --
 * it is indistinguishable from a seek, which is the very thing the player must
 * reject. Encoding it as "normal playback" forced the lock's tolerance above
 * ten seconds, which would let a candidate skip ten seconds at a time.
 *
 * Stepping keeps every assertion in this file intact while letting the product
 * hold a tolerance that reflects how the event actually behaves.
 */
function playTo(audio: HTMLAudioElement, target: number, step = 0.25) {
  for (let t = step; t < target - 1e-9; t += step) {
    setCurrentTime(audio, Math.min(t, target));
    fireEvent.timeUpdate(audio);
  }
  setCurrentTime(audio, target);
  fireEvent.timeUpdate(audio);
}

  it("snaps back to the allowed watermark after an external forward jump during playback", () => {
    const { container } = render(<LockedAudioPlayer src="test.mp3" />);
    const audio = getAudio(container);

    Object.defineProperty(audio, "duration", {
      value: 100,
      configurable: true,
    });
    fireEvent.loadedMetadata(audio);

    // Normal forward playback advances the allowed watermark to 10s.
    playTo(audio, 10);

    // Simulate external code (devtools, a script, a scrub attempt) jumping
    // playback ahead without going through the component's own controls.
    audio.currentTime = 40;
    fireEvent(audio, new Event("seeking"));

    expect(audio.currentTime).toBe(10);
  });

  it("snaps back to the allowed watermark after an external backward jump", () => {
    const { container } = render(<LockedAudioPlayer src="test.mp3" />);
    const audio = getAudio(container);

    Object.defineProperty(audio, "duration", {
      value: 100,
      configurable: true,
    });
    fireEvent.loadedMetadata(audio);

    playTo(audio, 25);

    audio.currentTime = 2;
    fireEvent(audio, new Event("seeking"));

    expect(audio.currentTime).toBe(25);
  });

  it("also corrects a jump reported only via timeupdate (no seeking event fired)", () => {
    // Programmatic assignment to `currentTime` doesn't always dispatch a
    // `seeking` event depending on how it's done, so the watermark check in
    // the timeupdate handler itself must independently catch a divergence.
    const { container } = render(<LockedAudioPlayer src="test.mp3" />);
    const audio = getAudio(container);

    Object.defineProperty(audio, "duration", {
      value: 100,
      configurable: true,
    });
    fireEvent.loadedMetadata(audio);

    playTo(audio, 10);

    // A jump reported only through timeupdate, with no seeking event.
    setCurrentTime(audio, 60);
    fireEvent.timeUpdate(audio);

    expect(audio.currentTime).toBe(10);
  });

  it("does not treat small natural forward drift as an illegal seek", () => {
    const { container } = render(<LockedAudioPlayer src="test.mp3" />);
    const audio = getAudio(container);

    Object.defineProperty(audio, "duration", {
      value: 100,
      configurable: true,
    });
    fireEvent.loadedMetadata(audio);

    setCurrentTime(audio, 10);
    fireEvent.timeUpdate(audio);

    // Well inside the component's own tolerance band for natural playback
    // ticks — should be accepted as the new watermark, not corrected.
    setCurrentTime(audio, 10.1);
    fireEvent.timeUpdate(audio);

    expect(audio.currentTime).toBe(10.1);
  });

  it("keeps the watermark at 0 if a seek is attempted before any playback has occurred", () => {
    const { container } = render(<LockedAudioPlayer src="test.mp3" />);
    const audio = getAudio(container);

    Object.defineProperty(audio, "duration", {
      value: 100,
      configurable: true,
    });
    fireEvent.loadedMetadata(audio);

    audio.currentTime = 50;
    fireEvent(audio, new Event("seeking"));

    expect(audio.currentTime).toBe(0);
  });
});
