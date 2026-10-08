# Conversational Talk control

Talk to LUMINA is a labelled target at least 170 by 52 CSS pixels. After successful
microphone acquisition it becomes green, says End call, and exposes aria-pressed=true.
The status explicitly says the microphone is on even while an answer is being prepared.
The call opens without sending a greeting, text prompt, or empty provider activity.

An explicit call holds the selected microphone for follow-ups. It closes after nine
seconds without initial speech, eight seconds after playback ends without new speech,
or three minutes total. End call, navigation, disconnect, audio error and page hiding
also release it. This replaces the previous one-utterance policy for this explicit call.
No idle background microphone is introduced.

Speech starts and ends are paired by a monotonic client timestamp. Old endpoint events
and tool results cannot finish a newer turn. Resumed speech cancels pending tool tasks
and playback, starts provider activity and sends buffered microphone audio. Gemini's
existing conversation supplies the prior half; its instruction requires a combined
answer when a thought resumes before playback. This semantic behavior still needs a
live provider test, not just mocked protocol coverage. Cancellation cannot undo a tool
operation which already completed.

Echo cancellation and a higher speaking threshold are used, not speaker-based state
inference. Thresholds alone cannot guarantee perfect speaker/user separation on every
device. No shortcut is advertised; configuration explicitly reports talk_hotkey=null.

Five browser/protocol tests pass, covering target size, initial off state, timer
boundaries, stale response timestamps, silent startup, endpointing, follow-up activity
and shutdown. These are automated checks, not an unprompted human usability study.

Human acceptance remains open: give another person the application with only the goal
“Talk to LUMINA,” without pointing at the button. Record whether they find it, understand
when the microphone is on and can end the call. Then test a mid-thought pause, a spoken
follow-up after the first answer, initial silence and silence after playback using the
real microphone/provider. Do not call this human validation complete until it happens.
