import { useEffect } from "react";

/**
 * Mobile Safari doesn't reliably shrink dvh-based layouts when the on-screen
 * keyboard opens alongside another layout change (e.g. an attachment chip
 * appearing), leaving fixed-position content hidden behind the keyboard.
 * This tracks the actual visible viewport size via the VisualViewport API
 * and exposes it as --app-height, which CSS can use instead of trusting
 * dvh to update correctly on its own.
 */
export function useVisualViewportHeight(): void {
  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;

    const updateHeight = () => {
      document.documentElement.style.setProperty("--app-height", `${viewport.height}px`);
    };

    updateHeight();
    viewport.addEventListener("resize", updateHeight);
    viewport.addEventListener("scroll", updateHeight);
    return () => {
      viewport.removeEventListener("resize", updateHeight);
      viewport.removeEventListener("scroll", updateHeight);
    };
  }, []);
}
