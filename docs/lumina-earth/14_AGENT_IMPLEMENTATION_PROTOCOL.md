# Lumina Earth — Coding-Agent Implementation Protocol

**Version:** 0.1.0 | **Intended for:** Gemini 3.8 Flash High in Antigravity or another coding agent

## Mission

Implement Lumina Earth incrementally according to the accepted milestone and this documentation pack. Preserve the full feature vision but do not expand the currently assigned scope.

## Mandatory first task: read-only reconnaissance

Before changing code:
1. Confirm repository root, branch, working tree and current commit.
2. Read repository instructions and relevant architecture docs.
3. Identify actual Electron renderer, backend, dependency injection, event bus, skill/tool execution, persistence, TTS/voice and test patterns.
4. Identify existing map/geographic functionality, if any.
5. Map proposed components to existing modules.
6. Identify conflicts, missing dependencies and architectural risks.
7. Inspect package manifests and existing versions before proposing new dependencies.
8. Check current tests and document baseline failures.
9. Do not modify files during reconnaissance.
10. Produce an integration report and wait for explicit assignment/approval before implementation.

## Implementation rules

- One explicitly assigned milestone at a time.
- Do not rewrite unrelated subsystems.
- Do not introduce a second DI container, event bus, memory engine or provider abstraction if an existing one can be extended safely.
- Use the smallest coherent vertical slice.
- Keep provider responses behind adapters and normalized schemas.
- Use typed command contracts and explicit failure states.
- Never invent provider capabilities, API response fields, URLs, pricing or licensing terms.
- If a provider fact is uncertain, verify current official documentation and record the source/date.
- Do not put secret credentials in code, logs, screenshots or output.
- Add tests with each behavior.
- Do not claim tests passed unless the command ran and the actual exit status/result was inspected.
- Preserve unrelated working-tree changes.
- Do not commit, push, or modify roadmap status unless explicitly authorized by the task.
- Stop at the assigned milestone's boundary.

## Required implementation report

1. Summary of work.
2. Files changed and purpose.
3. Design decisions and alternatives rejected.
4. Exact commands run.
5. Test output/counts and any failures.
6. Manual verification performed.
7. Provider/API/terms changes or assumptions.
8. Security/privacy review.
9. Acceptance criteria table with PASS / FAIL / BLOCKED / NOT TESTED and evidence.
10. Remaining risks and next recommended task.

## Stop conditions

Stop without broadening scope when:
- Repository architecture contradicts the proposal.
- A provider's licensing or API behavior is unresolved.
- Credentials/permissions are missing.
- A test failure suggests unrelated regressions.
- The task requires an owner decision.
- The milestone acceptance gate cannot be met safely.

## Definition of done

A milestone is complete only when code, tests, documentation and acceptance evidence agree. A partially implemented feature must remain explicitly partial; do not mark it verified based on UI appearance alone.
