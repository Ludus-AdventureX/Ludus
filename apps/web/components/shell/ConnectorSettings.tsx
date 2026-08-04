"use client";

import { useCallback, useEffect, useState } from "react";

// Connector settings modal: BYOK key management for search connectors,
// user-selected model endpoints, and MCP tool servers.
// Layout referenced from open-webui's settings modal (sidebar sections +
// content pane); no code copied (license boundary). Look V7: square corners,
// hairline borders, semantic tokens. No secrets shown beyond the mask.

type CatalogItem = { provider: string; label: string; kind: string; hint: string };
type ConnectorView = {
  connectorId: string;
  provider: string;
  label: string;
  kind: string;
  mask: string;
  status: string;
  createdAt: string | null;
  lastCheckedAt: string | null;
  config?: Record<string, string>;
};
type McpTool = { name: string; description: string };

const STATUS_LABELS: Record<string, string> = {
  available: "可用",
  missing_credentials: "未配置",
  invalid_credentials: "凭证无效",
  rate_limited: "限流中",
  quota_exhausted: "配额耗尽",
  provider_error: "提供商异常",
  disabled: "已禁用",
};

const SECTIONS = [
  { id: "search", label: "检索连接器", hint: "网络搜索与网页抓取" },
  { id: "model", label: "自定义模型", hint: "OpenAI-compatible endpoint" },
  { id: "mcp", label: "MCP 工具", hint: "外部工具服务器" },
] as const;

type SectionId = (typeof SECTIONS)[number]["id"];

export type ConnectorSettingsProps = {
  workspaceId: string;
  onClose: () => void;
};

