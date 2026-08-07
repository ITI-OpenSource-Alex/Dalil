import "@testing-library/jest-dom/vitest";

// jsdom implements neither scrollIntoView nor matchMedia. Both are used by
// components that are otherwise perfectly testable -- MessageList scrolls the
// transcript on every update, and framer-motion's useReducedMotion reads the
// media query -- so without these stubs a component test fails on the
// environment rather than on the component.
if (typeof window !== "undefined") {
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = function scrollIntoView() {};
  }

  if (!window.matchMedia) {
    window.matchMedia = ((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
  }
}
