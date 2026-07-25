import Link from "next/link";

import { DecisionShell } from "@/components/shell/DecisionShell";

export default function Home() {
  return (
    <>
      <DecisionShell />
      <nav
        aria-label="Technical Alpha demo entry"
        className="fixed bottom-4 right-4 z-50 sm:bottom-6 sm:right-6"
      >
        <Link
          href="/demo"
          className="inline-flex items-center gap-2 rounded-full border border-neutral-300 bg-white px-4 py-2 text-sm font-semibold text-neutral-900 shadow-sm hover:border-neutral-400"
        >
          <span aria-hidden="true">▸</span>
          <span>Guest Simulation Demo</span>
          <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-900">
            Alpha
          </span>
        </Link>
      </nav>
    </>
  );
}
