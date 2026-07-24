# Ludus Logo Loader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a left-to-right, letter-by-letter line-drawn Ludus Logo loader as a standalone SVG, reusable React component, and full-screen loading overlay.

**Architecture:** A standalone animated SVG owns the five hand-tuned guide paths and CSS timing. A client React component embeds the same geometry so it can stop cleanly after loading finishes, while a thin overlay component handles full-screen presentation and exit timing. Component tests validate semantics and state; browser screenshots validate the visual phases at desktop and mobile sizes.

**Tech Stack:** Next.js 15, React 19, TypeScript, CSS animations, inline SVG, Vitest, Testing Library, Playwright/browser inspection.

---

## File Map

- Create `apps/web/components/brand/LudusLogoLoader.tsx`: reusable loader and shared inline SVG geometry.
- Create `apps/web/components/brand/LudusLoadingOverlay.tsx`: full-screen wrapper and completion callback.
- Create `apps/web/components/brand/ludus-logo-loader.css`: sizing, drawing, resolve, breathing, exit, and reduced-motion rules.
- Create `apps/web/public/ludus-logo-loader.svg`: standalone self-animating asset.
- Create `apps/web/tests/ludus-logo-loader.test.tsx`: component states, semantics, and timing hooks.
- Modify `apps/web/app/globals.css`: import the loader stylesheet.
- Modify `apps/web/app/page.tsx`: mount the initial overlay in a demo-safe client boundary.

### Task 1: Define Loader Semantics With Failing Tests

**Files:**
- Create: `apps/web/tests/ludus-logo-loader.test.tsx`

- [ ] **Step 1: Write the failing component tests**

```tsx
/** @vitest-environment jsdom */
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { LudusLogoLoader } from "../components/brand/LudusLogoLoader";
import { LudusLoadingOverlay } from "../components/brand/LudusLoadingOverlay";

afterEach(cleanup);

describe("LudusLogoLoader", () => {
  test("renders five ordered drawing groups and an accessible status", () => {
    const { container } = render(<LudusLogoLoader label="Loading Ludus" />);
    expect(screen.getByRole("status", { name: "Loading Ludus" })).toBeInTheDocument();
    expect([...container.querySelectorAll("[data-letter]")].map((node) => node.getAttribute("data-letter")))
      .toEqual(["L", "U", "D", "U", "S"]);
  });

  test("marks the current cycle to finish when loading stops", () => {
    const { rerender } = render(<LudusLogoLoader loading />);
    rerender(<LudusLogoLoader loading={false} />);
    expect(screen.getByRole("status")).toHaveAttribute("data-loading", "false");
  });

  test("overlay exits after its animation and reports completion", () => {
    const onExited = vi.fn();
    const { container, rerender } = render(<LudusLoadingOverlay loading onExited={onExited} />);
    rerender(<LudusLoadingOverlay loading={false} onExited={onExited} />);
    fireEvent.animationEnd(container.querySelector(".ludus-loading-overlay")!, { animationName: "ludus-overlay-exit" });
    expect(onExited).toHaveBeenCalledOnce();
  });
});
```

- [ ] **Step 2: Run the focused test and verify red state**

Run: `pnpm --filter web test -- tests/ludus-logo-loader.test.tsx`

Expected: FAIL because both brand components do not exist.

- [ ] **Step 3: Commit the red test**

```bash
git add apps/web/tests/ludus-logo-loader.test.tsx
git commit -m "test: define Ludus logo loader behavior"
```

### Task 2: Build The Reusable Animated Logo

**Files:**
- Create: `apps/web/components/brand/LudusLogoLoader.tsx`
- Create: `apps/web/components/brand/ludus-logo-loader.css`
- Modify: `apps/web/app/globals.css`
- Test: `apps/web/tests/ludus-logo-loader.test.tsx`

- [ ] **Step 1: Implement the typed loader shell and five guide groups**

Create a client component with this public interface:

