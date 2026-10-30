# Cloud Phase 2 implementation and evidence

Scope: supervised outbound Windows connectors for the approved single-owner Cloud Core. The owner accepted responsibility for the earlier public-cloud setup and explicitly authorized this phase before those external checks were complete. No Phase 3 work, real cloud deployment, personal-memory upload or credential setup was performed.

## Delivered

- Additive device registry migration, independent pairing keys, named PC/laptop identities and measured last-contact status.
- Owner-authenticated proposals and immutable, explicitly approved device requests, with per-device queues, leases and fenced receipts.
- Device challenge signatures, short-lived bearer credentials, revocation, origin isolation and bounded request rates.
- Outbound Windows connector integrated into the existing local server lifecycle. No exposed Windows listener or remote shell.
- Current-user DPAPI protection for the private key and durable local execution journal, atomic saves and exclusive profile ownership.
- Seven bounded local capabilities through the existing tool registry; workspace/secret restrictions remain authoritative. Remote app launching cannot start a terminal, interpreter or coding agent.
- Local execution approval plus separate reviewed disclosure of results. Results are not automatically uploaded when a file is read.
- Cloud Connected devices and Windows Settings controls; shared cloud conversation link; phone-width layout.
- Existing event replay extended with device lifecycle events. Private results and pairing secrets are excluded from events.
- Conservative crash, cancellation and restore handling. Uncertain effects do not replay, and restored devices need owner approval again.
- Optional connector dependency manifest and inclusion in future portable builds. Existing installed packages remain untouched.

## Verification

Final integrated Windows regression: **1,232 passed, 3 skipped**, in 145.96 seconds, using an isolated test memory database. The focused cloud/device suite completed with **187 passed, 1 skipped**. The registry's standalone suite completed with **61 passed**. No tests failed in these final runs. `git diff --check` and the PowerShell parser check for the changed portable build script also passed.

The real Chromium test exercised the cloud HTTPS UI and the actual local Windows UI together. It created a pairing invitation, enrolled a Windows endpoint, approved its fingerprint, submitted a machine-information request, approved execution locally, reviewed the result locally and explicitly shared it. The cloud received real machine information, including operating system and CPU count. The connector used verified HTTPS with a test-specific trust anchor; production certificate verification was not disabled. Identity sessions and reasoning were synthetic test fixtures, not a live OIDC account or Gemini session. Browser audio used fake devices; this was not a physical microphone test.

The browser also checked conversation persistence after reload, durable reminders, logout, a 390-pixel mobile viewport and absence of page errors. Generated screenshots were visually inspected. An actual Windows DPAPI round trip verified the saved key was not plaintext and that a second profile owner was refused.

State tests cover independent devices, offline queues, duplicate requests/results, wrong keys and replay, stale/cross-device fences, delayed consent, explicit refusal, failed disclosure, lost receipts before and after begin, restart recovery, cancellation, byte limits, secret/path exclusions and atomic migration rollback. Backup restore tests prove device credentials are invalidated and unfinished snapshot commands cannot replay while the existing core identity is preserved. Existing Phase 1 tests retain conversations, approved memory and completed reminders across restore.

## Changes by file

New `lumina/device_protocol.py` defines the platform-neutral versioned capability and signature contract. New `lumina/device_connector.py` implements Windows key/journal storage, scoped tool dispatch, outbound transport, local approval, disclosure and cleanup.

New `lumina/cloud/devices.py` and `lumina/cloud/migrations/002_devices.sql` own durable device identities and commands. New `lumina/cloud/device_routes.py` separates owner and device APIs. Changed `lumina/cloud/server.py` adds the device authentication boundary and routes. Changed `lumina/cloud/runtime.py` adds proposal/inspection tools and conservative recovery. Changed `lumina/cloud/operations.py` invalidates device authority and pending work when restoring a backup.

Changed `lumina/server.py` attaches the optional connector to local startup/cleanup and the existing protected local API. Changed `web/app.js` initializes the local panel. New `web/device-connector.js` provides pairing and local approval. New `web/cloud-devices.js`, changed `web/cloud.js` and `web/cloud.css` provide the cloud device controls within the existing interface.

New `requirements-device.txt` contains the optional cryptography dependency. Changed `scripts/build_desktop.ps1` includes it in future portable builds. Changed `.gitignore` excludes encrypted connector profiles and includes the new reports. The Phase 1 documentation now distinguishes its historical scope from the newly authorized connector phase.

New tests: `test_cloud_devices.py`, `test_cloud_connector.py`, `test_cloud_device_transport.py`. Updated `test_cloud_browser.py` exercises actual paired UI/transport; `test_cloud_core.py` expects the newly available connector capability. The separate prior Phase 1 changes to `lumina/tools.py`, `lumina/tool_contract.py`, `lumina/continuity/repository.py` and cloud files remain preserved; they were not reverted or confused with this phase's work.

## Outstanding deployment acceptance and limits

No actual Oracle instance, public TLS/domain route, real OIDC login, live cloud Gemini call, phone on another network or PC-off acceptance was tested here. Those checks remain the owner's deployment work described in CLOUD_PHASE2.md and CLOUD_CORE.md. Existing local regression tests passed, but physical microphone, speaker, camera and interactive Claude authentication were not re-tested by a human in this phase. No new portable executable was built or signed.

Devices must be online with their existing LUMINA backend running. This does not install an auto-start Windows service. Local approval and separate result disclosure are mandatory; unattended device operation is not part of this phase. A cancellation after begin cannot undo an effect already dispatched to Windows and is reported as unknown. A revoked identity remains auditable; renewing it requires a new connector profile. Native Android tools, automatic voice/conversation handoff, bidirectional memory synchronization, remote Claude execution and cloud coding agents are not implemented.

The full-suite skips are the POSIX-only file-ownership check on Windows, optional NetworkX absent in the interpreter, and an opt-in disposable Windows UI Automation fixture. Skips are not passes. Cloud/browser tests use isolated state and synthetic credentials and do not prove public deployment or free-tier availability.
