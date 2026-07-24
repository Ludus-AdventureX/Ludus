"use client";

import { useState } from "react";

import { LudusLogoLoader } from "./LudusLogoLoader";

type LudusLoadingOverlayProps = {
  loading: boolean;
  onExited?: () => void;
};

export function LudusLoadingOverlay({ loading, onExited }: LudusLoadingOverlayProps) {
  const [visible, setVisible] = useState(true);

  if (!visible) return null;

  return (
    <div
      className="ludus-loading-overlay"
      data-loading={String(loading)}
      onAnimationEnd={() => {
        if (!loading) {
          setVisible(false);
          onExited?.();
        }
      }}
    >
      <LudusLogoLoader loading={loading} size="lg" />
    </div>
  );
}
