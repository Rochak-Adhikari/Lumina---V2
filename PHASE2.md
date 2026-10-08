# Phase Two implementation

The existing Python runtime now owns a provider-independent speaking policy, validated
Windows tools, explicit external-action confirmation, and a provider-neutral worker
coordinator. The configured model IDs and API-key authentication are unchanged.

## Use it

Launch `start.ps1`, open the existing local page, and refresh the browser after an update.
The **Local controls** button works without online reasoning. Enter `system info`,
`open notepad`, `find respiratory`, or `read file README.md`. File content appears in a
separate result view instead of being read aloud. Reading is bounded to 32 KiB and the
configured root. `open file notes.txt` opens a permitted document in its default app.
Application names are allowlisted; model-generated commands are never executed.

`open https://example.com` creates a confirmation dialog displaying the exact address.
Only the authenticated local UI can approve it. Approval expires after two minutes,
is single-use, and cannot change the stored destination. Cancellation, a new chat turn,
or disconnection invalidates pending approval. No deletion, messaging, upload, purchase,
or publishing tool is implemented. Such actions are unavailable rather than implicitly
authorized. Default document applications are Windows-controlled, not sandboxed by LUMINA.

## Spoken behavior

`lumina/speech.py` holds the shared policy. Native Live audio receives it before speech
generation. Text passed into runtime speech announcements is cleaned of visual formatting
and reduced to a brief summary. Already-generated native audio cannot be rewritten by a
text sanitizer; compliance on that path still depends on the configured provider.

Speech remains explicit tap-to-talk by default. Click Speak, wait for Listening, speak, and
click Finish speaking. Settings also provides an explicitly enabled hands-free mode. It uses
local PCM amplitude detection, keeps a short pre-roll so the first word is not discarded,
ends after sustained silence, and interrupts current playback when speech begins. It sends
audio only through the configured voice provider. Microphone selection and its local level
test remain in Settings. An explicitly selected local browser voice can speak runtime
notifications when online voice output is unavailable; it is never an automatic fallback.
No browser SpeechRecognition, Windows speech recognition, or extra cloud speech service is
used.

Worker completion notifications are spoken only through an already connected Live session
when spoken replies are enabled and the interaction is idle. They remain visible in the
conversation without voice. Notification speech cannot execute tools. Full worker reports
are available through Read result and are never automatically read aloud.

## Worker integration

Memory is stored in a private SQLite database under the Windows application-data directory
unless an explicit path is configured. Saving memory requires a trusted local user action.
Searches exclude journal entries by default, and deletion uses a single-use confirmation that
expires after one minute. Deleted records are soft-deleted and restoration requires an explicit
trusted operation.

No production worker is configured or launched by default. Local controls reports this
explicitly. `Runtime(config, workers={"coding": adapter})` accepts a trusted implementation
of `WorkerAdapter` from `lumina/tasks.py`. This is a Python integration seam, not a shell
command or a user-editable executable setting. The adapter must enforce its own permitted
operations and configured cost limits; the coordinator does not sandbox third-party code.

An adapter implements asynchronous `run(session_id, message)`,
`send_message(session_id, message)`, and `cancel(session_id)`. A run returns
`WorkerResult(text, summary, needs_input)`. Only explicit token-protected UI requests start,
message, resume, or cancel tasks. Replies preserve the user's wording. Task state and full
results are in memory and do not survive a server restart. Persistent memory is not added.

Cancellation is confirmed by the adapter. Failed cancellation leaves a distinct state,
permits a retry, and blocks a concurrent resume. Stale results cannot replace a cancelled
turn. Adapter failures produce a brief error rather than exposing tracebacks or secrets.

## Cost and verification limits

Fresh installations default to the local provider, and there is no automatic provider or
paid-service fallback. This does not establish the billing status of an API key configured
by the user. Direct-key authentication cannot guarantee that a cloud request is free.
No Google Cloud CLI or account-billing verification has been reintroduced.

Automated tests cover structured tools, path boundaries, exact confirmation, worker
authorization and lifecycle, result summaries, browser controls, microphone selection,
synthetic PCM capture, playback, and explicit interruption. Physical microphone accuracy,
real cloud speech behavior, and production worker adapters have not been verified.
