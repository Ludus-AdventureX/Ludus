/** @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";

import { createElement } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import { ConnectorSettings } from "../components/shell/ConnectorSettings";

afterEach(() => {
  cleanup();
});

const WS = "ws-connector-test";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function stubFetch(handlers: Record<string, () => Response>): typeof fetch {
  return vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    for (const [pattern, handler] of Object.entries(handlers)) {
      if (path.includes(pattern)) return handler();
    }
    return jsonResponse(404, { ok: false });
  }) as unknown as typeof fetch;
}

const CATALOG = {
  ok: true,
  data: {
    writable: true,
    items: [
      { provider: "exa", label: "Exa", kind: "search", hint: "默认网络检索" },
      { provider: "model", label: "自定义模型", kind: "model", hint: "OpenAI-compatible endpoint" },
      { provider: "mcp", label: "MCP 工具服务器", kind: "mcp", hint: "HTTP/SSE MCP Server" },
    ],
  },
};

describe("ConnectorSettings", () => {
  test("renders catalog sections with masked connector states, never the key", async () => {
    vi.stubGlobal(
      "fetch",
      stubFetch({
        "/connectors/catalog": () => jsonResponse(200, CATALOG),
        "/connectors": () =>
          jsonResponse(200, {
            ok: true,
            data: {
              items: [
                { connectorId: "c1", provider: "exa", label: "Exa", kind: "search", mask: "sk-****abcd", status: "available", createdAt: null, lastCheckedAt: null },
              ],
            },
          }),
      }),
    );
    render(createElement(ConnectorSettings, { workspaceId: WS, onClose: vi.fn() }));
    await screen.findByText("检索连接器");
    expect(screen.getByText("Exa")).toBeInTheDocument();
    expect(screen.getByText("可用")).toBeInTheDocument();
    // Mask only — the real key never renders.
    expect(screen.getByText(/sk-\*\*\*\*abcd/)).toBeInTheDocument();
    expect(screen.queryByText(/secret-key-value/)).not.toBeInTheDocument();
  });

  test("inline API key input carries an accessible name", async () => {
    vi.stubGlobal(
      "fetch",
      stubFetch({
        "/connectors/catalog": () => jsonResponse(200, CATALOG),
        "/connectors": () => jsonResponse(200, { ok: true, data: { items: [] } }),
      }),
    );
    render(createElement(ConnectorSettings, { workspaceId: WS, onClose: vi.fn() }));
    await screen.findByText("检索连接器");
    fireEvent.click(screen.getByRole("button", { name: "添加" }));
    const keyInput = await screen.findByPlaceholderText("粘贴 API Key");
    expect(keyInput).toHaveAccessibleName("API Key");
    expect(keyInput).toHaveAttribute("type", "password");
  });

  test("Esc closes the modal", async () => {
    vi.stubGlobal(
      "fetch",
      stubFetch({
        "/connectors/catalog": () => jsonResponse(200, CATALOG),
        "/connectors": () => jsonResponse(200, { ok: true, data: { items: [] } }),
      }),
    );
    const onClose = vi.fn();
    render(createElement(ConnectorSettings, { workspaceId: WS, onClose }));
    await screen.findByText("检索连接器");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
