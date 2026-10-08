# LUMINA Windows desktop

The Win32 WinForms shell uses WebView2 and stable identity `LUMINA.Desktop`.
Build with `powershell -File scripts/build_desktop.ps1 -Mode Portable -AllowUnsigned`.
The executable is `dist/LUMINA-Portable/LUMINA.exe`; move the entire directory,
not just the executable. WebView2 Runtime must be installed. Python and .NET are bundled.
Development mode uses external, build-generated runtime.json paths and requires
the existing virtual environment. Portable mode uses relative paths and a clean
example configuration; configure Gemini locally without distributing credentials.

The launcher validates runtime files and imports using the configured Python,
then reads host and port from LUMINA configuration. It accepts only loopback.
GET /health must identify LUMINA API 1 as ready before any WebView navigation.
A foreign listener is rejected. A session-local Windows mutex prevents duplicate
desktop launchers. The process handle is retained for an owned backend; private
stdin shutdown runs aiohttp cleanup, with an eight-second termination fallback.
Pre-existing healthy servers are never stopped by the launcher. Startup is bounded,
and runtime health failure presents an error without automatic restart loops.
Quit and the native close control, including Alt+F4, use normal window lifecycle.

Navigation is restricted to the local origin. External URLs require confirmation
before opening the ordinary browser. Host objects and WebView host messaging are
disabled. Local actions continue through the Python action policy. Microphone is
disabled until enabled in the native menu and approved in the permission prompt.
Camera and other unexpected permissions are denied. Diagnostics inspect available
Windows ConsentStore settings and distinguish unknown values from denied access.
An unpackaged Win32 app may have no per-app consent record; this is not an MSIX
package and does not claim MSIX permission behavior. Device, driver, browser policy
and Gemini failures still require separate diagnosis.

The build generates seven ICO resolutions, 16 through 256 pixels, from drawing
instructions. No source image is required. Current output is UNSIGNED, confirmed
by Get-AuthenticodeSignature as NotSigned. SmartScreen may warn. No Windows security
settings or root trust are changed. A stable existing certificate can be supplied
with -SigningThumbprint; it must have code-signing usage, a private key and a valid
trusted chain, and the resulting Authenticode signature is verified. Signing with
a real certificate has not been tested here; no suitable certificate was available.
The script does not timestamp signatures or produce an installer/MSIX package.

## Verified on this machine

scripts/verify_desktop_package.py copies the portable folder into a new temporary
location, runs from the Windows directory, and tests an isolated port. Evidence is
in artifacts/desktop-package-verification.json. Owned startup, graceful cleanup,
existing-server reuse and preservation, foreign-port rejection, and a real visible
WebView loading the connected LUMINA page passed. WebView2 151.0.4129.101 was found.
No original repository root is required by the relocated runtime metadata.

## Remaining acceptance work

Explorer double-click and manual Alt+F4, icon appearance, real microphone capture,
Bluetooth selection, native permission prompts, and Gemini connectivity have not
been manually verified. Automated window verification closes the real window via
its normal Close method. The SDK emits an unused WebView2 WPF WindowsBase reference
warning; compilation and the WinForms live test succeed. Production certificate
signing remains untested. These limits mean packaging is not fully accepted yet.
Existing build directories may retain old bytecode or symbols; use a fresh output
directory for distribution. The build excludes source bytecode and disables new
debug symbols, and does not require those old files at runtime.
