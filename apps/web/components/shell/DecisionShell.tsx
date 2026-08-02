"use client";

import Image from "next/image";
import { CSSProperties, FormEvent, MouseEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  CaseCreateFlowError,
  createDecisionCase,
  isAuthRequired,
  navigateToCreatedCase,
  navigateToEnter
} from "@/lib/shell/createCase";
import { caseListRouteAvailable, fetchProjectDirectory, type ProjectDirectory } from "@/lib/shell/projects";

const copy = {
  "currentIssue": "当前议题",
  "emptyCaseTitle": "尚未创建决策项目",
  "emptySource": "空工作台",
  "mobileCaseGlyph": "项",
  "themeLabel": "主题",
  "dossierLabel": "档案",
  "emptyCoordinate": "NEW-00",
  "emptyCoordinateStatus": "尚未建立项目",
  "emptyEyebrow": "这里没有示例答案，也没有等待你清理的仪表盘",
  "emptyTitle": "先写下一个真正需要\n承担后果的问题。",
  "emptyIntro": "Ludus 不要求你先选模板、方法或 Agent。一个决策项目从人的问题开始；证据、分析、推演和正式决定会在边界确认后逐步出现。",
  "formSubline": "只有创建后才会生成 Case 版本",
  "formLabel": "现在最需要看清的取舍是什么？",
  "formPlaceholder": "例如：未来 12 个月，我们应该把有限资源投入现有产品增长，还是验证一个新的市场方向？",
  "formPrivacy": "项目创建前不会生成证据、模型、报告或正式档案。",
  "importText": "先导入材料",
  "createText": "建立决策项目",
  "createSubline": "进入问题边界确认，而不是立即开始分析",
  "methodLabel": "从一个问题开始",
  "methodNote": "没有项目时，Decision Spine、档案计数和运行状态都不会伪造显示。",
  "examplesTitle": "可作为起点的提问方式",
  "examplesSubline": "点击只会填入草稿，不会自动创建项目",
  "caseDrawerTitle": "项目与空工作台",
  "caseDrawerIntro": "切换只改变当前展示项目，不会修改已保存的 Case 版本。",
  "caseEmptyTitle": "空项目演示",
  "caseEmptyStatus": "尚未创建 Case",
  "caseEmptyDescription": "查看没有任何项目时，对外呈现的新建决策入口。",
  "themeDrawerTitle": "十种材料色",
  "themeDrawerIntro": "只改变环境、强调色与模型墨色；人的责任、系统证据和未知状态仍保持清晰分工。",
  "themeReset": "恢复水墨",
  "themeApply": "应用并返回",
  "caseRuleLabel": "展示规则",
  "caseRuleText": "空项目不会显示伪造的进度、证据数量、运行状态或推荐结果。",
  "caseStay": "留在当前项目",
  "caseOpen": "打开空工作台",
  "draftedTitle": "决策项目已建立",
  "draftedSubline": "正在打开五工作台",
  "creatingTitle": "正在建立决策项目…",
  "creatingSubline": "建立访客会话并写入决策问题",
  "emptySubmitNotice": "决策项目已建立，正在打开工作台…",
  "emptyNoQuestionNotice": "先写下一个需要承担后果的问题。",
  "emptyCreateFailedFallback": "建立决策项目失败，请稍后重试。",
  "emptyImportNotice": "材料导入即将上线：届时会把已有材料写入项目级档案，再开始边界确认。",
  "methodRows": [
    [
      "01",
      "写下问题",
      "保留你的原话，不自动改写成系统任务。"
    ],
    [
      "02",
      "确认边界",
      "确认时间、资源、责任主体和不能接受的结果。"
    ],
    [
      "03",
      "决定深度",
      "由你选择快速梳理、聚焦研究或完整战略分析。"
    ]
  ],
  "exampleRows": [
    [
      "方向取舍",
      "我们应该继续扩大当前市场，还是把资源转向一个更小但更确定的细分机会？",
      "继续扩大，还是换一个更可验证的方向？"
    ],
    [
      "资源承诺",
      "在现金窗口有限的情况下，我们应该现在招聘关键岗位，还是延后并先降低交付风险？",
      "现在投入，还是保留路线切换能力？"
    ],
    [
      "条件决策",
      "我们是否应该接受这个合作条件；哪些前提一旦不成立，就必须退出？",
      "在什么条件下做，以及何时停止？"
    ]
  ]
} as const;
const workspaceItems = [
  [
    "workspace",
    "Q",
    "问题",
    "界定边界"
  ],
  [
    "analysis",
    "E",
    "证据",
    "研究与质疑"
  ],
  [
    "report",
    "J",
    "判断",
    "条件化建议"
  ],
  [
    "sandbox",
    "G",
    "推演",
    "寻找翻转"
  ],
  [
    "decision",
    "D",
    "决定",
    "冻结行动"
  ],
  [
    "review",
    "R",
    "复盘",
    "回到现实"
  ]
] as const;
const themes = [
  [
    "ink",
    "水墨黑白",
    "Ink Wash",
    "黑、灰与矿物蓝灰，作为不带情绪的研究基线。",
    "#f1f0ec",
    "#2b2d2c",
    "#53656b",
    "#716957"
  ],
  [
    "ledger",
    "墨纸酒红",
    "Quiet Ledger",
    "暖纸、酒红承诺与烟墨证据，保留沉静而克制的经典基线。",
    "#f2eee5",
    "#783b49",
    "#536866",
    "#80633b"
  ],
  [
    "vermilion",
    "宣纸朱红",
    "Xuan Cinnabar",
    "宣纸白、朱砂红与深靛青，拉开承诺、推演与未知的责任层级。",
    "#f6f2e9",
    "#a54030",
    "#40536b",
    "#80694a"
  ],
  [
    "red",
    "莫兰迪红",
    "Dusty Red",
    "旧玫瑰与松柏灰，适合编辑批注、承诺复核与谨慎异议。",
    "#f2eceb",
    "#84515b",
    "#4e625f",
    "#7d6048"
  ],
  [
    "orange",
    "莫兰迪橙",
    "Quiet Terracotta",
    "陶土与深青，推动行动但不触发警报感。",
    "#f2ece5",
    "#8f5746",
    "#44676a",
    "#7c633f"
  ],
  [
    "yellow",
    "莫兰迪黄",
    "Dry Ochre",
    "赭石与橄榄灰，适合条件、阈值与未知项。",
    "#f3f0e4",
    "#78693e",
    "#52675b",
    "#876047"
  ],
  [
    "green",
    "莫兰迪绿",
    "Muted Sage",
    "鼠尾草与深灰蓝，适合长期观察、稳健和复盘。",
    "#edf1eb",
    "#5a705e",
    "#4c626a",
    "#7c624d"
  ],
  [
    "cyan",
    "莫兰迪青",
    "Mist Cyan",
    "雾青与深紫灰，保持清醒而不进入科技荧光。",
    "#eaf1f0",
    "#4d7272",
    "#554e6b",
    "#7a6348"
  ],
  [
    "blue",
    "莫兰迪蓝",
    "Slate Blue",
    "灰蓝与暖橄榄，强调研究秩序和版本边界。",
    "#ebeff4",
    "#5b6d88",
    "#536452",
    "#7e604d"
  ],
  [
    "purple",
    "莫兰迪紫",
    "Dusty Violet",
    "灰紫与松柏青，适合复杂判断和审慎异议。",
    "#f0edf2",
    "#75617d",
    "#4e665f",
    "#7f604d"
  ]
] as const;

