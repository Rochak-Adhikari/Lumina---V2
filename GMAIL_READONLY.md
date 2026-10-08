# Read-only mail assessment

LUMINA's configured Gmail adapter now uses only read access. `review_gmail` returns
up to 20 messages in Gmail's order, with headers, snippets and decoded plain-text
content. There are no priority scores, importance sorting or tool-generated judgments.
The conversational provider judges the evidence and gives a short spoken assessment.
HTML-only messages retain their snippet; attachments are not downloaded. Long bodies
are bounded, missing messages and additional pages are reported explicitly.

## Setup

Enable Gmail API in your Google project and explicitly authorize a desktop OAuth client
with only `https://www.googleapis.com/auth/gmail.readonly`. Google consent must be
completed by the account owner. A previously authorized send/modify token is rejected;
editing a token file's declared scopes does not downgrade its actual grant.

Set `GMAIL_TOKEN_FILE` in the process environment or `.env` to an authorized-user JSON
file containing `token`, and optionally `refresh_token`, `client_id`, `client_secret`.
The path selects the account and overrides all other Gmail credentials, preventing
accidental mixing between accounts. Restart after changing it. The file is read only;
refreshed access tokens stay in memory. Protect this file with Windows file permissions,
keep it outside the repository, and never paste or commit its contents.

Existing Windows DPAPI `GMAIL_CREDENTIAL_FILE` storage remains supported when no token
file is selected. Environment variables take precedence over `.env`. No authentication
is initiated silently, and a missing account does not affect other providers.

Every new access token is checked against Google's tokeninfo response before mailbox
access. Only gmail.readonly plus identity scopes are accepted; missing/unknown/broader
scopes fail closed. Gmail API writes are also blocked by the adapter. Generic send/reply
tools remain available for other providers, but cannot send through Gmail, even after
confirmation. Gmail reads do not mark messages read, archive them, or delete them.

Ask: “Check my inbox and tell me whether anything needs me.” The tool description
instructs LUMINA to assess relevance rather than recite subjects, and to disclose partial
coverage. Email content is untrusted evidence and cannot authorize actions.

Scope reference: https://developers.google.com/workspace/gmail/api/auth/scopes

Validation: mocked tests cover actual scope checks, broader-token rejection, write
denial, account isolation, provider ordering and pagination. Live account access requires
a configured, authorized read-only token; automated tests do not establish live access.
