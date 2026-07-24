"use client";

import type { SVGProps } from "react";

export type LudusLogoLoaderProps = {
  loading?: boolean;
  size?: "sm" | "md" | "lg";
  className?: string;
  label?: string;
};

const guidePaths: Array<{ letter: string; path: string }> = [
  { letter: "L", path: "M90 72V330H260" },
  { letter: "U", path: "M350 76V245C350 308 380 334 430 334C480 334 510 308 510 245V76" },
  { letter: "D", path: "M620 76V330M620 76H700C798 76 842 126 842 203C842 280 798 330 700 330H620" },
  { letter: "U", path: "M936 76V245C936 308 966 334 1016 334C1066 334 1096 308 1096 245V76" },
  { letter: "S", path: "M1372 108C1345 82 1308 70 1266 74C1218 79 1187 104 1187 139C1187 184 1229 194 1274 204C1320 214 1364 227 1364 274C1364 316 1325 338 1273 338C1224 338 1187 322 1162 296" },
];

function GuidePath({ path }: { path: string }) {
  return <path d={path} pathLength="1" vectorEffect="non-scaling-stroke" />;
}

function LogoArt(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...props} className="ludus-logo-loader__art" viewBox="0 0 1478 406" focusable="false">
      <g className="ludus-logo-loader__guides" aria-hidden="true">
        {guidePaths.map(({ letter, path }, index) => (
          <g key={`${letter}-${index}`} data-letter={letter} className={`ludus-logo-loader__letter ludus-logo-loader__letter--${index + 1}`}>
            <GuidePath path={path} />
          </g>
        ))}
      </g>
      <image className="ludus-logo-loader__fill" href="/logo.svg" x="0" y="0" width="1478" height="406" preserveAspectRatio="xMidYMid meet" />
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

export { guidePaths };
