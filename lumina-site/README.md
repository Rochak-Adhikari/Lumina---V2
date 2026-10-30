# Lumina — website ("The Loom of Light")

A cinematic, interactive 3D website for Lumina, the personal AI companion. One continuous real-time scene — a loom of light — carries seven chapters: arrival, intent, memory, action, capabilities, a working demo and an explorable finale.

- Creative direction: [docs/CREATIVE-DIRECTION.md](docs/CREATIVE-DIRECTION.md)
- Where every product claim comes from: [docs/CONTENT-SOURCES.md](docs/CONTENT-SOURCES.md)
- Assets: [docs/ASSET-MANIFEST.md](docs/ASSET-MANIFEST.md)
- Test and performance results: [docs/TEST-REPORT.md](docs/TEST-REPORT.md)

This project is self-contained. It does not import, call or modify the Lumina desktop application.

## Run it

Requires Node.js 22.12+ or 24+ (Vite 8 and Vitest 5 engine ranges; built with 24.12).

```bash
npm install
npm run dev        # http://localhost:5183
npm run build      # type-check + production build into dist/
npm run preview    # serve dist/ at http://localhost:4183
npm test           # unit tests (demo engine, sequence math)
```

Browser checks use `playwright-core` with a Chromium that Playwright has already cached on the machine (`%LOCALAPPDATA%\ms-playwright`), or any Chromium given via `CHROMIUM_PATH`. Run them against a running server:

```bash
node scripts/e2e.mjs --url http://localhost:4183/      # 23 end-to-end checks
node scripts/perf.mjs --url http://localhost:4183/     # load, transfer, frame times, heap
node scripts/shoot.mjs --url http://localhost:4183/ --shots "0:0,3:0.5,6:0.5"   # screenshots
node scripts/make-social.mjs                           # regenerate og image + touch icon
```

`scripts/debug-eval.mjs`, `profile.mjs` and `trace.mjs` are developer tools (the first needs the dev server).

## Architecture

```
index.html            all copy and structure; works without JS and without WebGL
src/main.ts           boot order, 3D lifecycle (lazy, lite mode, failure), diagnostics
src/core/store.ts     the single source of shared state + transient events (plucks, cues)
src/core/scroll.ts    the only scroll listener: scroll → camera timeline `t` + chapter progress
src/core/sequence.ts  pure math shared by the HTML action list and the 3D heddles
src/core/quality.ts   GPU/device tier selection
src/world/            three.js scene: ribbon shader, loom builder, keyframes, World runtime
src/ui/               nav, chapter rail, memory inspector, capabilities, explore, settings, sound
src/demo/             scenarios (example data), pure engine (+ tests), console UI
src/audio/            procedural Web Audio engine (loaded on first Sound click)
src/content/          capability statuses, example memories, destinations
```

Key decisions:

- **No framework.** Vanilla TypeScript + Vite. The render loop never passes through a UI framework.
- **One state store, one scroll listener.** Scroll position maps deterministically to a timeline; the camera and every world parameter are interpolated from a single keyframe table (`src/world/keyframes.ts`). Scrolling backwards replays it in reverse; deep links land on the same state.
- **Shared math, not duplicated animation.** The action chapter's HTML steps and 3D heddles both read `loopView()` from `sequence.ts`.
- **Lines, not meshes.** Every thread is a screen-space ribbon (constant pixel width, soft core + halo) in one custom shader. 8 draw calls, no textures, no post-processing.
- **Demand-driven rendering.** Renders on change; ambient shimmer capped (≈20–45 fps by tier); nothing at all in reduced motion while idle; paused when the tab is hidden.
- **Progressive loading.** HTML and text paint first; three.js loads after the `load` event and only if WebGL works; audio loads only on request.
- **Adaptive quality.** Tier from the GPU string and device signals; resolution steps down if frames stay slow; if still slow, a one-time offer to switch to Lite mode.
- **Fallbacks.** Lite mode (Settings) and WebGL failure both show static SVG art; every chapter, the demo and the explore cards keep working. Context loss is handled.
- **Demo engine is pure.** `src/demo/engine.ts` has no timers or DOM; the UI advances simulated time. Fully unit-tested.

## Accessibility and motion

Semantic landmarks and headings, skip link, visible focus, keyboard-operable everything, `aria-pressed` / `aria-expanded` / live regions, 44 px touch targets, text contrast ≥ 5.6:1. `prefers-reduced-motion` is honoured by default (this build machine has it on) and can be overridden in Settings. Sound never starts without a click, has mute and volume, and carries no essential information.

## Before deploying

1. **Domain:** add `<link rel="canonical">`, make `og:image` / `twitter:image` absolute URLs, and add a `Sitemap:` line plus `public/sitemap.xml` once the production domain is known.
2. **Hosting:** `dist/` is a static site; any static host works. Serve `assets/*` with long-lived immutable caching and `index.html` with revalidation.
3. **Personal details:** the footer credits the creator by name (`data-config="creator"` in `index.html`). Keep, change or remove before publishing.
4. **Call to action:** there is deliberately no download, sign-up or waitlist because none exists. If one is created, add it to the hero and footer CTA rows.
5. **Capability status:** statuses come from the project's recorded October 2026 evidence (see CONTENT-SOURCES). Re-check `src/content/content.ts` before publishing.

## Known limitations

- Tested on one machine (Intel UHD 620) in Chromium only; phones were emulated, not physical. Firefox, Safari, screen readers and forced-colours mode were not tested.
- On CPUs roughly 4× slower than this laptop, scrolling stutters (p95 50–100 ms) — the Lite offer is the mitigation.
- The sound design has been verified numerically, not by listening.
- The explore chapter's orbit is limited (±34° yaw, ±16° pitch) by design; there is no free-roam camera.
- The three.js chunk is the largest download (144 KB gz); it is lazy and does not block first paint.
