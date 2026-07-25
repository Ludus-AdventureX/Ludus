import type { Metadata } from "next";

import { SimulationDemoPanel } from "@/components/demo/SimulationDemoPanel";

export const metadata: Metadata = {
  title: "Simulation Demo · Technical Alpha · Ludus",
  description:
    "Guest Technical Alpha demo: auto-create/restore a guest session, run a preset simulation fixture, and replay the persisted result.",
};

export default function DemoPage() {
  return <SimulationDemoPanel />;
}
