# WebView2 audio and graph repair — 8 October 2026

## Confirmed causes

The native shell defaulted its separate microphone-request switch to off. Thus
the web settings discovery call was denied before the user could grant permission.
When enabled, the original code opened a modal dialog synchronously from the
WebView2 PermissionRequested callback, an unsupported reentrant pattern.
The catch-all permission handler also denied Autoplay, which can block Web Audio.

The previous portable package's knowledge endpoint returned zero nodes and
unavailable=true. It contained neither the notes nor graphify-out/graph.json.
The graph engine itself was intact: after packaging the real graph, it rendered
10 concepts and the existing three-or-more-member gold hyperedge hub in WebView2.

## Repairs

Microphone requests are now permitted to ask by default, without granting capture.
A deferred native prompt asks for session consent at the first request. Closing
the app clears consent. The native menu can disable future requests and stops
the active capture/test. Unexpected origins and other capture permissions remain
denied. No unrestricted host bridge, operating-system privacy change, or persistent
permission auto-grant was introduced.

Autoplay permission is allowed only for LUMINA's trusted local origin. Actual
speech remains controlled by the existing spoken-replies and user-call logic.
Speaker selection still reports whether AudioContext.setSinkId is available.
Device discovery releases its temporary stream and saves a uniquely identified
internal microphone only when selection is unambiguous.

Talk is a 39-by-39-pixel microphone button, matching Send. Its accessible name,
tooltip, pressed state, green outline and separate Listening status remain.
Call state changes preserve the SVG rather than replacing the entire button text.

Personal notes/graph packaging is explicit via IncludePersonalKnowledge. Source
paths are made relative, out-of-notes paths and links are rejected, and existing
destination knowledge is never overwritten. Generic builds omit personal data.

## Verification

331 automated tests passed in 68.72 seconds. The earlier large-button test was
updated to the user's new compact-button requirement. New tests cover the icon
surviving start/stop, accessible state, relative graph sources, preserved hyperedges,
outside-source rejection and refusal to overwrite packaged knowledge.

Relocated native package tests passed: owned startup/shutdown, existing-server
reuse without termination, foreign-port rejection, healthy WebView load, 11 graph
nodes including the hub, real WebGL canvas, and equal 39-pixel Talk/Send width.
The captured WebView preview was visually inspected. The updated real desktop
window was opened, audio settings clicked, and its deferred native microphone
permission dialog was visibly confirmed. No synthetic grant was used.

Physical device enumeration and audible output remain pending user approval of
that native prompt. They must not be reported as passed based on browser mocks.
The online provider is currently shown as unavailable; this is separate from
local device discovery and does not prove a Windows permission failure.

The build is unsigned and uses installed Evergreen 151.0.4129.101 with SDK
1.0.4258.31. The runtime installer remains blocked by execution policy as recorded
in PHASE1_WRAP_AUDIT.md. This repair does not claim a system runtime update.

Package: dist/LUMINA-Portable-AudioGraph/LUMINA.exe
Checklist: PHASE1_CHECKLIST.md
Live launcher evidence: artifacts/desktop-package-verification.json

## Official API evidence

https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/threading-model
https://learn.microsoft.com/en-us/microsoft-edge/webview2/reference/win32/icorewebview2?view=webview2-1.0.4129.50
