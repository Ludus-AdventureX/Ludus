import type { Metadata } from "next";

import { SimulationDemoPanel } from "@/components/demo/SimulationDemoPanel";

export const metadata: Metadata = {
  title: "Simulation Demo · Technical Alpha · Ludus",
  description:
    "Technical Alpha demo: run a preset simulation fixture against the same-origin /api and replay the persisted result.",
};

export default function DemoPage() {
  return <SimulationDemoPanel />;
}
