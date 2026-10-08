import type { Wllama } from "@wllama/wllama";

type WllamaModule = typeof import("@wllama/wllama");

/**
 * The wllama npm package resolves to its TypeScript source under webpack
 * (its "main" points at a missing index.js), so the benchmark loads the
 * built, self-contained ESM bundle from public/ at runtime instead of
 * importing the package at build time. Types still come from the package,
 * which is compile-time only. The Function indirection keeps bundlers from
 * statically analyzing the specifier.
 */
let libllamaVersion = "";

/**
 * The libllama build string, captured when the module loads. Empty until the
 * first createWllama() succeeds.
 */
export function getLibllamaVersion(): string {
  return libllamaVersion;
}

export async function createWllama(): Promise<Wllama> {
  const dynamicImport = new Function(
    "specifier",
    "return import(specifier)",
  ) as (specifier: string) => Promise<WllamaModule>;
  const wllamaModule = await dynamicImport("/wllama/index.min.js");
  libllamaVersion = wllamaModule.Wllama.getLibllamaVersion();
  return new wllamaModule.Wllama(
    { default: "/wasm/wllama.wasm" },
    { logger: { ...console, debug: () => undefined } },
  );
}
