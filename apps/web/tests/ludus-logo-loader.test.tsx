/** @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
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
});

describe("LudusLoadingOverlay", () => {
  test("renders an exiting state when loading stops", () => {
    const onExited = vi.fn();
    const { container, rerender } = render(<LudusLoadingOverlay loading onExited={onExited} />);

    rerender(<LudusLoadingOverlay loading={false} onExited={onExited} />);

    expect(container.querySelector(".ludus-loading-overlay")).toHaveAttribute("data-loading", "false");
    expect(onExited).not.toHaveBeenCalled();
  });
});
