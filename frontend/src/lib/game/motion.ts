/**
 * One place for the "should this animate?" question, shared by the typewriter
 * and the action-gate track. Both client-side animations answer to the same
 * switches so a user (or a test) never sees one on while the other is off.
 */

/** Automation override written by the e2e fixtures. */
export const MOTION_SUPPRESS_KEY = "jity_typewriter";

export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** `?typing=off` or the localStorage flag: tests and debugging want it all off. */
export function automationSuppressed(): boolean {
  if (typeof window === "undefined") return true;
  try {
    if (window.localStorage.getItem(MOTION_SUPPRESS_KEY) === "off") return true;
  } catch {
    // Private mode / disabled storage: fall through to the query param.
  }
  return new URLSearchParams(window.location.search).get("typing") === "off";
}

export function animationsSuppressed(): boolean {
  return prefersReducedMotion() || automationSuppressed();
}
