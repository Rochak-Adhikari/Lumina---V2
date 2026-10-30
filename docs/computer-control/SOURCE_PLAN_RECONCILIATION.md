# Supplied-plan reconciliation
Both original files were read in full (Markdown text and all 1219 DOCX body paragraphs, including tables). Neither was edited. After removing Markdown link destinations/formatting, every substantive DOCX paragraph is covered by Markdown; unmatched DOCX paragraphs below are cover material. The reverse comparison exposes an important omission: Word section 24 contains its headings but omits the Markdown checkbox requirements. The files are therefore NOT fully equivalent; this is not a byte/layout equivalence claim.

DOCX-only material: ["LUMINA General-PurposeWindows Computer-Control Engine", "Professional Engineering Plan and Implementation Specification", "28 October 2026", "Windows desktop computer control only", "AUDIENCE", "Rochak, GPT-6 Astra and implementation agents", "Proposed engineering baseline; not an implementation-completion claim", "Design objective: observe the real Windows screen, choose actions dynamically, execute them, verify outcomes, and adapt safely."]

| Original requirement or assumption | Resolution in this planning set |
|---|---|
| §§0–3 Windows-only dynamic execution; preserve existing work | Retained; fixed recipes are regression fixtures, not the target engine. |
| §4 visual-primary but §8.4 UIA-preferred | Visual observation must support unfamiliar interfaces; choose an admitted app API/UIA action when more reliable, otherwise verified visual input. No compulsory UIA dependency. |
| §§5–6 many new states/types | Reuse TaskManager statuses plus progress phase. Extend existing action dataclasses/controller explicitly; no parallel state database. |
| §7 broker/capture_latest and revoke on control Stop | Connection-owned stream remains canonical. Stop revokes action bindings, never independent sharing. capture_latest is a consumer request, not another capture pump. |
| §8 UIA patterns generally useful | Inspection exists; generic Invoke/Value/Toggle remain denied. Pattern presence is not permission. Toggle known limitation remains until specifically resolved. |
| §9 guaranteed release, last-moment validation | Replace guarantee with tracked release attempts and explicit uncertainty. Global SendInput cannot atomically bind an HWND/focus; owner must accept documented ordinary-input limits before native expansion. |
| §§10–11 replaceable model and exact approval | Retained. Existing generate_goal is text/recipe selection, not screenshot computer use. Local token is not OS-backed human authentication. Sensitive/external operations stay disabled absent a stronger reviewed path. |
| §§12–15 verification, failures, UI, lifecycle | Retained. Current matching UI alone cannot prove causal external settlement or absence of intermediate effects. No automatic restart adoption. |
| §16 approximately two dozen new modules | Reduced to four justified proposed modules; most responsibilities extend existing files. No wholesale package migration. |
| §17 function inventory | Covered by CONTRACTS.md, existing reuse references and phase tests; optional events/deltas are optimizations within phases, not new prerequisite chains. |
| §18 new session endpoints | Reuse /api/tasks, /api/windows, existing sharing routes and WebSocket. New production routes require evidence that existing routes cannot carry the contract. |
| §19 test layers and 90%/80% suggested thresholds | Seven evidence levels retained. Thresholds are proposed release gates with fixed denominators, not established performance or newly approved promises. |
| §20 Phases 0–8 (nine phases) | Exactly eight phases P0–P7. Observation precedes input; Stop/permission checks precede every native expansion. Open-ended Phase 8 broadening removed from release scope. |
| §§21–24 discipline, resources, threat model and gates | Retained in execution protocol, matrix, model research and phase risks. No large local model or permanent free hosted dependency assumed. |
| §25 scenarios including Call | Controlled receiver only for consequential acceptance. No real call/message as experiment; real WhatsApp calling is future separately reviewed authorization. |
| §§26–27 locked decisions/references; next task Phase 0 | Scope principles retained, unsupported guarantees corrected. This assignment supplies the static P0 audit; first implementation is P1.1 after owner plan approval, not another full audit. |

The roadmap is a proposal for approval. No phase structure is falsely described as owner-approved. Original hashes and the complete initial Git checkpoint are in PLANNING_PRESERVATION.json.

## Markdown-only section 24 checklist

34 checklist items are absent from DOCX body text. All are preserved below and assigned to the acceptance classes, contracts and implementation gates; none was silently discarded. The original two-app minimum is strengthened to three ordinary apps in this proposed release corpus, explicitly subject to owner plan approval.

1. Current Lumina task/authority/screen-sharing systems are reused rather than duplicated.
2. All native input routes through one typed executor/admission boundary.
3. Model is replaceable and cannot invoke native APIs directly.
4. General loop acts on observations; no task sequence must be hardcoded for acceptance tasks.
5. Frame source, frame/capture timestamps, geometry and revocation are carried through.
6. Stale frames/targets fail closed.
7. Window identity is revalidated before actions.
8. UIA tree is bounded; incomplete UIA falls back safely to visual reasoning.
9. Real post-action frames are used for verification.
10. Move/click/press/release/type/hotkey/scroll are implemented and tested on an owned native target.
11. Coordinates are correct for tested scale/DPI/monitor configurations.
12. Partial input and key/button release uncertainty are explicit.
13. Focus failures do not result in unintended typing.
14. Drag and more advanced input are added only after cleanup/release behavior is proven.
15. Strict action schema rejects unsupported actions and code-like fields.
16. At most one action is executed per observe/verify cycle.
17. The model action is dynamic, not a preset recipe for each acceptance task.
18. The system replans after observed changes and handles timeouts.
19. Completion requires a typed, verified postcondition.
20. Stop/takeover invalidates pending actions and late model callbacks.
21. No new action is admitted after Stop epoch in race tests.
22. Current in-flight input is reported honestly; no false rollback promise.
23. Exact, expiring approvals gate consequential effects.
24. The owner can see who has control and can take over.
25. Restart leaves sessions disarmed and approvals invalid.
26. Remote screenshot transmission is visible and authorized.
27. Tier 0–2 tests pass.
28. Controlled live-app tests pass for at least two ordinary apps and one UIA-poor surface.
29. Blind acceptance corpus meets the calibrated success/error thresholds or remaining blockers are explicitly recorded.
30. Zero false-success reports in the corpus.
31. Zero unauthorized effects or post-Stop admissions in testing.
32. Per-test logs, exact commands, timing breakdown and source-change inventory are preserved.
33. Report distinguishes simulated, native, live-model and live-app evidence.
34. No unrelated dirty/untracked work is lost or overwritten.

Mapping: architecture/schema/task-loop→C01–C14/C25–C26 and A/C/D; observation/targets→C01–C08 and A/B; input/cleanup→C14–C22 and B/G; verification/recovery→C23–C27 and D/E/F; Stop/approval/restart→C14/C26/C28 and F/G; privacy/UI/evidence/preservation→C29–C30 and H/I/J plus EXECUTION_PROTOCOL.md.
