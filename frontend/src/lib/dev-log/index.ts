/** Canonical development history lives with the project documentation. */
import entries from "../../../../docs/dev-log/entries.json";
import type { DevLogEntry } from "./types";

export type { DevLogEntry } from "./types";
export const devLogEntries: DevLogEntry[] = entries;
