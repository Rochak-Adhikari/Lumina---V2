# LUMINA Cloud Phase 2 — connected Windows devices

This phase extends the existing Cloud Core. It does not replace the Windows application, migrate its private database, or create an Android application. The owner authorized this phase while retaining responsibility for the Phase 1 public deployment and PC-off acceptance tests. Those external tests remain open.

## What is added

The cloud UI has a Connected devices panel. It can pair multiple named Windows installations, show their last contact, prepare and approve requests for one exact device, cancel pending requests and show durable results. Existing conversation, memory, reminders and notifications retain their original APIs and storage.

The Windows Settings panel has a Cloud device connection section. It opens an outbound HTTPS connection to the configured Cloud Core and displays local execution requests. No inbound Windows port, router forwarding, remote shell, cloud administrator key or new microphone permission is added. Pairing is off by default. Closing the Windows backend makes that device offline; the cloud continues independently.

The initial exposed operations are basic system information, workspace filename search, reading bounded text, listing a directory, opening a folder, creating a new directory and opening an approved application. File operations are confined to the existing configured workspace and current path/secret restrictions. Remote app launch is restricted further to Notepad, Calculator, Chrome and Edge, without arguments. Local LUMINA keeps its existing broader desktop capabilities.

Cloud reasoning can inspect devices, propose a typed device action and retrieve an approved result. It cannot approve its own proposal or claim success from a queued request. No model is needed to use the device panel. The cloud and Windows adapters use the existing tool registry, not generated commands.

## What remains deliberately separate

Your shared cloud conversations and approved memory belong to the Cloud Core identity. The Windows connector joins that identity as a named device; it does not upload your local conversation or memory database. Open shared cloud conversation in Settings opens the same authenticated cloud interface used on your phone. Existing local chat and voice continue locally. Automatic voice handoff, merged local/cloud histories, bidirectional memory synchronization, Android hardware access, cloud coding agents, screen streaming and remotely invoked Claude are later work.

This is a supervised connector. Every request requires owner approval in the cloud and approval on the addressed Windows device. Its resulting data stays local until you review the preview and choose Share this result with Cloud Core. Cloud reasoning may subsequently use that shared result. Keep result on this device sends only a refusal receipt. Merely pairing a device is not consent to upload its files. This conservative first boundary means unattended desktop operation is not yet available.

## Manual setup

1. Finish the existing Cloud Core deployment in `CLOUD_CORE.md`: a persistent Linux data volume, HTTPS domain, exact-owner OIDC login and your explicitly configured reasoning provider. Keep the original owner and assistant IDs. Do not initialize another database over the existing one. Confirm cloud conversations and reminders from your phone on mobile data before adding devices.
2. Before updating an existing cloud installation, take an encrypted backup using the documented maintenance command. Deploy the updated application code and web assets, preserving the mounted cloud data directory and private environment. Restart the existing cloud service. The additive `002_devices.sql` migration applies automatically at server creation; it does not change continuity's migration history or the original Windows database. Docker deployments need a rebuilt image because their code is copied into the image. Keep the persistent volume.
3. Update the Windows installation's application code and web assets together. For a source checkout, install the optional connector dependency with the same interpreter used to start LUMINA: `.\.venv\Scripts\python.exe -m pip install -r requirements-device.txt`. Start LUMINA normally. Do not install into an unrelated Python interpreter. New portable builds include this dependency through the existing build script; an old portable executable/package does not update itself.
4. In the authenticated cloud UI, open Connected devices. Enter a recognizable device name, such as Home PC, and select Create pairing code. The code expires in ten minutes and is shown once. If its response is lost, create a new invitation; the old unused invitation expires. Never put a code in a chat, repository or screenshot you intend to share.
5. On that Windows machine, open Settings, Cloud device connection. Enter the exact HTTPS cloud address and pairing code. Pair this device. Compare the complete fingerprint shown locally with the pending device in the cloud panel. Approve matching fingerprint only when both match. The connector will establish its authenticated session automatically.
6. Repeat pairing on your laptop using a new invitation and a distinct name. The two devices have independent private keys and command queues. Keep each local LUMINA backend running for it to be reachable. Windows autostart or a background Windows service is not installed by this phase.
7. On your phone, sign in to the same cloud URL. Select the target device, choose Inspect machine and Prepare request. Review the exact target/action and Approve this exact request. On that Windows machine, choose Allow this local action, inspect the result, then Share this result with Cloud Core. The cloud command must reach succeeded and contain real system information. This path also works when online reasoning is disabled.

