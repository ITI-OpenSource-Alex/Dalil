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
  it("snaps back to the allowed watermark after an external forward jump during playback", () => {
    const { container } = render(<LockedAudioPlayer src="test.mp3" />);
    const audio = getAudio(container);

    Object.defineProperty(audio, "duration", {
      value: 100,
      configurable: true,
    });
    fireEvent.loadedMetadata(audio);

    // Normal forward playback advances the allowed watermark to 10s.
    setCurrentTime(audio, 10);
    fireEvent.timeUpdate(audio);

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

    setCurrentTime(audio, 25);
    fireEvent.timeUpdate(audio);

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

    setCurrentTime(audio, 10);
    fireEvent.timeUpdate(audio);

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
