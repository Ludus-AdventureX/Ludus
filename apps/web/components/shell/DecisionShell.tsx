"use client";

import Image from "next/image";
import {
  Archive,
  Beaker,
  BookOpenText,
  CheckCircle2,
  ChevronRight,
  FileText,
  FolderOpen,
  Menu,
  Network,
  Palette,
  Plus,
  Scale,
  Sparkles,
  X,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

const workspaceOrder = ["workspace", "analysis", "report", "sandbox", "decision"] as const;
type WorkspaceId = (typeof workspaceOrder)[number];
type DrawerId = "project" | "theme" | null;

const workspaces: Record<
  WorkspaceId,
  { label: string; number: string; description: string; icon: typeof FolderOpen }
> = {
  workspace: {
    label: "工作台",
    number: "01",
    description: "界定问题与责任边界",
    icon: FolderOpen,
  },
  analysis: {
    label: "分析",
    number: "02",
    description: "授权方法并形成证据链",
    icon: Sparkles,
  },
  report: {
    label: "报告",
    number: "03",
    description: "审阅主张、引用与反方",
    icon: FileText,
  },
  sandbox: {
    label: "沙盘",
    number: "04",
    description: "检验脆弱条件与情景",
    icon: Network,
  },
  decision: {
    label: "决定",
    number: "05",
    description: "由人签署并承担责任",
    icon: Scale,
  },
};

const themes = [
  ["ink", "水墨黑白", "克制、清晰、默认"],
  ["ledger", "墨纸酒红", "档案感与人类承诺"],
  ["vermilion", "宣纸朱红", "深靛青分析副色"],
  ["red", "冷红", "谨慎与冲突"],
  ["orange", "赭橙", "行动与窗口"],
  ["yellow", "矿黄", "提醒与未知"],
  ["green", "松绿", "韧性与长期"],
  ["cyan", "青瓷", "系统与关系"],
  ["blue", "靛蓝", "证据与审阅"],
  ["purple", "暮紫", "复杂与反事实"],
] as const;

type ThemeId = (typeof themes)[number][0];

function isWorkspace(value: string | null): value is WorkspaceId {
  return value !== null && workspaceOrder.includes(value as WorkspaceId);
}

function isTheme(value: string | null): value is ThemeId {
  return value !== null && themes.some(([id]) => id === value);
}

export function DecisionShell() {
  const [activeWorkspace, setActiveWorkspace] = useState<WorkspaceId>("workspace");
  const [theme, setTheme] = useState<ThemeId>("ink");
  const [drawer, setDrawer] = useState<DrawerId>(null);
  const [question, setQuestion] = useState("");
  const [draftNotice, setDraftNotice] = useState("");
  const projectTrigger = useRef<HTMLButtonElement>(null);
  const themeTrigger = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const queryView = params.get("view");
    const queryTheme = params.get("theme");
    const storedTheme = window.localStorage.getItem("ludus-theme-v7");
    const nextWorkspace = isWorkspace(queryView) ? queryView : "workspace";
    const migratedTheme = queryTheme === "v6" ? "ledger" : queryTheme;
    const nextTheme = isTheme(migratedTheme)
      ? migratedTheme
      : isTheme(storedTheme)
        ? storedTheme
        : "ink";

    setActiveWorkspace(nextWorkspace);
    setTheme(nextTheme);
    document.documentElement.dataset.theme = nextTheme;
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("ludus-theme-v7", theme);
    const params = new URLSearchParams(window.location.search);
    params.set("theme", theme);
    params.set("view", activeWorkspace);
    window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
  }, [activeWorkspace, theme]);

  const closeDrawer = useCallback(() => {
    const closing = drawer;
    setDrawer(null);
    window.setTimeout(() => {
      if (closing === "project") projectTrigger.current?.focus();
      if (closing === "theme") themeTrigger.current?.focus();
    }, 0);
  }, [drawer]);

  useEffect(() => {
    if (!drawer) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeDrawer();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [closeDrawer, drawer]);

  const currentTheme = useMemo(
    () => themes.find(([id]) => id === theme) ?? themes[0],
    [theme],
  );

  const submitDraft = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!question.trim()) {
      setDraftNotice("请先写下一个需要承担责任的取舍问题。");
      return;
    }
    setDraftNotice("问题草稿已保留在当前页面；API 合同接入前不会创建 Case 或启动分析。");
  };

  return (
    <div className="app-shell">
      <header className="masthead">
        <div className="brand-lockup">
          <Image
            className="brand-logo"
            src="/ludus-logo.svg"
            alt="Ludus"
            width={1478}
            height={406}
            priority
          />
        </div>

        <div className="masthead-context">
          <span className="source-mode"><i /> 离线准备</span>
          <span className="context-divider" aria-hidden="true" />
          <span className="project-context">未建立决策项目</span>
        </div>

        <div className="masthead-actions">
          <button
            ref={themeTrigger}
            className="quiet-action"
            type="button"
            aria-haspopup="dialog"
            aria-expanded={drawer === "theme"}
            onClick={() => setDrawer("theme")}
          >
            <Palette size={17} aria-hidden="true" />
            <span><small>主题</small>{currentTheme[1]}</span>
          </button>
          <button
            ref={projectTrigger}
            className="quiet-action"
            type="button"
            aria-haspopup="dialog"
            aria-expanded={drawer === "project"}
            onClick={() => setDrawer("project")}
          >
            <Archive size={17} aria-hidden="true" />
            <span><small>档案</small>项目</span>
          </button>
          <button className="mobile-menu" type="button" onClick={() => setDrawer("project")} aria-label="打开项目抽屉">
            <Menu size={20} />
          </button>
        </div>
      </header>

      <nav className="decision-spine" aria-label="决策工作区">
        {workspaceOrder.map((id) => {
          const item = workspaces[id];
          const Icon = item.icon;
          const active = activeWorkspace === id;
          return (
            <button
              key={id}
              type="button"
              className={active ? "spine-step is-active" : "spine-step"}
              aria-current={active ? "page" : undefined}
              onClick={() => setActiveWorkspace(id)}
            >
              <span className="spine-number">{item.number}</span>
              <Icon size={18} aria-hidden="true" />
              <span className="spine-copy"><b>{item.label}</b><small>{item.description}</small></span>
              {id !== "decision" && <ChevronRight className="spine-chevron" size={16} aria-hidden="true" />}
            </button>
          );
        })}
      </nav>

      <main className="stage">
        {activeWorkspace === "workspace" ? (
          <section className="workspace-view" aria-labelledby="workspace-title">
            <header className="view-intro">
              <div>
                <p className="section-code">WORKSPACE / EMPTY PROJECT</p>
                <h1 id="workspace-title">先把问题写清楚，再让系统开始工作。</h1>
              </div>
              <p>当前没有 Case。Ludus 不会伪造档案计数、证据、运行状态或结论。</p>
            </header>

            <div className="empty-workbench">
              <form className="decision-question" onSubmit={submitDraft}>
                <div className="form-heading"><span>DECISION QUESTION / DRAFT</span><small>创建后才生成 Case 版本</small></div>
                <label htmlFor="decision-question">现在最需要看清的取舍是什么？</label>
                <textarea
                  id="decision-question"
                  rows={6}
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  placeholder="例如：未来 12 个月，我们应该把有限资源投入现有产品增长，还是验证一个新的市场方向？"
                />
                <div className="form-actions">
                  <button type="button" className="secondary-button" onClick={() => setDraftNotice("材料导入将在安全上传合同完成后开放。")}>先导入材料</button>
                  <button type="submit" className="primary-button"><Plus size={17} />建立决策项目</button>
                </div>
                <p className="privacy-note">项目创建前不会生成证据、模型、报告或正式档案。</p>
                {draftNotice && <p className="draft-notice" role="status">{draftNotice}</p>}
              </form>

              <aside className="method-note" aria-label="新项目建立步骤">
                <p className="section-code">RESPONSIBILITY FIRST</p>
                <h2>系统先确认责任，再请求计算。</h2>
                <ol>
                  <li><span>1</span><div><b>界定问题</b><small>明确选项、时间窗和真正的取舍。</small></div></li>
                  <li><span>2</span><div><b>确认材料</b><small>区分用户输入、外部来源与未知。</small></div></li>
                  <li><span>3</span><div><b>授权分析</b><small>由人确认方法、阈值与可接受风险。</small></div></li>
                </ol>
                <div className="method-callout"><CheckCircle2 size={18} /><p>没有项目时，Decision Spine 与运行状态都不会伪造显示。</p></div>
              </aside>
            </div>

            <section className="example-prompts" aria-labelledby="example-title">
              <div><p className="section-code">STARTING POINTS</p><h2 id="example-title">从一种真实取舍开始</h2></div>
              <div className="example-grid">
                {[
                  ["方向取舍", "继续扩大当前市场，还是转向一个更可验证的细分机会？"],
                  ["资源承诺", "现在招聘关键岗位，还是延后并先降低交付风险？"],
                  ["条件决策", "是否接受合作条件；哪些前提失效时必须退出？"],
                ].map(([title, copy]) => (
                  <button key={title} type="button" onClick={() => { setQuestion(copy); setDraftNotice(""); }}>
                    <b>{title}</b><span>{copy}</span><ChevronRight size={17} />
                  </button>
                ))}
              </div>
            </section>
          </section>
        ) : (
          <section className="pending-view" aria-labelledby="pending-title">
            <div className="pending-symbol">
              {activeWorkspace === "analysis" && <Sparkles size={34} />}
              {activeWorkspace === "report" && <BookOpenText size={34} />}
              {activeWorkspace === "sandbox" && <Beaker size={34} />}
              {activeWorkspace === "decision" && <Scale size={34} />}
            </div>
            <p className="section-code">{activeWorkspace.toUpperCase()} / NO CASE</p>
            <h1 id="pending-title">{workspaces[activeWorkspace].label}工作区尚未获得有效输入。</h1>
            <p>请先在工作台建立决策项目。系统不会用静态样例冒充本次运行结果。</p>
            <button type="button" className="text-button" onClick={() => setActiveWorkspace("workspace")}>返回工作台 <ChevronRight size={16} /></button>
          </section>
        )}
      </main>

      <footer className="status-rail">
        <span><i className="status-dot" /> Gate 0 · baseline bootstrap</span>
        <span>尚未创建决策项目；静态界面不会伪造分析、报告或签署结果。</span>
      </footer>

      {drawer && (
        <div className="drawer-backdrop" onMouseDown={(event) => { if (event.currentTarget === event.target) closeDrawer(); }}>
          <aside className="drawer" role="dialog" aria-modal="true" aria-label={drawer === "project" ? "项目抽屉" : "主题抽屉"}>
            <header><div><p className="section-code">{drawer === "project" ? "PROJECT ARCHIVE" : "THEME FOLIO"}</p><h2>{drawer === "project" ? "决策项目" : "材料主题"}</h2></div><button type="button" onClick={closeDrawer} aria-label="关闭抽屉"><X size={20} /></button></header>
            {drawer === "project" ? (
              <div className="drawer-empty"><FolderOpen size={30} /><h3>还没有决策项目</h3><p>建立第一个问题后，这里才会出现 Case、版本与档案状态。</p><button type="button" className="primary-button" onClick={() => { closeDrawer(); setActiveWorkspace("workspace"); }}><Plus size={17} />建立项目</button></div>
            ) : (
              <div className="theme-list" role="listbox" aria-label="选择主题">
                {themes.map(([id, name, description]) => (
                  <button key={id} type="button" role="option" aria-selected={theme === id} className={theme === id ? "theme-option is-selected" : "theme-option"} onClick={() => setTheme(id)}>
                    <span className="theme-swatch" data-preview-theme={id}><i /><i /><i /></span>
                    <span><b>{name}</b><small>{description}</small></span>
                    {theme === id && <CheckCircle2 size={18} />}
                  </button>
                ))}
              </div>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}