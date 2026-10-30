# Decision and risk register
Architecture choices originated as proposals within the planning assignment. D1 is accepted as recorded below; this does not approve other pending gates or authorize implementation. Owner approval remains required for applicable pending decisions; routine implementation details inside an approved milestone need no repeated approval.

| ID | Choice / evidence / alternatives | Cost or risk | Revisit trigger |
|---|---|---|---|
| D0 | Eight phases, source-first reuse. Original nine-phase layout and new computer_use package rejected as unnecessary migration. | Existing files are large/dirty; use small scoped patches. | Evidence existing seams cannot carry a specific approved contract. |
| D1 — ACCEPTED — OWNER APPROVED | **Bounded risk; owner approval: 28 October 2026.** Accept practical ordinary foreground-input semantics in ARCHITECTURE.md, limited to armed approved scope and the mandatory safeguards below. Cooperative receiver's strict target-effect guarantee cannot generalize to global SendInput. | Target/desktop state may change after the final check; possible misdelivery and already-admitted effects after Stop. Ordinary Windows input cannot generally guarantee atomic delivery or zero post-Stop effects. Stronger requirement means general global input is a NO-GO, not grounds for a recovery redesign. | Owner withdraws acceptance or authorized native tests expose unacceptable misdelivery. |
| D2 — OWNER DECISION before P3.2 | Choose account-eligible $0 synthetic image trial or bounded local model trial. No account keys/quotas read. | Model may fail accuracy/latency/free quota; dedicated Google Computer Use currently has no free tier. | Pricing/terms/entitlement or candidate test failure. |
| D3 — OWNER DECISION before live R3 | Consequential automation remains disabled. Existing web token is not authenticated-human evidence; design exact trusted approval and causal postcondition per operation class before enabling. | A vague approval or screen match can duplicate sends/calls. | Separate user request to enable named consequential target/action; no generic unlock. |
| D4 | No new durable ownership/enrollment journal, global registry, process adoption or cloud service. Preserve current unresolved state. | Production marker may block startup/arming; do not inspect/resolve it within this roadmap implementation by default. | Separately authorized runtime-state investigation; unaffected isolated work continues. |
| D5 | Four proposed focused modules; extend existing controller dataclasses and TaskManager. | Existing exact adapter allowlist/digest verifier need explicit compatibility work. | P1 contract tests demonstrate a required additive seam. |
| D6 | UIA opportunistic, visual fallback required; API-specific adapters optional. Toggle stays disabled unless separately evidenced. | Incomplete UIA trees/COM hangs; generic pixels can't establish causal external settlement. | Per-pattern native evidence and target-specific policy. |
| D7 | Latency limits measured per stage. Existing 3-second evidence lifetime cannot simply be relaxed to accommodate a slow model. | Repeated stale predictions may make chosen model unusable. | P2/P3 measurements; use fresh target re-grounding or pause, never re-date frame. |
| D8 | Bounded release corpus; no promise of universal Windows compatibility. | A model can generalize poorly to unfamiliar apps. | Acceptance failure updates tasks within phase, not hidden new major phases. |

Risk handling: RISK-FOCUS→P2.2/D1; RISK-KEYUP→P2.2; RISK-GEOMETRY→P1.2/P2.3; RISK-MODEL/COST→P3.2/D2; RISK-UNCERTAIN→P5.1; RISK-PRIVACY/AUTH→P5.2/D3; RISK-CONCURRENT→every checkpoint; RISK-PACKAGING/RESOURCE→P6.2; RISK-ACCEPTANCE→P7.1. Owner is the approval authority, Astra is implementer, and an explicitly commissioned reviewer may review a gate. The same agent's review is never labeled independent human review.

D1 approval record — 28 October 2026, explicit owner instruction, documentation only. This records acceptance of the bounded-risk decision originally proposed above; stricter existing requirements remain in force.

Accepted limitations:
- The target or desktop state may change after the final pre-action check.
- Stop blocks subsequent action admissions but cannot guarantee that an action already admitted or submitted will have no further effect.
- A timeout, exception, cancellation, interrupted operation or failed cleanup does not prove that an action had no effect.
- Ordinary Windows input cannot generally guarantee atomic delivery or zero post-Stop effects.
- Task success requires independent verification; neither a model response nor a submission acknowledgement establishes success.

Mandatory safeguards:
- Validate target identity, freshness, geometry and action authorization before submission.
- Keep input batches bounded and reject unsupported or unauthorized actions.
- Ensure Stop and takeover block new admissions.
- Track uncertain submissions and potentially held inputs.
- Attempt cleanup when safe and obtain independent release evidence where available.
- Preserve unresolved state and block unsafe continuation while outcomes or cleanup remain uncertain.
- Verify task outcomes against explicit predicates and observable evidence.
- Keep native production enablement disabled until applicable safety and release gates are satisfied.

Authorization boundaries: D1 acceptance does not declare P2.2 complete or authorize native implementation, execution, any real-input test, any disposable target, unrestricted desktop access, P2.3, P3.1 or another milestone. It waives no confirmation, privacy, identity, verification or release requirement. A separate explicit disposable-target authorization is required before native testing; earlier scratchpad permission is insufficient. This documentation-only assignment authorizes changes solely to this decision log, not the roadmap, status, acceptance matrix, phase documents, source, tests, runtime configuration or evidence artifacts.

## P2.2 ordinary focus revision — 29 October 2026

Engineering decision under the owner's **P2.2 OWNER-AUTHORIZED COMPLETION MANDATE** (attachment `d75a64c8-8c8b-4ea8-b07d-5085343eb7fa`): permit C17's single ordinary `SetForegroundWindow` request for an exactly bound newly created practice window. This explicitly revises the prior assignment's blanket API prohibition for this disposable P2.2 session only. It is an implementation decision under the owner's delegated revision authority, not independent human review or general desktop permission.

Microsoft documents foreground eligibility restrictions and possible refusal even when conditions are met: [SetForegroundWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow). The existing C17 contract already specifies this request followed by foreground readback. Substituting an activation bypass is unnecessary and prohibited. Keep `AttachThreadInput`, desktop switching, elevation, foreground-lock changes, simulated Alt tricks, repeated focus requests and forced reacquisition disabled.

Before the one request, validate owner/target identity, session/desktop, freshness/geometry, exact approval and physical conflicts. Require both nonzero API return and independent foreground equality. Refusal or post-request drift stops/revokes the session; a successful return alone is not verified task success. Existing controller postconditions and cleanup remain mandatory. Native TOCTOU and D1 limits remain; no promise of zero post-Stop effects.

The new completion mandate authorizes a fresh bounded two-owned-window session, synthetic operations and target-only observation. Its recorded scope is `p22-two-owned-windows-ordinary-focus-v2`: one use, 15 minutes, 100 admissions including a four-admission cleanup reserve, and a 24-hour start/absolute expiry window. The owner-side runner checks reviewed source hashes and its own matching desktop/non-elevated token before consuming that record. Expiry, source drift or context failure cannot mint a new approval. Previous consumed records and uncertainty remain unchanged. No production registration or later milestone is authorized.

Native physical-conflict evidence requires the owner to hold then release Shift only when prompted by the owned practice window; automation never injects a deliberately stuck modifier. Missing participation fails that acceptance case. Native focus-negative cases reject a real owned window that lost foreground during the authorized two-window switch and a mismatched owned Focus target before dispatch. OS-generated focus refusal is not artificially forced; deterministic API-refusal tests remain labeled inert, and any naturally occurring refusal aborts the native run.
