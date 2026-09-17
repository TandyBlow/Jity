import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { DiceDemo } from "@/components/dice-demo/DiceDemo";
import { diceDemoEnabled } from "@/lib/devFlags";

export const metadata: Metadata = {
  title: "骰子判定演示 | Jity",
  description: "Jity dice check demo",
};

export default function DiceDemoPage() {
  if (!diceDemoEnabled()) {
    notFound();
  }

  return <DiceDemo />;
}
