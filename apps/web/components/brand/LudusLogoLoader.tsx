"use client";

import type { SVGProps } from "react";

export type LudusLogoLoaderProps = {
  loading?: boolean;
  size?: "sm" | "md" | "lg";
  className?: string;
  label?: string;
};

const letterSegments = [
  ["L", 0, 296], ["U", 296, 592], ["D", 592, 888], ["U", 888, 1184], ["S", 1184, 1478],
] as const;

function LogoArt(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...props} className="ludus-logo-loader__art" viewBox="0 0 1478 406" focusable="false">
      <g className="ludus-logo-loader__segments" aria-hidden="true">
        {letterSegments.map(([letter, start, end], index) => (
          <g key={`${letter}-${index}`} data-letter={letter} className={`ludus-logo-loader__segment ludus-logo-loader__segment--${index + 1}`}>
            <clipPath id={`ludus-loader-clip-${index + 1}`}><rect x={start} y="0" width={end - start} height="406" /></clipPath>
            <image href="/logo.svg" x="0" y="0" width="1478" height="406" clipPath={`url(#ludus-loader-clip-${index + 1})`} preserveAspectRatio="xMidYMid meet" />
            <line className="ludus-logo-loader__tracer" x1={start + 3} y1="32" x2={start + 3} y2="374" />
          </g>
        ))}
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

export { letterSegments };