No new domain, tenancy, public firewall rule or billing configuration is created by these changes. Only the existing cloud HTTPS listener is needed. A valid trusted TLS certificate is required; production connector code does not disable certificate verification or accept redirects. Oracle hosting still has the limitations documented for Phase 1 and is not guaranteed 24/7 availability.

For a new local portable package, the existing PowerShell build entry point is `scripts/build_desktop.ps1 -Mode Portable -AllowUnsigned`. This explicitly creates an unsigned development build in a new output folder; it does not replace your existing installation, bypass SmartScreen or sign the application. Use your existing trusted signing configuration instead when appropriate. The build requires the existing .NET/Python build prerequisites and downloads portable dependencies. Its updated dependency list now includes `requirements-device.txt`. Preserve your old portable directory and private settings while testing the new one. This implementation run did not produce or sign a new portable executable.

## Simple manual checks and prompts

Use “Which of my devices are connected?” in cloud chat after both machines are paired. For ambiguous names LUMINA should ask which device. Use “On Home PC, propose a request to inspect its machine information.” The reply should describe a proposal, not say that the action already happened. After sharing its result, ask “Summarize device request REQUEST_ID in one sentence.” Copy the actual request ID from the panel.

Create a harmless text file within the configured Windows workspace. In the cloud panel choose Read workspace text file with its relative filename. Verify nothing is read before local approval, and nothing is disclosed before sharing. Choose Keep result on this device once and verify the cloud receives no file content. Attempt `.env`, an outside path, an alternate stream, a linked folder and a terminal application: these must not become successful remote operations.

Disconnect the laptop in its local Settings. Approve a cloud request for that laptop. It should remain queued rather than run on the PC. Reconnect the laptop and approve locally. Requests expire after 24 hours. Close and reopen a client: history, request IDs, states and approved results should still be present.

Cancel a queued request and verify it cannot run. Cancel after execution begins: the state must be unknown, because cancellation cannot reverse a local effect. Inspect the addressed machine before submitting a new request. A shutdown, crash, timeout or lost execution lease must never cause automatic re-execution of an uncertain action.

Restore an encrypted backup into a fresh cloud directory following Phase 1's procedure. Re-sign in. Previously active devices must await fingerprint approval again. Pending snapshot commands become cancelled; running snapshot commands become unknown. Old tokens must fail, while completed reminders remain completed. Reapprove the stable device identity, then submit a new harmless request.

Finally shut down Windows completely and use the phone over another network. Cloud conversations, approved memory and reminders should still work. The Windows device should be offline and its new request should wait. This is a deployment acceptance check; simulated devices or localhost HTTPS do not prove it.

## API and event contract

Owner operations remain under `/api/v1`, using the existing exact-owner OIDC session, HTTPS, Secure/HttpOnly cookie, Origin check and CSRF token for mutations. Device bearer tokens cannot authorize these routes.

| Method/path | Contract |
| --- | --- |
| GET `/api/v1/devices` | Safe device identities plus the latest 100 commands |
| POST `/api/v1/devices/invitations` | `{name}` plus Idempotency-Key; one-time code and expiry |
| POST `/api/v1/devices/{id}/approve` | Empty object; approves the fingerprint the owner reviewed |
| POST `/api/v1/devices/{id}/revoke` | Empty object; revokes tokens and fences unfinished work |
| POST `/api/v1/device-commands` | `{device_id,tool,args}` plus Idempotency-Key; creates awaiting_owner |
| POST `/api/v1/device-commands/{id}/approve` | Empty object; queues the immutable request |
| POST `/api/v1/device-commands/{id}/cancel` | Empty object; cancels pre-execution work, marks running outcome unknown |