```tsx
export type LudusLogoLoaderProps = {
  loading?: boolean;
  size?: "sm" | "md" | "lg";
  className?: string;
  label?: string;
};

export function LudusLogoLoader({
  loading = true,
  size = "md",
  className = "",
  label = "Loading Ludus",
}: LudusLogoLoaderProps) {
  return (
    <span
      className={`ludus-logo-loader ludus-logo-loader--${size} ${className}`.trim()}
      role="status"
      aria-label={label}
      data-loading={String(loading)}
    >
      <svg className="ludus-logo-loader__art" viewBox="0 0 1478 406" aria-hidden="true">
        <g className="ludus-logo-loader__guides">
          <g data-letter="L" className="ludus-logo-loader__letter ludus-logo-loader__letter--1">
            <path d="M90 72V330H260" />
          </g>
          <g data-letter="U" className="ludus-logo-loader__letter ludus-logo-loader__letter--2">
            <path d="M350 76V245C350 308 380 334 430 334C480 334 510 308 510 245V76" />
          </g>
          <g data-letter="D" className="ludus-logo-loader__letter ludus-logo-loader__letter--3">
            <path d="M620 76V330M620 76H700C798 76 842 126 842 203C842 280 798 330 700 330H620" />
          </g>
          <g data-letter="U" className="ludus-logo-loader__letter ludus-logo-loader__letter--4">
            <path d="M936 76V245C936 308 966 334 1016 334C1066 334 1096 308 1096 245V76" />
          </g>
          <g data-letter="S" className="ludus-logo-loader__letter ludus-logo-loader__letter--5">
            <path d="M1372 108C1345 82 1308 70 1266 74C1218 79 1187 104 1187 139C1187 184 1229 194 1274 204C1320 214 1364 227 1364 274C1364 316 1325 338 1273 338C1224 338 1187 322 1162 296" />
          </g>
        </g>
        <image className="ludus-logo-loader__fill" href="/logo.svg" width="1478" height="406" />
      </svg>
    </span>
  );
}
```

Tune these concrete paths against the supplied artwork without changing their group order. Keep every guide inside its letter's visible bounds and use round line caps and joins.

- [ ] **Step 2: Add stable sizing and animation phases**

Define `sm`, `md`, and `lg` dimensions with a `1478 / 406` aspect ratio. Animate guide paths with dash offsets and delays `0ms`, `280ms`, `560ms`, `840ms`, and `1120ms`. Fade the supplied fill layer in after drawing, hold, breathe to opacity `.35`, restore, and reset at `4800ms`. When `data-loading="false"`, prevent another reset and retain the resolved fill.

- [ ] **Step 3: Add reduced-motion rules**

```css
@media (prefers-reduced-motion: reduce) {
  .ludus-logo-loader__guides { display: none; }
  .ludus-logo-loader__fill { animation: none; opacity: 1; }
}
```

- [ ] **Step 4: Import the focused stylesheet**

Add `@import "../components/brand/ludus-logo-loader.css";` to `apps/web/app/globals.css` after the Tailwind import.

- [ ] **Step 5: Run the focused tests**

Run: `pnpm --filter web test -- tests/ludus-logo-loader.test.tsx`

Expected: the first two tests PASS; the overlay import still fails until Task 3.

- [ ] **Step 6: Commit the reusable loader**

```bash
git add apps/web/components/brand/LudusLogoLoader.tsx apps/web/components/brand/ludus-logo-loader.css apps/web/app/globals.css
git commit -m "feat: add line-drawn Ludus logo loader"
```

### Task 3: Add Full-Screen Overlay And Initial Integration

**Files:**
- Create: `apps/web/components/brand/LudusLoadingOverlay.tsx`
- Modify: `apps/web/app/page.tsx`
- Test: `apps/web/tests/ludus-logo-loader.test.tsx`

- [ ] **Step 1: Implement overlay lifecycle**

```tsx
"use client";

import { useState } from "react";
import { LudusLogoLoader } from "./LudusLogoLoader";

export function LudusLoadingOverlay({ loading, onExited }: { loading: boolean; onExited?: () => void }) {
  const [visible, setVisible] = useState(true);
  if (!visible) return null;
  return (
    <div
      className="ludus-loading-overlay"
      data-loading={String(loading)}
      onAnimationEnd={(event) => {
        if (!loading && event.animationName === "ludus-overlay-exit") {
          setVisible(false);
          onExited?.();
        }
      }}
    >
      <LudusLogoLoader loading={loading} size="lg" />
    </div>
  );
}
```

