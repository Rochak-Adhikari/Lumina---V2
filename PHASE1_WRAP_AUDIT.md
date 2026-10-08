# Phase 1 wrap verification — 8 October 2026

This audit supersedes the earlier Gemini-grounded search and portable-build status.
It does not claim that every legacy capability or every hardware/provider combination is proven.

## Changes

Search now uses Tavily's explicitly free keyless HTTP search, without Gemini,
an account, API key, Authorization header, generated answers, or metered fallback.
The former gemini_grounded setting migrates to this provider; explicitly configured
other providers remain respected. Model numbers such as 5700X are preserved in
queries. Responses retain source URLs, provider and retrieval time. Fair-use limits
fail visibly, and requests remain bounded and restricted to public destinations.

Workers now expose Stop selected agent and Remove inactive agent. Each operation
requires a fresh, single-use, exact-task confirmation that expires after 60 seconds.
Stopping verifies the tmux socket, session and pane identity. MSYS glob expansion
is disabled for structured tmux arguments; printable field delimiters replace tabs
that this installed tmux sanitizes to underscores. Native Windows process handles
are retained before termination, including verified descendants, so a vanished
terminal is not mistaken for a stopped native process. Unknown identity fails closed.
Removal requires confirmed inactivity and preserves workspace files and logs.
Persistent agents still survive ordinary LUMINA shutdown.

Voice no longer ends merely because document visibility changes. Explicit Stop,
page closure, disconnection and the existing bounded call/quiet-time policy still
end capture. This does not promise indefinite background microphone access on
every browser or operating-system configuration.

Desktop uses WebView2 SDK 1.0.4258.31, dark native menu/dialog/loading/error surfaces,
dark WebView color scheme and supported DWM caption/border attributes. Builds emit
a dependency/hash/signature manifest and use a fresh output directory. Portable
browser discovery resolves bundled Chromium relative to the packaged Python runtime.
The existing personal portable configuration is copied into the new personal build;
the old distribution is preserved. No credentials are embedded or printed.

## Evidence

The final full regression suite passed 328 tests in 66.50 seconds, including the
native process cleanup and portable browser resolution regression.
Focused lifecycle tests passed, including exact one-use approval and stale identity
rejection. A real isolated tmux session running a harmless Windows Python process
and a native child process were stopped, both process handles signalled termination, and its inactive record was
removed. No existing user agent was selected or terminated.

Live keyless search returned official Microsoft WebView2 links and Australian
Ryzen 7 5700X product sources, including PCPartPicker Australia and Scorptec.
Search evidence is not a guarantee of current checkout prices or stock.

Relocated package verification opens a real native window from the Windows directory,
checks healthy UI loading, starts and cleans up an owned server, reuses and preserves
a pre-existing LUMINA server, and rejects a foreign listener on the selected port.
See artifacts/desktop-package-verification.json and artifacts/agent-cancel-live.json.

The final package was copied to a separate temporary installation directory and
passed these checks again. Its embedded Python also launched and closed the real
bundled supervised Chromium browser successfully, with one real tab. The final
package is dist/LUMINA-Portable-Phase1-Final/LUMINA.exe. It was started from the
Windows directory for the user's physical audio check. The previous distribution
remains untouched.

## Honest remaining limits

The installed Evergreen runtime is 151.0.4129.101. Automatic approval review blocked
the official Microsoft installer action with 'blocked by policy'. The SDK was
updated, but an Evergreen runtime update is NOT claimed. The build is unsigned;
SmartScreen reputation and trusted production signing are not claimed. A non-fatal
WindowsBase reference warning from the WebView2 package remains in build output.

The browser visibility regression uses simulated media and provider output. Actual
human speech, audibility, Bluetooth behavior and a successful fresh Gemini call
while switching applications still require hands-on acceptance. Existing vision,
file, reminder, browser and device evidence is recorded in the preceding audits;
those do not prove universal legacy parity. Browser external commits/downloads,
scanned-PDF OCR and legacy media conversion remain outside the verified feature set.

## Plain-language acceptance prompts

Search the web for official Windows WebView2 documentation.

Search online for Ryzen 7 5700X prices in Australia. Use source links and distinguish
processor-only listings from bundles.

Show my uploaded files. Read the selected uploaded file.

Create a reminder in 30 seconds to check the microphone.

Open Workers, select a disposable agent, Stop selected agent, review its exact
identity and confirm. Confirm it reaches CANCELLED, then Remove inactive agent.

Enable microphone in the desktop application menu, select a real input and output
in microphone settings, start a call, and switch to another application while speaking.
Return and press Stop; confirm the microphone indicator clears.

## Primary references

https://www.tavily.com/blog/What-keyless-search-really-means-for-your-data
https://github.com/tavily-ai/tavily-python/blob/master/tavily/tavily.py
https://www.nuget.org/packages/Microsoft.Web.WebView2/1.0.4258.31
https://developer.microsoft.com/en-us/microsoft-edge/webview2
