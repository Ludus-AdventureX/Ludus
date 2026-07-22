# Look V7 → Production Component Map

This map records the first, read-only translation boundary from the static Look V7 reference into the production shell. It is not a runtime import contract.

| Look source concept | Production target | Rule |
|---|---|---|
| Masthead | `Masthead` | Render current workspace, source mode and theme entry from API/session state. |
| Decision Spine | `DecisionSpine` | Five workspaces remain the only active information architecture. |
| Workspace | `WorkspaceView` | Case/dossier context and next-action surface; no fabricated run state. |
| Analysis | `AnalysisView` | Charter, run progress, evidence quality and recovery states. |
| Report | `ReportView` | Structured report, source mode and Evidence Drawer; never hidden reasoning. |
| Sandbox | `SandboxView` | Draft/confirmed graph and simulation controls with formal/preview distinction. |
| Decision | `DecisionView` | Human-owned signoff and append-only DecisionRecord flow. |
| Project Drawer | `ProjectDrawer` | Case selection and creation; clear cross-Case selection on switch. |
| Empty Project | `EmptyProjectView` | Creation before Run/Source/Report; no fake counters or analysis state. |
| Review dialog | `ReviewDialog` | Structured review only; does not mutate a DecisionRecord. |
| Theme drawer | `ThemeDrawer` | Ten themes; visual mutation only, never an analysis/signoff mutation. |
| Evidence drawer | `EvidenceDrawer` | SourceSpan, citation, quality and opposing evidence. |

## Runtime boundary

- `look/index.html` supplies structure and accessibility behavior as a reference.
- `look/themes.css` is converted into centralized design tokens.
- `look/styles.css` is split into semantic, layout and component layers.
- `look/app.js` is a behavior specification and test input only; it must not be loaded by production.
- All production data comes from generated contracts, TanStack Query and the SSE adapter.