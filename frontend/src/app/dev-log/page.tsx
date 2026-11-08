import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { DevLogView } from "./DevLogView";
import { devLogEntries } from "@/lib/dev-log";

export const metadata: Metadata = {
  title: "开发日志 | Jity",
  description: "Jity internal development changelog",
};

export default function DevLogPage() {
  const isDevLogEnabled = process.env.ENABLE_DEV_LOG !== "false";

  if (!isDevLogEnabled) {
    notFound();
  }

  return <DevLogView entries={devLogEntries} />;
}
