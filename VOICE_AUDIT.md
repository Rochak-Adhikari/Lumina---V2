# Gemini-only voice audit

Scope: Gemini Live is the only speech understanding and speech output provider. No whisper installation, local TTS, browser recognition, or alternate paid provider is activated. Existing provider interfaces, runtime states, tools and worker architecture remain in place.

## Changes

Removed continuous hands-free and local speech settings and their active frontend paths. Talk connects to the configured Live provider before requesting microphone capture. Connection attempts time out after twenty seconds. Capture closes at the utterance endpoint, manual finish, cancellation, page hiding, disconnect, or provider failure. Capture has a sixty-second upper bound and a ten-second no-speech endpoint. Late microphone acquisition after cancellation releases its tracks.

Microphone acquisition uses an exact device ID. A single explicitly identifiable internal microphone may be selected automatically; Bluetooth/headset devices are excluded from automatic selection. Otherwise the user must select a device. Refreshing device names no longer opens the default microphone. Browser permission may hide labels; this is reported instead of guessing a device.

Endpointing uses Gemini's provisional input transcript when available: 1.1 seconds of silence for ordinary speech, 2 seconds after continuation words, immediate ending on recognized stop/hang up. There is no local provisional transcription job. Native Gemini audio remains streamed; LUMINA does not synthesize or segment it into local sentence jobs.

## Evidence

Full regression before the final connection-timeout and acquisition-race hardening: 62 tests passed in 20.26 seconds. Focused checks after hardening are recorded in the delivery response. Browser tests use synthetic media and a fake Live provider, not physical hardware or cloud inference.

## Limitations and acceptance gaps

Physical microphone opening, Bluetooth playback quality, real Gemini authentication/quota/audio and subjective endpoint latency have not been verified in this change. No microphone capture or cloud inference is performed automatically on application startup; configured support is not a claim of provider health. The existing capabilities endpoint still reports structural Live support, while runtime connection state reports actual session status.

Because the microphone is closed after capture, spontaneous spoken interruption during playback is impossible without opening it again. Press Talk to interrupt and start a new exchange, or press Stop. This is intentional compliance with the no-always-open microphone policy.

Audio streams from the start of the explicitly activated capture, preserving the first phoneme without a VAD-triggered start. There is no exact 0.35-second pre-roll trim. Sub-0.3-second noise cannot be retracted once streamed to Gemini; complete noise rejection is not claimed. Linguistic endpoint extensions depend on timely Gemini input transcripts. Native audio failure leaves text available, not a synthesized local fallback. No free-tier billing guarantee is inferred from the configured API key.

The Gemini-only implementation is tested locally but full live acceptance remains outstanding. Earlier documentation about hands-free or local speech fallback is superseded by this audit.