Device protocol routes use `/device/v1`. Browser Origin/cookie requests are rejected on this boundary. The enrollment code is not a long-lived credential. The Windows endpoint generates an Ed25519 key locally; only the public key reaches the cloud. Its fingerprint is SHA-256 of the raw public key.

| POST path under `/device/v1` | Contract |
| --- | --- |
| `/enroll` | `{code,public_key}`; public key is standard padded base64 of 32 raw bytes; returns pending device. Same code/key can recover a lost receipt. |
| `/challenge` | `{device_id}`; approved devices receive a single-use nonce valid for 30 seconds. |
| `/authenticate` | `{device_id,nonce,signature}`; signature is standard padded base64 Ed25519 over UTF-8 `LUMINA-DEVICE-V1\n{public_origin}\n{device_id}\n{nonce}`. Returns a 10-minute bearer credential. |
| `/heartbeat` | `{}` plus bearer token; updates last_seen, renews a lease and returns at most one command for this device. |
| `/command` | `{id}` plus bearer token; only this device's command is readable. |
| `/begin` | `{id,fence}` plus bearer token; last server-side check before execution. Valid claimed work becomes running. Duplicate begin is refused. |
| `/finish` | `{id,fence,status,result}` plus bearer token; bounded JSON receipt. Identical repeated completion is safe; conflicting or stale completion is refused. |

Opaque invitation, challenge and session credentials are stored as hashes on the cloud. Challenges bind the origin, device and key, and are consumed even on a bad signature. Revocation invalidates active credentials immediately. HTTPS redirects and ambient proxy credentials are not followed by the connector. Windows keys and the receipt journal use current-user DPAPI, not plaintext storage. Their location is under LocalAppData/LUMINA/device-connector, scoped to the current workspace. Another backend cannot concurrently own that connector profile. Corrupt state fails closed rather than discarding receipts.

`device.*` and `device_command.*` events use the existing version-1 event envelope and replay cursor. Events contain safe state metadata, not pairing secrets or file content. Approved results are fetched through authenticated snapshots. No second event infrastructure is added.

## Durability and cancellation

The command state sequence is awaiting_owner, queued, claimed, running and a terminal state. Terminals include succeeded, failed, declined, cancelled, expired and unknown. Claim fences prevent stale workers from committing. Leases last 30 seconds and are renewed by outbound heartbeat, bounded by the 24-hour command expiry. Claimed work can return to the queue after a lost lease because execution has not been authorized. Running work becomes unknown and is never automatically replayed. Local state is flushed atomically before execution begins.

The Windows endpoint normally polls every two seconds, with failure backoff capped at 30 seconds. Each network operation has a deadline. One local action executes at a time per device; different devices can operate independently. There are at most 16 registered devices, 50 unfinished cloud commands, 100 local journal entries and bounded request/results. Revoked identities remain auditable and count toward the pilot's identity limit. A new identity after permanent revocation currently requires a new connector profile; this phase does not silently erase the prior profile or its receipts.

Cancellation prevents actions that have not passed begin. It stops waiting after begin and reports uncertainty; it is not an undo mechanism and cannot forcibly reverse an already dispatched Windows API/thread operation. Device shutdown cancels owned asynchronous work, closes HTTP resources and releases the profile lock. It never terminates unrelated applications.

## Rollback and limitations

The device migration is additive and keeps Cloud Core's base schema at version 1. Stop the service and back up before rollback. Restoring the older application code disables device routes; it does not require dropping new tables or altering existing conversation/memory records. Do not manually reset fences or edit command status to force execution. Re-upgrade through the same migration; in-flight leases recover conservatively.

Encrypted Phase 1 backups include device state automatically. Service restore invalidates browser sessions, device tokens, challenges and invitations, resets the event stream, fences unfinished work and requires device reapproval. Keep backups and their key independently from the instance. The untouched original Windows database is not a rollback substitute for shared cloud conversation history.

No actual Oracle deployment, public OIDC login, physical phone-network test or PC-off test can be inferred from repository tests. Existing portable installations must be rebuilt or updated deliberately; this source change does not overwrite an installed portable directory. Trusted signing behavior is unchanged. Phone access currently means the cloud web interface, not Android device tools or native push notifications.
