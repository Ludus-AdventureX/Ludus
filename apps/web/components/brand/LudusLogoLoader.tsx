"use client";

import type { SVGProps } from "react";

export type LudusLogoLoaderProps = {
  loading?: boolean;
  size?: "sm" | "md" | "lg";
  className?: string;
  label?: string;
};

const letters = ["L", "U", "D", "U", "S"] as const;

function LogoArt(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...props} className="ludus-logo-loader__art" viewBox="0 0 1478 406" focusable="false">
      <g className="ludus-logo-loader__letters" aria-hidden="true">
        {letters.map((letter, index) => <text key={`${letter}-${index}`} data-letter={letter} className={`ludus-logo-loader__letter ludus-logo-loader__letter--${index + 1}`} x={6 + index * 290} y="285">{letter}</text>)}
      </g>
    </svg>
  );
}

export function LudusLogoLoader({ loading = true, size = "md", className = "", label = "Loading Ludus" }: LudusLogoLoaderProps) {
  return (
    <span
      className={`ludus-logo-loader ludus-logo-loader--${size} ${className}`.trim()}
      role="status"
      aria-label={label}
      data-loading={String(loading)}
    >
      <LogoArt />
    </span>
  );
}

export { letters };