type WorkspaceId = (typeof workspaceItems)[number][0];
type ThemeId = (typeof themes)[number][0];
type DrawerId = "project" | "theme" | null;

function isWorkspace(value: string | null): value is WorkspaceId {
  return value !== null && workspaceItems.some(([id]) => id === value);
}
function isTheme(value: string | null): value is ThemeId {
  return value !== null && themes.some(([id]) => id === value);
}

const drawerFocusableSelector = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])"
].join(",");

function getDrawerFocusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(drawerFocusableSelector)).filter(
    (element) => element.getAttribute("aria-hidden") !== "true"
  );
}

export function DecisionShell() {
  const [activeWorkspace, setActiveWorkspace] = useState<WorkspaceId>("workspace");
  const [theme, setTheme] = useState<ThemeId>("ink");
  const [drawer, setDrawer] = useState<DrawerId>(null);
  const [question, setQuestion] = useState("");
  const [draftNotice, setDraftNotice] = useState("");
  const [isDrafted, setIsDrafted] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [ready, setReady] = useState(false);
  const [projectDirectory, setProjectDirectory] = useState<ProjectDirectory | null>(null);
  const [projectCases, setProjectCases] = useState<Array<{ decisionCaseId: string; title: string; status: string }>>([]);
  const projectTrigger = useRef<HTMLButtonElement>(null);
  const themeTrigger = useRef<HTMLButtonElement>(null);
  const questionInput = useRef<HTMLTextAreaElement>(null);
  const drawerDialog = useRef<HTMLElement>(null);
  const drawerTrigger = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    document.body.classList.add("empty-case");
    return () => document.body.classList.remove("empty-case");
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const requestedTheme = params.get("theme");
    const storedTheme = window.localStorage.getItem("ludus-theme-v7");
    const requestedView = params.get("view");
    setActiveWorkspace(isWorkspace(requestedView) ? requestedView : "workspace");
    setTheme(isTheme(requestedTheme) ? requestedTheme : isTheme(storedTheme) ? storedTheme : "ink");
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("ludus-theme-v7", theme);
    const params = new URLSearchParams(window.location.search);
    params.set("theme", theme);
    params.set("view", activeWorkspace);
    window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
  }, [activeWorkspace, ready, theme]);

  const currentTheme = useMemo(() => themes.find(([id]) => id === theme) ?? themes[0], [theme]);
  const activeItem = useMemo(() => workspaceItems.find(([id]) => id === activeWorkspace) ?? workspaceItems[0], [activeWorkspace]);

  const openDrawer = useCallback((nextDrawer: Exclude<DrawerId, null>, trigger: HTMLButtonElement) => {
    drawerTrigger.current = trigger;
    setDrawer(nextDrawer);
  }, []);

  // Live case directory for the project drawer: same canonical read surface
  // the case shell's ProjectDrawer consumes. The drawer previously rendered
  // only the static "empty project" demo because the list route did not exist
  // when this shell shipped; it does now, so the drawer lists real projects.
  useEffect(() => {
    if (drawer !== "project") return;
    let cancelled = false;
    (async () => {
      setProjectDirectory(null);
      const dir = await fetchProjectDirectory();
      if (cancelled) return;
      setProjectDirectory(dir);
      if (caseListRouteAvailable && dir.status === "ready" && dir.workspaces.length > 0) {
        const ws = dir.workspaces[0]!;
        try {
          const res = await fetch(
            `/api/workspaces/${encodeURIComponent(ws.workspaceId)}/cases`,
            { credentials: "include" },
          );
          if (!cancelled && res.ok) {
            const body = (await res.json()) as { data?: { items?: Array<{ decisionCaseId: string; title: string; status: string }> } };
            setProjectCases(body?.data?.items ?? []);
          }
        } catch { /* graceful: empty list keeps the honest new-project entry */ }
      }
    })();
    return () => { cancelled = true; };
  }, [drawer]);

  const closeDrawer = useCallback(() => {
    if (!drawer) return;
    const closing = drawer;
    const trigger = drawerTrigger.current;
    setDrawer(null);
    window.setTimeout(() => {
      const fallback = closing === "project" ? projectTrigger.current : themeTrigger.current;
      (trigger?.isConnected ? trigger : fallback)?.focus();
      drawerTrigger.current = null;
    }, 0);
  }, [drawer]);

  useEffect(() => {
    if (!drawer) return;
    const dialog = drawerDialog.current;
    if (!dialog) return;

    const focusTimer = window.setTimeout(() => {
      const [firstFocusable] = getDrawerFocusableElements(dialog);
      (firstFocusable ?? dialog).focus();
    }, 0);

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeDrawer();
        return;
      }
      if (event.key !== "Tab") return;

      const focusable = getDrawerFocusableElements(dialog);
      if (focusable.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      const focusIsOutside = active === null || !dialog.contains(active);

      if (event.shiftKey && (active === first || focusIsOutside)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || focusIsOutside)) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [closeDrawer, drawer]);

  const submitDraft = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (isCreating || isDrafted) return;
    if (!question.trim()) {
      setDraftNotice(copy.emptyNoQuestionNotice);
      questionInput.current?.focus();
      return;
    }
    setIsCreating(true);
    setDraftNotice("");
    try {
      const created = await createDecisionCase(question.trim());
      setIsDrafted(true);
      setDraftNotice(copy.emptySubmitNotice);
      navigateToCreatedCase(created);
    } catch (error) {
      // Unauthenticated visitor -> invite-gated entry, returning here after.
      if (isAuthRequired(error)) {
        navigateToEnter("/");
        return;
      }
      setDraftNotice(
        error instanceof CaseCreateFlowError ? error.message : copy.emptyCreateFailedFallback
      );
      questionInput.current?.focus();
    } finally {
      setIsCreating(false);
    }
  };

  const chooseExample = (value: string) => {
    setQuestion(value);
    setDraftNotice("");
    window.setTimeout(() => questionInput.current?.focus(), 0);
  };

  const drawerTitleId = drawer === "theme" ? "theme-drawer-title" : "project-drawer-title";
  const drawerDialogId = drawer === "theme" ? "theme-drawer-dialog" : "project-drawer-dialog";

  return (
    <div className="app-shell">
      <header className="masthead" inert={drawer !== null}>
        <div className="brand-lockup" aria-label="Ludus">
          <Image className="brand-logo" src="/ludus-logo.svg" alt="Ludus" width={1478} height={406} priority />
        </div>
        <div className="case-title">
          <span>{copy.currentIssue}</span>
          <button ref={projectTrigger} id="openCaseMenu" type="button" aria-haspopup="dialog" aria-controls="project-drawer-dialog" aria-expanded={drawer === "project"} onClick={(event) => openDrawer("project", event.currentTarget)}>
            <span>{copy.emptyCaseTitle}</span> <i aria-hidden="true">{"\u2304"}</i>
          </button>
        </div>
        <div className="masthead-actions">
          <span className="source-mode is-empty" id="sourceMode"><i /> <span>{copy.emptySource}</span></span>
          <button className="mobile-case-trigger" id="openMobileCaseMenu" type="button" aria-label="Open project switcher" aria-haspopup="dialog" aria-controls="project-drawer-dialog" aria-expanded={drawer === "project"} onClick={(event) => openDrawer("project", event.currentTarget)}>{copy.mobileCaseGlyph}</button>
          <button ref={themeTrigger} className="theme-trigger" id="openThemeDrawer" type="button" aria-label={`Switch theme: ${currentTheme[1]}`} aria-haspopup="dialog" aria-controls="theme-drawer-dialog" aria-expanded={drawer === "theme"} onClick={(event) => openDrawer("theme", event.currentTarget)}>
            <span className="theme-trigger-swatch" aria-hidden="true"><i /><i /><i /></span>
            <span className="theme-trigger-label"><small>{copy.themeLabel}</small><b>{currentTheme[1]}</b></span>
          </button>
          <button className="quiet-action" id="openDossier" type="button" aria-label="Open decision dossier" aria-haspopup="dialog" aria-controls="project-drawer-dialog" aria-expanded={drawer === "project"} onClick={(event) => openDrawer("project", event.currentTarget)}><span>{copy.dossierLabel}</span><b>?</b></button>
        </div>
      </header>

      <nav className="decision-spine" aria-label="Decision lifecycle" inert={drawer !== null}>
        <div className="spine-line" aria-hidden="true" />
        {workspaceItems.map(([id, coordinate, label, description]) => {
          const active = activeWorkspace === id;
          return (
            <button key={id} className={active ? "spine-step is-active" : "spine-step"} type="button" aria-current={active ? "page" : undefined} onClick={() => setActiveWorkspace(id)}>
              <span className="step-coordinate">{coordinate}</span>
              <span className="step-copy"><b>{label}</b><small>{description}</small></span>
            </button>
          );
        })}
      </nav>

      <main className="stage" id="mainStage" inert={drawer !== null}>
        {activeWorkspace === "workspace" ? (
          <section className="view empty-view is-active" id="view-empty" aria-labelledby="empty-title">
            <div className="empty-case-shell">
              <header className="empty-intro">
                <div className="intro-coordinate"><span>{copy.emptyCoordinate}</span><i /><small>{copy.emptyCoordinateStatus}</small></div>
                <p className="eyebrow">{copy.emptyEyebrow}</p>
                <h1 id="empty-title">{copy.emptyTitle.split("\n").map((line, index) => <span key={line}>{index > 0 && <br />}{line}</span>)}</h1>
                <p>{copy.emptyIntro}</p>
              </header>

              <div className="empty-workbench">
                <form className={isDrafted ? "empty-case-form is-drafted" : "empty-case-form"} id="emptyCaseForm" onSubmit={submitDraft}>
                  <div className="empty-form-heading"><span>DECISION QUESTION / DRAFT</span><small>{copy.formSubline}</small></div>
                  <label htmlFor="emptyQuestion">{copy.formLabel}</label>
                  <textarea ref={questionInput} id="emptyQuestion" rows={5} value={question} onChange={(event) => { setQuestion(event.target.value); setDraftNotice(""); }} placeholder={copy.formPlaceholder} />
                  <div className="empty-form-actions">
                    <button type="button" className="secondary-action" id="importEmptyMaterial" onClick={() => setDraftNotice(copy.emptyImportNotice)}>{copy.importText}</button>
                    <button type="submit" className="primary-action" id="createEmptyCase" disabled={isCreating}><span>{isDrafted ? copy.draftedTitle : isCreating ? copy.creatingTitle : copy.createText}</span><small>{isDrafted ? copy.draftedSubline : isCreating ? copy.creatingSubline : copy.createSubline}</small></button>
                  </div>
                  <p className="empty-privacy">{copy.formPrivacy}</p>
                  {draftNotice && <p className="draft-notice" role="status">{draftNotice}</p>}
                </form>

                <aside className="empty-method" aria-label="New project steps">
                  <span className="margin-label">{copy.methodLabel}</span>
                  <ol>
                    {copy.methodRows.map(([number, title, description]) => <li key={number}><b>{number}</b><div><strong>{title}</strong><p>{description}</p></div></li>)}
                  </ol>
                  <div className="empty-method-note"><i /><p>{copy.methodNote}</p></div>
                </aside>
              </div>

              <section className="empty-examples" aria-labelledby="emptyExamplesTitle">
                <header><span id="emptyExamplesTitle">{copy.examplesTitle}</span><small>{copy.examplesSubline}</small></header>
                <div>
                  {copy.exampleRows.map(([label, prompt, description]) => <button key={prompt} type="button" onClick={() => chooseExample(prompt)}><b>{label}</b><span>{description}</span></button>)}
                </div>
              </section>
            </div>
          </section>
        ) : (
          <section className="view pending-view is-active" aria-labelledby="pending-title">
            <div className="pending-symbol"><span>{activeItem[1]}</span></div>
            <p className="eyebrow">{activeItem[1]} / NO CASE</p>
            <h1 id="pending-title">No case input yet.</h1>
            <p>Please return to the question entry and create a decision project before opening this workspace.</p>
            <button type="button" className="text-action" onClick={() => setActiveWorkspace("workspace")}>Back to question entry <span aria-hidden="true">{"\u2192"}</span></button>
          </section>
        )}
      </main>

      {drawer && (
        <aside className={drawer === "theme" ? "drawer theme-drawer is-open" : "drawer case-drawer is-open"}>
          <button className="drawer-scrim" type="button" aria-label="Close drawer" onClick={closeDrawer} />
          <section ref={drawerDialog} id={drawerDialogId} className={drawer === "theme" ? "drawer-sheet theme-sheet" : "drawer-sheet case-sheet"} role="dialog" aria-modal="true" aria-labelledby={drawerTitleId} tabIndex={-1}>
            <header>
              <div>
                <span>{drawer === "theme" ? "THEME FOLIO" : "DECISION PROJECTS"}</span>
                <h2 id={drawerTitleId}>{drawer === "theme" ? copy.themeDrawerTitle : copy.caseDrawerTitle}</h2>
                <p>{drawer === "theme" ? copy.themeDrawerIntro : copy.caseDrawerIntro}</p>
              </div>
              <button className="drawer-close" type="button" onClick={closeDrawer} aria-label="Close drawer">{"\u00d7"}</button>
            </header>

            {drawer === "project" ? (
              <>
                <div className="case-list" role="radiogroup" aria-label="Choose project">
                  {projectCases.length > 0 && (
                    <>
                      {projectCases.map((c) => {
                        const href = `/cases/${encodeURIComponent(c.decisionCaseId)}?ws=${encodeURIComponent(projectDirectory?.status === "ready" ? projectDirectory.workspaces[0]?.workspaceId ?? "" : "")}`;
                        return (
                          <a
                            key={c.decisionCaseId}
                            className="case-choice"
                            href={href}
                            onClick={(event: MouseEvent<HTMLAnchorElement>) => {
                              // Full-page navigation: this shell's drawer
                              // effect rewrites the URL from the stale
                              // pathname and would cancel a client-side router
                              // push (same live finding as ProjectDrawer).
                              event.preventDefault();
                              window.location.assign(href);
                            }}
                          >
                            <span className="case-glyph">Q</span>
                            <span><b>{c.title || c.decisionCaseId.slice(0, 8)}</b><small>{c.status}</small></span>
                          </a>
                        );
                      })}
                    </>
                  )}
                  <button className="case-choice" type="button" role="radio" aria-checked="true" onClick={() => { setActiveWorkspace("workspace"); closeDrawer(); }}>
                    <span className="case-glyph empty">{"\uff0b"}</span>
                    <span><b>{copy.caseEmptyTitle}</b><small>{copy.caseEmptyStatus}</small><em>{copy.caseEmptyDescription}</em></span>
                  </button>
                </div>
                <section className="case-drawer-note"><span>{copy.caseRuleLabel}</span><p>{copy.caseRuleText}</p></section>
                <footer>
                  <button className="secondary-action" type="button" onClick={closeDrawer}>{copy.caseStay}</button>
                  <button
                    className="primary-action small"
                    type="button"
                    onClick={(event: MouseEvent<HTMLButtonElement>) => {
                      // Same full-page navigation rationale as the case links.
                      event.preventDefault();
                      window.location.assign("/");
                    }}
                  >
                    <span>新建项目</span>
                  </button>
                </footer>
              </>
            ) : (
              <>
                <div className="theme-options" role="radiogroup" aria-label="Choose Ludus theme">
                  {themes.map(([id, name, english, description, paper, key, analysis, unknown]) => {
                    const previewStyle = { "--preview-paper": paper, "--preview-key": key, "--preview-analysis": analysis, "--preview-unknown": unknown } as CSSProperties;
                    return (
                      <button key={id} className="theme-option" type="button" role="radio" aria-checked={theme === id} style={previewStyle} onClick={() => setTheme(id)}>
                        <span className="theme-preview" aria-hidden="true"><i /><i /><i /><i /></span>
                        <span><b>{name}</b><small>{english}</small><em>{description}</em></span>
                      </button>
                    );
                  })}
                </div>
                <footer><button className="secondary-action" type="button" onClick={() => setTheme("ink")}>{copy.themeReset}</button><button className="primary-action small" type="button" onClick={closeDrawer}><span>{copy.themeApply}</span></button></footer>
              </>
            )}
          </section>
        </aside>
      )}
    </div>
  );
}
