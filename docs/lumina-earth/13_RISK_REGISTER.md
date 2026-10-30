# Lumina Earth — Risk Register

**Version:** 0.1.0 | **Status:** Proposed; review at each milestone

| ID | Risk | Likelihood / impact | Mitigation | Gate |
|---|---|---|---|---|
| R01 | Imagery/Street View lacks target-region coverage | Medium / High | Test Nepal and representative global locations before provider commitment; model no-coverage explicitly | P0 |
| R02 | API cost or quota is higher than expected | Medium / High | Estimate usage scenarios; quotas/budget alerts; lazy load; request deduplication | P0 |
| R03 | Provider terms restrict caching, persistence or combined display | Medium / High | Legal/terms review and attribution checklist before implementation | P0 |
| R04 | Renderer degrades voice responsiveness | Medium / High | Separate rendering lifecycle, performance tests, lazy loading and profiling | P0/P1 |
| R05 | Model claims action succeeded when it did not | Medium / High | Typed controller result; speak only confirmed result; acceptance tests | P1 onward |
| R06 | Stale network response overwrites selected context | Medium / Medium | Correlation IDs, cancellation and context-version checks | P1 |
| R07 | Provider schema changes break UI | Medium / Medium | Normalize behind adapters; contract tests; schema validation | P2 onward |
| R08 | Weather is mislabeled as live or certain | Medium / High | Provenance, observation/forecast timestamps and precise UI language | P2 |
| R09 | Street “movement” is mistaken for continuous navigation | High / Medium | Explicit panorama graph semantics and voice wording | P3 |
| R10 | Background notifications become noisy | Medium / Medium | Opt-in, quiet hours, thresholds, dedupe and one-click disable | P4 |
| R11 | Precise location is logged or retained unnecessarily | Low–Medium / High | Data minimization, sanitized logs, no background tracking by default | All |
| R12 | Advanced features expand MVP and block delivery | High / High | Feature flags, milestone ownership, hard exit criteria, no unassigned scope | All |
| R13 | API keys leak in renderer/build output | Low–Medium / High | Backend secret handling, restricted browser keys where unavoidable, bundle scans | P0 |
| R14 | Tracking data is mistaken for authoritative real-time truth | Medium / High | Epoch/freshness indicators and source limitations | P6 |
| R15 | Historical/third-party datasets cannot be redistributed | Medium / High | License validation before caching or display | P0/P7 |

## Risk review rule

At each milestone, update likelihood, impact, owner, mitigation and residual risk. Any unresolved high-impact provider/legal/security risk blocks release of the affected capability.