- [ ] **Step 2: Add overlay styling**

Use `position: fixed; inset: 0; z-index: 1000; display: grid; place-items: center;` with the application's page background. Add pointer blocking while visible and a named `ludus-overlay-exit` opacity animation for `data-loading="false"`.

- [ ] **Step 3: Integrate a bounded initial-loading demonstration**

Move the page UI into a small client wrapper that starts `loading=true`, switches to `false` after the application-ready signal, and renders `<DecisionShell />` behind the overlay. For the current static shell, schedule `window.setTimeout(() => setLoading(false), 3000)` inside an effect and clear that timer during cleanup. This gives the initial animation an observable minimum display without tying it to nonexistent API work.

- [ ] **Step 4: Run the loader and existing accessibility tests**

Run: `pnpm --filter web test -- tests/ludus-logo-loader.test.tsx tests/decision-shell-accessibility.test.tsx`

Expected: PASS with no duplicate or obscured accessibility roles after the overlay exits.

- [ ] **Step 5: Commit overlay integration**

```bash
git add apps/web/components/brand/LudusLoadingOverlay.tsx apps/web/app/page.tsx apps/web/tests/ludus-logo-loader.test.tsx
git commit -m "feat: add initial Ludus loading overlay"
```

### Task 4: Produce The Standalone Animated SVG

**Files:**
- Create: `apps/web/public/ludus-logo-loader.svg`

- [ ] **Step 1: Create the standalone asset from the verified component geometry**

Use `viewBox="0 0 1478 406"`, a transparent root, the same five `data-letter` groups, and the same guide paths and delays as the React component. Inline the final supplied Logo paths rather than linking to another file so the asset remains standalone.

- [ ] **Step 2: Add SVG-local motion preferences**

Embed the drawing, resolve, hold, breathing, and reduced-motion CSS inside `<style>`. Under reduced motion, hide guide paths and display the final fill paths at opacity `1`.

- [ ] **Step 3: Validate XML and expected structure**

Run:

```bash
xmllint --noout apps/web/public/ludus-logo-loader.svg
rg -c 'data-letter=' apps/web/public/ludus-logo-loader.svg
```

Expected: XML validation succeeds and the count is `5`.

- [ ] **Step 4: Commit the asset**

```bash
git add apps/web/public/ludus-logo-loader.svg
git commit -m "feat: add standalone animated Ludus logo"
```

### Task 5: Verify Behavior And Visual Quality

**Files:**
- Modify only if verification exposes defects in the files created above.

- [ ] **Step 1: Run the full automated gate**

Run:

```bash
pnpm --filter web typecheck
pnpm --filter web lint
pnpm --filter web test
pnpm --filter web build
```

Expected: all commands exit `0`.

- [ ] **Step 2: Start the development server**

Run: `pnpm --filter web dev`

Expected: Next.js reports a local URL and serves the page without runtime errors.

- [ ] **Step 3: Inspect five animation phases in a browser**

At desktop `1440x900` and mobile `390x844`, inspect or capture the loader during L draw, mid-word draw, completed fill, dimmed breathing, and restored breathing. Confirm the canvas is nonblank, L/U/D/U/S appear in order, the final artwork does not jump, and nothing clips or overlaps.

- [ ] **Step 4: Inspect reduced motion**

Emulate `prefers-reduced-motion: reduce` and confirm the complete Logo is immediately visible with no drawing or breathing animation.

- [ ] **Step 5: Fix visual defects and repeat the complete gate**

Adjust only guide geometry, timing, stroke width, or responsive constraints. Re-run Step 1 and repeat both viewport checks until every acceptance condition passes.

- [ ] **Step 6: Commit verification fixes**

```bash
git add apps/web/components/brand apps/web/public/ludus-logo-loader.svg apps/web/app apps/web/tests/ludus-logo-loader.test.tsx
git commit -m "fix: polish Ludus loader motion and responsiveness"
```
