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

  // Nor IntersectionObserver, which Reveal (components/marketing/reveal.tsx)
  // constructs on mount. Any test that renders a marketing section -- or
  // anything built on SectionHeader, such as /pricing -- otherwise fails in
  // the observer constructor rather than on anything the component did.
  // The stub never fires: these tests assert rendered content, not scroll
  // behaviour, and Reveal's children are in the DOM either way.
  if (!window.IntersectionObserver) {
    class MockIntersectionObserver implements IntersectionObserver {
      readonly root = null;
      readonly rootMargin = "";
      readonly thresholds: ReadonlyArray<number> = [];
      observe() {}
      unobserve() {}
      disconnect() {}
      takeRecords(): IntersectionObserverEntry[] {
        return [];
      }
    }
    window.IntersectionObserver =
      MockIntersectionObserver as unknown as typeof window.IntersectionObserver;
    globalThis.IntersectionObserver =
      MockIntersectionObserver as unknown as typeof globalThis.IntersectionObserver;
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
