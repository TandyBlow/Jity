import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

/**
 * Static invariants for the stylesheets under `src/app/`.
 *
 * These read the CSS as text rather than rendering it. They exist to make the
 * token refactor verifiable: before the split they are red, after it they are
 * green, and they stay green afterwards to catch regressions.
 *
 * The file list is discovered recursively, so moving rules into
 * `src/app/styles/**` needs no change here.
 */

const APP_DIR = fileURLToPath(new URL(".", import.meta.url));

function collectCssFiles(dir: string): string[] {
  const found: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) found.push(...collectCssFiles(full));
    else if (entry.name.endsWith(".css")) found.push(full);
  }
  return found;
}

const sources = collectCssFiles(APP_DIR)
  .sort()
  .map((file) => ({
    file: path.relative(APP_DIR, file).replace(/\\/g, "/"),
    css: fs.readFileSync(file, "utf8").replace(/\/\*[\s\S]*?\*\//g, ""),
  }));

const DEFINITION = /(--[a-zA-Z0-9-]+)\s*:/g;
const REFERENCE = /var\(\s*(--[a-zA-Z0-9-]+)\s*(,)?/g;

/**
 * Custom properties that are intentionally referenced without being defined:
 * either they are supplied from JavaScript at runtime, or the reference carries
 * its own fallback. Keep this empty unless there is a real reason.
 */
const DEFINED_AT_RUNTIME = new Set<string>([
  // Written by app/page.tsx from the pointer-parallax handler.
  "--background-shift-x",
  "--background-shift-y",
  // Written by app/page.tsx from the scene background URL.
  "--scene-background",
]);

/**
 * Ratchet for hardcoded colours outside custom-property definitions, counted
 * per line (one line may hold several literals).
 *
 * Lower this every time the refactor removes some, never raise it. Reaching 0
 * is the goal; until then it still fails if a *new* literal is introduced.
 */
const RAW_COLOUR_BUDGET = 111;

describe("stylesheet invariants", () => {
  it("every var() reference resolves to a defined custom property", () => {
    const defined = new Set<string>();
    for (const { css } of sources) {
      for (const match of css.matchAll(DEFINITION)) defined.add(match[1]);
    }

    const dangling: string[] = [];
    for (const { file, css } of sources) {
      for (const match of css.matchAll(REFERENCE)) {
        const name = match[1];
        if (defined.has(name) || DEFINED_AT_RUNTIME.has(name)) continue;
        dangling.push(`${name}  referenced in ${file}${match[2] ? " (has fallback)" : ""}`);
      }
    }

    expect([...new Set(dangling)].sort()).toEqual([]);
  });

  it("keeps hardcoded colours within the budget", () => {
    const offenders: string[] = [];
    for (const { file, css } of sources) {
      css.split("\n").forEach((line, index) => {
        // A custom-property definition IS the place for a literal.
        if (/^\s*--[a-zA-Z0-9-]+\s*:/.test(line)) return;
        if (/#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\(/.test(line)) {
          offenders.push(`${file}:${index + 1}  ${line.trim().slice(0, 64)}`);
        }
      });
    }

    const preview = offenders.slice(0, 6).join("\n");
    expect(
      offenders.length,
      `${offenders.length} 处裸色值，预算 ${RAW_COLOUR_BUDGET}。前几处：\n${preview}`,
    ).toBeLessThanOrEqual(RAW_COLOUR_BUDGET);
  });

  it("does not declare the same @media condition twice in one file", () => {
    const duplicates: string[] = [];
    for (const { file, css } of sources) {
      const seen = new Map<string, number>();
      for (const match of css.matchAll(/@media\s*([^{]+)\{/g)) {
        const condition = match[1].trim().replace(/\s+/g, " ");
        const count = (seen.get(condition) ?? 0) + 1;
        seen.set(condition, count);
        if (count === 2) duplicates.push(`${file}: @media ${condition}`);
      }
    }

    expect(duplicates).toEqual([]);
  });

  it("keeps @keyframes definitions and animation references in sync", () => {
    // Tokens that can appear in the `animation` shorthand but are not names.
    const NOT_A_NAME = new Set([
      "infinite", "forwards", "backwards", "both", "none", "normal", "reverse",
      "alternate", "alternate-reverse", "running", "paused", "initial", "inherit",
      "unset", "ease", "ease-in", "ease-out", "ease-in-out", "linear",
      "step-start", "step-end",
    ]);

    const defined = new Set<string>();
    const referenced = new Set<string>();

    for (const { css } of sources) {
      for (const match of css.matchAll(/@keyframes\s+([\w-]+)/g)) defined.add(match[1]);

      for (const match of css.matchAll(/animation(?:-name)?\s*:\s*([^;}]+)[;}]/g)) {
        // Drop timing functions first: their comma-separated arguments would
        // otherwise be split apart and read as animation names.
        const withoutFunctions = match[1].replace(/[\w-]+\([^)]*\)/g, " ");
        for (const token of withoutFunctions.split(/[\s,]+/)) {
          if (NOT_A_NAME.has(token)) continue;
          // Animation names are identifiers; this rejects durations and the
          // numeric fragments of anything left behind.
          if (!/^[a-zA-Z_][\w-]*$/.test(token)) continue;
          referenced.add(token);
        }
      }
    }

    const unused = [...defined].filter((name) => !referenced.has(name)).sort();
    const missing = [...referenced].filter((name) => !defined.has(name)).sort();

    expect({ unused, missing }).toEqual({ unused: [], missing: [] });
  });
});
