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
const SRC_DIR = fileURLToPath(new URL("..", import.meta.url));

const DEFINITION = /(--[a-zA-Z0-9-]+)\s*:/g;
const REFERENCE = /var\(\s*(--[a-zA-Z0-9-]+)\s*(,)?/g;

function collectFiles(dir: string, matches: (name: string) => boolean): string[] {
  const found: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) found.push(...collectFiles(full, matches));
    else if (matches(entry.name)) found.push(full);
  }
  return found;
}

const toRelative = (from: string, file: string) => path.relative(from, file).replace(/\\/g, "/");

const sources = collectFiles(APP_DIR, (name) => name.endsWith(".css"))
  .sort()
  .map((file) => ({
    file: toRelative(APP_DIR, file),
    css: fs.readFileSync(file, "utf8").replace(/\/\*[\s\S]*?\*\//g, ""),
  }));

const definedTokens = new Set<string>();
for (const { css } of sources) {
  for (const match of css.matchAll(DEFINITION)) definedTokens.add(match[1]);
}

/**
 * Custom properties that are intentionally referenced without being defined:
 * they are written from JavaScript at runtime. Keep this list short and
 * justified — every entry is a hole in the check below.
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
const RAW_COLOUR_BUDGET = 13;

/**
 * Component sources hold zero raw colours: CSS custom properties cannot reach
 * WebGL, so the three.js material colours in this file are JS constants and
 * the file is exempt.
 */
const CANVAS_COLOUR_FILES = new Set(["components/dice/DiceCanvas.tsx"]);

describe("stylesheet invariants", () => {
  it("every var() reference in CSS resolves to a defined custom property", () => {
    const dangling: string[] = [];
    for (const { file, css } of sources) {
      for (const match of css.matchAll(REFERENCE)) {
        if (definedTokens.has(match[1]) || DEFINED_AT_RUNTIME.has(match[1])) continue;
        dangling.push(`${match[1]}  referenced in ${file}${match[2] ? " (has fallback)" : ""}`);
      }
    }

    expect([...new Set(dangling)].sort()).toEqual([]);
  });

  it("every var() reference in TSX resolves to a defined custom property", () => {
    // Renaming a token in CSS silently breaks components that reference it from
    // an inline style or an SVG presentation attribute.
    const componentFiles = collectFiles(
      SRC_DIR,
      (name) => /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name),
    );

    const dangling: string[] = [];
    for (const file of componentFiles) {
      const text = fs.readFileSync(file, "utf8");
      for (const match of text.matchAll(REFERENCE)) {
        if (definedTokens.has(match[1]) || DEFINED_AT_RUNTIME.has(match[1])) continue;
        const line = text.slice(0, match.index).split("\n").length;
        dangling.push(`${match[1]}  referenced in ${toRelative(SRC_DIR, file)}:${line}`);
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

  it("keeps raw colours out of component sources", () => {
    const offenders: string[] = [];
    const componentFiles = collectFiles(
      SRC_DIR,
      (name) => /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name),
    );

    for (const file of componentFiles) {
      if (CANVAS_COLOUR_FILES.has(toRelative(SRC_DIR, file))) continue;
      fs.readFileSync(file, "utf8").split("\n").forEach((line, index) => {
        if (/#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\(/.test(line)) {
          offenders.push(`${toRelative(SRC_DIR, file)}:${index + 1}  ${line.trim().slice(0, 64)}`);
        }
      });
    }

    expect(offenders, `component sources hold raw colours:\n${offenders.join("\n")}`).toEqual([]);
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
