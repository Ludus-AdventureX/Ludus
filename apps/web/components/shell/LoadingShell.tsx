"use client";

import { useEffect, useState } from "react";

import { LudusLoadingOverlay } from "@/components/brand/LudusLoadingOverlay";

import { DecisionShell } from "./DecisionShell";

export function LoadingShell() {
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const timer = window.setTimeout(() => setLoading(false), 3000);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <>
      <DecisionShell />
      <LudusLoadingOverlay loading={loading} />
    </>
  );
}
