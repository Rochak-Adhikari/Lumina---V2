# Creative direction — "The Loom of Light"

## The idea in one line

Lumina turns a person's intent into useful action by weaving it through the capabilities it has, and the result is a cloth that keeps the thread between sessions.

## Directions considered

| Direction | What it would have been | Why it lost |
|---|---|---|
| **Prism** | White light (intent) entering a prism and splitting into actions | Instantly recognisable cliché; says "transformation" but nothing about memory, consent or verification |
| **Orrery** | Capabilities as bodies orbiting a centre | Decorative; orbits imply the assistant circles on its own; weak metaphor for user control and memory |
| **Night desk diorama** | A miniature lit desk where Lumina works | Heavy geometry and textures for an integrated GPU; literal "AI does your computer" imagery the product can't yet back up |
| **Loom of light** (chosen) | Warp strings = capabilities, amber weft = the person's intent, cloth = memory, heddles = the action loop | One coherent object can carry every chapter; maps honestly to the product's real principles; cheap to render as lines |

## Why the loom works

- **Collaboration, not replacement.** A loom needs a weaver. The amber thread (the person) is always the active element; the silver warp (Lumina) gives it structure.
- **Memory you can see and undo.** Each remembered thing is a knot in the cloth. Forgetting visibly unpicks it. Corrections are part of the weave rather than a hidden database.
- **Action with gates.** The action chapter threads the amber line through six heddles — Understand, Recall, Plan, **Approve**, Act, Verify. The approval heddle is the person's colour and the thread waits there.
- **Honest capability status.** Each capability is a string. Working capabilities are solid; in-development ones are dashed; roadmap ones are dotted and dim. The visual language cannot overstate status.
- **Sound as part of the object.** The strings are tuned to a pentatonic harp; selecting a capability plucks it.
- **Performance.** Everything is a line, rendered as screen-space ribbons with no post-processing — this keeps the site at 60 fps on an Intel UHD 620.

## Visual system

| Token | Value | Role |
|---|---|---|
| Ink | `#07080b` → `#222836` | Atmospheric ground |
| Paper | `#ece7dd` / `#b4b0a7` / `#8a877f` | Text (16.6:1, 9.4:1, 5.6:1 contrast on ink) |
| Ember | `#ffad5c` | The person: intent, approvals, primary actions |
| Lumen | `#b9d4ff` | Lumina: capabilities, structure |
| Knot gold | `#f3d38b` | Memory |
| Verified / alert | `#8fd6b0` / `#ff8f80` | Evidence and problems only |

- **Type:** Instrument Serif (display, editorial italics) with Geist (interface) and Geist Mono (system labels). All self-hosted.
- **Materials:** light-emitting threads (additive soft core + halo), dark lacquered beams with a cool rim, a single warm/cool pool of backlight that shifts with the story.
- **Motion principles:** scroll position is the only clock for narrative state; the camera eases between keyframes and breathes slightly when idle; nothing animates that isn't explaining something. Reduced motion freezes ambient motion and snaps the camera.

## Scene design

| # | Scene | Understand | Feel | Visual | Camera | Agency | Transition out | Degrades to |
|---|---|---|---|---|---|---|---|---|
| 0 | Arrival | What Lumina is, that it's a private build | Calm confidence | Loom at an oblique angle; amber voice waveform sweeps in from below | Low three-quarter, loom right of headline | Primary CTA to the demo; nav | Camera swings to the right side | Static SVG strings + thread (Lite) |
| 1 | Intent | You speak naturally; it asks when unsure | Being listened to | Waveform straightens as it enters the weave | Three-quarter view showing weave depth | Illustrative exchange (text) | Drops below the cloth | Text + fallback art |
| 2 | Memory | Memory has sources, confidence, history, and can be forgotten | Trust, control | Cloth grows; gold knots | Low angle across the cloth, text right | Memory inspector: Inspect / Forget / Undo / Restore; hover lights the matching knot; forget unpicks the cloth | Rises to the heddles | Inspector works without 3D |
| 3 | Action | Plan → approve → act → verify; the model proposes, the runtime enforces | Discipline | Thread passes through six eyelets; Approve waits in amber, then turns green | Tracking shot along the heddles (three keyframes) | Scroll-driven, reversible; "Skip this sequence" link | Pulls back to the full instrument | Ordered list is complete without JS |
| 4 | Capabilities | What works, what's in development, what's planned | Clarity | Strings as instrument; status = solid / dashed / dotted | Frontal, wide | Select a capability → its string glows, others step back, string plucks | Steps back and dims | Cards + legend |
| 5 | Demo | How a request becomes a verified result | Competence | World dims to let the console lead; the newest row advances with the run | Low, distant | Full concept console (see README) | Rises to the finished tapestry | Demo is pure DOM; works without WebGL |
| 6 | Explore | Everything connects | Resolution | The finished tapestry | Right of controls; user can orbit ±34° / ±16° | Six destinations (buttons or click on the cloth), drag to orbit, Reset view | Footer | Destination cards work without 3D |

## What was deliberately avoided

Glowing AI orbs, neural-network graphics, robots, endless glass panels, neon gradients, scroll-jacking. The previous crimson HUD look of the desktop app (`LUMINA Cyberpunk AI Command Center.png`, `workspace-panel-check.png`) was inspected and intentionally not inherited.
