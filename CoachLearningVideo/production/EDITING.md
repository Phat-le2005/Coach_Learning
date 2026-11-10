# MathMate video source

1080p / 30 FPS / 180 seconds. `public/audio/narration.mp3` follows the user-selected unpaced narration, with only the two brand-name clips replaced to say Math Mate. The other six voice clips are preserved. Provenance and checksum are in `audio-selection.json`. Do not substitute the paced narration variant.

Run `node render.cjs still 0 5370` to check title and closing. Run `node render.cjs render` only after the real clips and captions are ready. It validates that every clip exists, probes source durations, bundles, then exports H.264/AAC MP4 in `out/`.

`src/manifest.json` controls eight real recorded shots. Source `trim` is seconds, `rate` is playback speed; default 1. If a recording is shorter than its shot, the final authentic frame is held. Prefer trimming/guided pacing in the captured footage rather than speeding up visible interaction. Parent may edit start/duration for cut alignment. Speech remains unchanged.

Expected footage: `plan.mp4`, `knowledge.mp4`, `theory.mp4`, `mathview.mp4`, `handwriting.mp4`, `mobile.mp4`, `ocr.mp4`, `feedback.mp4`, `teacher.mp4` under `public/footage/`. The synchronized mobile recording appears as a small framed inset during handwriting. Both handwriting clips use the same computed speed to fit the 13-second writing shot. If accelerated, the video labels this. `public/stills/feedback.png` must be a real UI screenshot; it is used behind opening and closing titles.

`public/captions.json` is an array of `{startMs,endMs,text}` in the final 180-second timeline. Captions are rendered visibly in the MP4. Keep them faithful to the selected audio. App screenshots, videos and cursor movements must come from the functioning product; do not synthesize grading results or replace errors with fixtures.

Fonts are Be Vietnam Pro with the OFL license in `public/fonts/`. Dependencies are provided by the existing adjacent toolchain via local junction; no private application environment is copied here.
