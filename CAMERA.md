# Windows camera capability

`ToolRegistry.camera.capture_camera_frame()` invokes the dedicated
`LUMINA.Camera.exe` application. Python never opens the device. The helper uses
Windows MediaCapture and actual Windows video device enumeration; no ffmpeg,
network listener, authentication protocol or browser camera permission is involved.

The model-facing `capture_camera_frame` tool uses the existing confirmation UI for
one local photograph. A successful response contains metadata only. JPEG bytes are
available in `ToolRegistry.camera.last_frame` for a vision adapter to consume; they
are not sent to Gemini or exposed in state/history. Cloud image analysis is not
automatically enabled by this capture feature. A model must not infer image contents
from the metadata. The next capture replaces the in-memory frame.

Requests and atomic responses use per-request UUID filenames below
`%LOCALAPPDATA%/LUMINA/camera`. The engine creates an expiring request and starts
the helper with its ID. Either process may restart; every new exchange uses a new
ID and an exclusive OS file handle serializes camera ownership. Old artifacts are
removed on the next capture after sixty seconds. Normal captures remove temporary
JPEGs immediately after reading. Local communication relies on the Windows user
profile boundary, not a network authentication scheme.

The helper rejects known virtual device names, ranks enclosure metadata and
built-in/internal names first, and tries remaining physical candidates on failure.
It starts a CPU frame reader, explicitly requests automatic exposure where supported,
and polls new frames and actual exposure values for at most three seconds. MediaCapture
does not expose an exposure-adjusting flag: value stability is an explicitly reported
heuristic, not proof of exposure convergence. The Auto property is not misrepresented
as an adjusting flag. Unsupported controls are reported in the result. Black frames
are rejected, though a genuinely dark scene can also fail this conservative check.

Every attempt disposes its reader, bitmap and capture session. An eighteen-second
helper watchdog exits on a stuck driver, releasing process-owned camera handles;
the engine independently bounds the whole process to twenty-two seconds and kills
only its helper on timeout/cancellation. Idle LUMINA owns no camera process or device.

The desktop build script publishes the helper alongside both builds and signs it
when an explicit trusted signing certificate is provided. The current helper is
unsigned. For a development shell, capability discovery uses the built portable
helper under the project output; the portable app resolves its adjacent camera folder.

Verification: the native helper compiled and ran on this Windows machine. It returned
“No enabled physical camera was found; virtual cameras are excluded” promptly.
Physical JPEG capture, device release/indicator behavior, exposure behavior and black
frame handling therefore remain hardware acceptance tests, not verified claims.
Automated handoff tests exercise independent request IDs, JPEG validation, missing
helper, failure cleanup and no network upload. No camera image was uploaded during
verification.