export function ConnectorSettings({ workspaceId, onClose }: ConnectorSettingsProps) {
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [connectors, setConnectors] = useState<ConnectorView[]>([]);
  const [writable, setWritable] = useState(false);
  const [section, setSection] = useState<SectionId>("search");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  // search section: which provider's key input is open
  const [editProvider, setEditProvider] = useState("");
  const [inputKey, setInputKey] = useState("");
  // model section
  const [inputBaseUrl, setInputBaseUrl] = useState("");
  const [inputModelName, setInputModelName] = useState("");
  const [inputModelKey, setInputModelKey] = useState("");
  // mcp section
  const [inputServerUrl, setInputServerUrl] = useState("");
  const [inputServerName, setInputServerName] = useState("");
  const [inputAuthType, setInputAuthType] = useState<"none" | "bearer">("none");
  const [inputMcpKey, setInputMcpKey] = useState("");
  const [mcpTools, setMcpTools] = useState<McpTool[] | null>(null);

  const base = `/api/workspaces/${encodeURIComponent(workspaceId)}`;

  const loadAll = useCallback(async () => {
    try {
      const [catRes, listRes] = await Promise.all([
        fetch(`${base}/connectors/catalog`, { credentials: "include" }),
        fetch(`${base}/connectors`, { credentials: "include" }),
      ]);
      if (catRes.ok) {
        const catBody = (await catRes.json()) as { data?: { items?: CatalogItem[]; writable?: boolean } };
        setCatalog(catBody.data?.items ?? []);
        setWritable(catBody.data?.writable ?? false);
      }
      if (listRes.ok) {
        const listBody = (await listRes.json()) as { data?: { items?: ConnectorView[] } };
        setConnectors(listBody.data?.items ?? []);
      }
    } catch { /* graceful */ }
  }, [base]);

  useEffect(() => { void loadAll(); }, [loadAll]);

  // Esc closes the modal.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const csrf = async (): Promise<string> => {
    const r = await fetch("/api/auth/csrf", { credentials: "include" });
    const b = (await r.json()) as { data?: { csrfToken?: string } };
    return b.data?.csrfToken ?? "";
  };

  const upsert = async (payload: Record<string, string>) => {
    setBusy(true);
    setNotice("");
    try {
      const token = await csrf();
      const res = await fetch(`${base}/connectors`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        setNotice("已保存");
        setEditProvider("");
        setInputKey("");
        setInputBaseUrl(""); setInputModelName(""); setInputModelKey("");
        setInputServerUrl(""); setInputServerName(""); setInputMcpKey(""); setInputAuthType("none");
        await loadAll();
        return true;
      }
      const err = (await res.json().catch(() => null)) as { error?: { message?: string } } | null;
      setNotice(err?.error?.message ?? "保存失败");
      return false;
    } catch {
      setNotice("网络错误");
      return false;
    } finally {
      setBusy(false);
    }
  };

  const testConn = async (connectorId: string) => {
    setBusy(true);
    setNotice("");
    try {
      const token = await csrf();
      await fetch(`${base}/connectors/${encodeURIComponent(connectorId)}/test`, {
        method: "POST", credentials: "include", headers: { "X-CSRF-Token": token },
      });
      await loadAll();
    } catch { /* graceful */ }
    finally { setBusy(false); }
  };

  const deleteConn = async (connectorId: string) => {
    setBusy(true);
    try {
      const token = await csrf();
      await fetch(`${base}/connectors/${encodeURIComponent(connectorId)}`, {
        method: "DELETE", credentials: "include", headers: { "X-CSRF-Token": token },
      });
      setMcpTools(null);
      await loadAll();
    } catch { /* graceful */ }
    finally { setBusy(false); }
  };

  const discoverTools = async (connectorId: string) => {
    setBusy(true);
    setMcpTools(null);
    try {
      const res = await fetch(`${base}/connectors/${encodeURIComponent(connectorId)}/tools`, { credentials: "include" });
      if (res.ok) {
        const body = (await res.json()) as { data?: { items?: McpTool[]; error?: string } };
        setMcpTools(body.data?.items ?? []);
        if (body.data?.error) setNotice(`工具发现失败：${body.data.error}`);
      }
    } catch { /* graceful */ }
    finally { setBusy(false); }
  };

  const searchItems = catalog.filter((c) => c.kind === "search" || c.kind === "fetch");
  const modelConn = connectors.find((c) => c.provider === "model");
  const mcpConn = connectors.find((c) => c.provider === "mcp");

  const statusDot = (status: string | undefined) => (
    <span className="connector-dot" data-dot={status ?? "none"} aria-hidden />
  );

  return (
    <div className="connector-overlay" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="connector-modal" role="dialog" aria-modal="true" aria-label="连接器设置">
        <div className="connector-modal-header">
          <span className="connector-modal-title">连接器设置</span>
          <button type="button" className="text-action" onClick={onClose}>关闭</button>
        </div>

        <div className="connector-modal-body">
          <nav className="connector-nav" aria-label="设置分区">
            {SECTIONS.map((s) => (
              <button
                key={s.id}
                type="button"
                className="connector-nav-item"
                data-active={section === s.id}
                onClick={() => { setSection(s.id); setNotice(""); }}
              >
                <b>{s.label}</b>
                <small>{s.hint}</small>
              </button>
            ))}
          </nav>

          <div className="connector-content">
            {section === "search" && (
              <div className="connector-section">
                {searchItems.map((item) => {
                  const conn = connectors.find((c) => c.provider === item.provider);
                  const editing = editProvider === item.provider;
                  return (
                    <div key={item.provider} className="connector-row">
                      <div className="connector-row-main">
                        {statusDot(conn?.status)}
                        <div className="connector-row-id">
                          <b>{item.label}</b>
                          <small>{item.hint}</small>
                        </div>
                        {conn ? (
                          <span className="connector-mask">{conn.mask}</span>
                        ) : (
                          <span className="connector-status">未配置</span>
                        )}
                        <div className="connector-row-actions">
                          {conn && (
                            <>
                              <button type="button" disabled={busy} onClick={() => void testConn(conn.connectorId)}>测试</button>
                              <button type="button" disabled={busy} onClick={() => void deleteConn(conn.connectorId)}>删除</button>
                            </>
                          )}
                          {writable && (
                            <button type="button" disabled={busy} onClick={() => { setEditProvider(editing ? "" : item.provider); setInputKey(""); }}>
                              {conn ? "更换" : "添加"}
                            </button>
                          )}
                        </div>
                      </div>
                      {conn && <span className="connector-substatus">{STATUS_LABELS[conn.status] ?? conn.status}</span>}
                      {editing && (
                        <div className="connector-inline-form">
                          <input
                            type="password"
                            placeholder="粘贴 API Key"
                            aria-label="API Key"
                            value={inputKey}
                            onChange={(e) => setInputKey(e.target.value)}
                            disabled={busy}
                            autoFocus
                          />
                          <button
                            type="button"
                            className="primary-action small"
                            disabled={busy || !inputKey.trim()}
                            onClick={() => void upsert({ provider: item.provider, apiKey: inputKey.trim() })}
                          >
                            <span>保存</span>
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {section === "model" && (
              <div className="connector-section">
                {modelConn ? (
                  <div className="connector-row">
                    <div className="connector-row-main">
                      {statusDot(modelConn.status)}
                      <div className="connector-row-id">
                        <b>{modelConn.config?.model_name ?? "自定义模型"}</b>
                        <small>{modelConn.config?.base_url}</small>
                      </div>
                      <span className="connector-mask">{modelConn.mask}</span>
                      <div className="connector-row-actions">
                        <button type="button" disabled={busy} onClick={() => void testConn(modelConn.connectorId)}>测试</button>
                        <button type="button" disabled={busy} onClick={() => void deleteConn(modelConn.connectorId)}>删除</button>
                      </div>
                    </div>
                    <span className="connector-substatus">
                      {STATUS_LABELS[modelConn.status] ?? modelConn.status} · 对话与深度分析将优先使用此模型
                    </span>
                  </div>
                ) : (
                  <p className="connector-empty">未配置自定义模型，系统使用默认模型（DeepSeek）。</p>
                )}

                {writable && (
                  <div className="connector-form">
                    <span className="connector-form-title">{modelConn ? "更换模型" : "添加模型"}</span>
                    <label className="connector-field">
                      <span>Base URL</span>
                      <input
                        type="url"
                        placeholder="https://api.deepseek.com/v1"
                        value={inputBaseUrl}
                        onChange={(e) => setInputBaseUrl(e.target.value)}
                        disabled={busy}
                      />
                    </label>
                    <label className="connector-field">
                      <span>Model Name</span>
                      <input
                        type="text"
                        placeholder="deepseek-chat / gpt-4o / kimi-k2 …"
                        value={inputModelName}
                        onChange={(e) => setInputModelName(e.target.value)}
                        disabled={busy}
                      />
                    </label>
                    <label className="connector-field">
                      <span>API Key</span>
                      <input
                        type="password"
                        placeholder="sk-…"
                        value={inputModelKey}
                        onChange={(e) => setInputModelKey(e.target.value)}
                        disabled={busy}
                      />
                    </label>
                    <button
                      type="button"
                      className="primary-action small"
                      disabled={busy || !inputBaseUrl.trim() || !inputModelName.trim() || !inputModelKey.trim()}
                      onClick={() => void upsert({
                        provider: "model",
                        apiKey: inputModelKey.trim(),
                        baseUrl: inputBaseUrl.trim(),
                        modelName: inputModelName.trim(),
                      })}
                    >
                      <span>保存</span>
                    </button>
                  </div>
                )}
              </div>
            )}

            {section === "mcp" && (
              <div className="connector-section">
                {mcpConn ? (
                  <div className="connector-row">
                    <div className="connector-row-main">
                      {statusDot(mcpConn.status)}
                      <div className="connector-row-id">
                        <b>{mcpConn.config?.name ?? "MCP Server"}</b>
                        <small>{mcpConn.config?.url}</small>
                      </div>
                      <div className="connector-row-actions">
                        <button type="button" disabled={busy} onClick={() => void testConn(mcpConn.connectorId)}>测试</button>
                        <button type="button" disabled={busy} onClick={() => void discoverTools(mcpConn.connectorId)}>工具</button>
                        <button type="button" disabled={busy} onClick={() => void deleteConn(mcpConn.connectorId)}>删除</button>
                      </div>
                    </div>
                    <span className="connector-substatus">{STATUS_LABELS[mcpConn.status] ?? mcpConn.status}</span>
                    {mcpTools !== null && (
                      <div className="connector-tools">
                        {mcpTools.length === 0 ? (
                          <span className="connector-substatus">未发现工具</span>
                        ) : (
                          mcpTools.map((t) => (
                            <div key={t.name} className="connector-tool">
                              <b>{t.name}</b>
                              {t.description && <small>{t.description}</small>}
                            </div>
                          ))
                        )}
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="connector-empty">未配置 MCP 工具服务器（HTTP/SSE，只读工具）。</p>
                )}

                {writable && (
                  <div className="connector-form">
                    <span className="connector-form-title">{mcpConn ? "更换服务器" : "添加服务器"}</span>
                    <label className="connector-field">
                      <span>Server URL</span>
                      <input
                        type="url"
                        placeholder="https://mcp.example.com/sse"
                        value={inputServerUrl}
                        onChange={(e) => setInputServerUrl(e.target.value)}
                        disabled={busy}
                      />
                    </label>
                    <label className="connector-field">
                      <span>名称</span>
                      <input
                        type="text"
                        placeholder="MCP Server"
                        value={inputServerName}
                        onChange={(e) => setInputServerName(e.target.value)}
                        disabled={busy}
                      />
                    </label>
                    <label className="connector-field">
                      <span>认证方式</span>
                      <select
                        value={inputAuthType}
                        onChange={(e) => setInputAuthType(e.target.value as "none" | "bearer")}
                        disabled={busy}
                      >
                        <option value="none">无认证</option>
                        <option value="bearer">Bearer Token</option>
                      </select>
                    </label>
                    {inputAuthType === "bearer" && (
                      <label className="connector-field">
                        <span>Bearer Token</span>
                        <input
                          type="password"
                          placeholder="Token"
                          value={inputMcpKey}
                          onChange={(e) => setInputMcpKey(e.target.value)}
                          disabled={busy}
                        />
                      </label>
                    )}
                    <button
                      type="button"
                      className="primary-action small"
                      disabled={busy || !inputServerUrl.trim() || (inputAuthType === "bearer" && !inputMcpKey.trim())}
                      onClick={() => void upsert({
                        provider: "mcp",
                        serverUrl: inputServerUrl.trim(),
                        serverName: inputServerName.trim() || "MCP Server",
                        authType: inputAuthType,
                        ...(inputAuthType === "bearer" ? { apiKey: inputMcpKey.trim() } : {}),
                      })}
                    >
                      <span>保存</span>
                    </button>
                  </div>
                )}
              </div>
            )}

            {!writable && (
              <p className="connector-notice">加密主密钥未配置，暂无法保存连接器凭证。</p>
            )}
            {notice && <p className="connector-notice" role="status">{notice}</p>}
          </div>
        </div>
      </div>
    </div>
  );
}
