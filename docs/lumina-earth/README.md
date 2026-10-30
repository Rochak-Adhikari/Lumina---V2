# Lumina Earth — Project Documentation Pack

**Status:** Planning baseline  
**Version:** 0.1.0  
**Prepared:** 2026-10-28  
**Implementation status:** Not verified against the current Lumina repository

## Purpose

Lumina Earth is a voice-first, interactive geographic workspace for Lumina. It combines a 3D Earth, geographic search, saved places, weather intelligence, street-level panorama navigation, time/day-night information, terrain, routes, guided tours, and optional scientific/live-data overlays.

This pack defines product intent, architecture boundaries, requirements, milestone sequencing, contracts, data models, safety/privacy expectations, and verification criteria. It is intended to be placed under the Lumina repository after an owner-approved path is chosen.

## Important caveat

These documents are a **proposed specification**, not a claim that the existing repository has been inspected or that any feature is implemented. Before coding, the assigned agent must inspect the actual repository, identify existing frontend/backend/DI/event-bus/tool/persistence conventions, and submit a compatibility report. Do not replace existing architecture merely because this pack proposes a component name.

## Documents

- `01_PRODUCT_REQUIREMENTS.md` — product vision, users, scope, outcomes, non-goals.
- `02_FEATURE_CATALOG.md` — all 27 agreed feature concepts and capability boundaries.
- `03_SYSTEM_ARCHITECTURE.md` — component boundaries, data flow, runtime responsibilities.
- `04_FUNCTIONAL_REQUIREMENTS.md` — testable functional requirements.
- `05_NONFUNCTIONAL_REQUIREMENTS.md` — performance, reliability, security, accessibility.
- `06_ROADMAP_AND_MILESTONES.md` — dependency-ordered delivery plan and exit gates.
- `07_API_AND_COMMAND_CONTRACTS.md` — proposed typed Earth command and service contracts.
- `08_DATA_MODEL.md` — proposed entities and persistence rules.
- `09_PROVIDER_AND_LICENSING_STRATEGY.md` — provider-selection criteria and integration strategy.
- `10_SECURITY_PRIVACY_AND_SAFETY.md` — location, secrets, proactive notifications, trust boundaries.
- `11_TEST_AND_ACCEPTANCE_PLAN.md` — automated, integration, manual and release checks.
- `12_UX_AND_INTERACTION_SPEC.md` — workspace, modes, voice interaction, failure states.
- `13_RISK_REGISTER.md` — major risks, mitigations and decision points.
- `14_AGENT_IMPLEMENTATION_PROTOCOL.md` — instructions for Gemini/other coding agents.
- `15_DECISION_LOG.md` — decisions to confirm; unresolved choices are not silently treated as settled.

## Recommended use

1. Copy this folder into a proposed docs location, e.g. `docs/lumina-earth/`, only after confirming repository conventions.
2. Ask the implementation agent to perform a **read-only repository reconnaissance** and produce a mapping from these proposed components to existing code.
3. Resolve P0 decisions in `15_DECISION_LOG.md`.
4. Implement one milestone at a time. Do not start P2/P3 implementation while P1's exit criteria are failing.
5. Update roadmap status only with evidence: changed files, commands run, results, and known gaps.

## Status vocabulary

- `PROPOSED` — in this pack, not yet owner-approved.
- `ACCEPTED` — explicitly approved by the project owner.
- `IN_PROGRESS` — implementation is underway.
- `BLOCKED` — a concrete dependency or gate prevents progress.
- `VERIFIED` — acceptance criteria passed with recorded evidence.
- `DEFERRED` — intentionally moved later; not deleted from the product vision.
