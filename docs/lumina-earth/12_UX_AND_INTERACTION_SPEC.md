# Lumina Earth — UX and Interaction Specification

**Version:** 0.1.0 | **Status:** Proposed

## 1. Workspace

Suggested layout:
- Main canvas: 3D globe or Street Mode panorama.
- Context panel: selected place, coordinates, local time and relevant information.
- Layer control: base imagery, terrain, weather, time/day-night and available advanced layers.
- Search: place query with disambiguation.
- Waypoint drawer: saved places and collections.
- Weather panel: current conditions, hourly/daily forecast, source timestamp and refresh state.
- Voice status: listening/processing/executing/completed/failed/cancelled as consistent with existing Lumina UI.

Adapt visual language to the current Lumina design system rather than introducing a second design system.

## 2. Modes

### Globe mode
- Orbit/zoom controls.
- Search and fly-to.
- Waypoint selection.
- Layer toggles.
- Weather and place panels.
- Current location only if permission is granted.

### Street mode
- Panorama fills the main canvas.
- Orientation controls and available linked movement options.
- Current panorama/location indicator where available.
- Exit-to-globe action.
- Visible indication when the selected area has no coverage.

### Tour mode
- Tour stop list and current stop.
- Play/pause/stop and next/previous.
- Optional narration setting.
- Stop on unavailable content or follow a documented skip policy.

## 3. Voice command examples

- “Show Tokyo.”
- “Zoom in.”
- “What time is it there?”
- “What's the weather here?”
- “Compare weather in Kathmandu and Tokyo.”
- “Save this place as Dream Destination.”
- “Enter Street Mode.”
- “Look left.”
- “Move forward twice.”
- “Stop the tour.”
- “Return to the globe.”
- “Show my saved places.”

The model maps utterances to typed commands; it does not manipulate arbitrary UI selectors.

## 4. Interaction semantics

- **Look left/right/up/down:** change panorama orientation.
- **Move forward/backward:** traverse a provider-returned link if available.
- **Turn left/right:** potentially ambiguous; in Street Mode, clarify whether the user means look/rotate or choose a linked street path unless the UI context establishes the intended meaning.
- **Go to a place:** resolve search result, ask clarification if ambiguous, then fly-to.
- **There/here:** use the active Earth context only if fresh and unambiguous.
- **My location:** require location permission and a valid current location result.

## 5. States

Every remote-data panel should support:
- Idle.
- Loading.
- Success.
- Partial data.
- Stale data.
- No coverage/not found.
- Offline/provider failure.
- Rate limited.
- Cancelled.
- Permission denied (where applicable).

## 6. Spoken responses

Keep responses concise and grounded. Examples:
- Success: “I've moved to the next available panorama.”
- No link: “There's no forward panorama link available from here.”
- Stale data: “I have a cached forecast, but it may be out of date.”
- Ambiguous place: “I found multiple places with that name. Which one do you mean?”
- Weather provider failure: “I couldn't retrieve current weather for this location.”

Never speak an expected result as though it were confirmed before execution.

## 7. Motion and responsiveness

- Camera transitions should be interruptible.
- New destination requests should supersede previous camera transitions.
- Avoid loading every advanced layer at startup.
- Provide reduced-motion behavior where feasible.
- Keep globe rendering isolated from voice/TTS processing.
