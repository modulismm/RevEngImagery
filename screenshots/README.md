# Screenshots

Drop UI captures here. Full resolution -- `Cmd+Shift+4` then Space grabs a clean
window without the desktop behind it.

Most useful, roughly in order:

| # | Capture | Why it matters |
|---|---|---|
| 1 | **Create / editor**, sound-zone panel open | Densest screen, hardest to infer from class names. Shows how `reverbLevel` / `pitch` / `highFreq` / `midFreq` / `lowFreq` / `isReversed` are actually presented. |
| 2 | **Canvas with zones placed** | `x`/`y`/`radius` are known to be percentages, but not whether a zone renders as a visible circle, a glow, or is invisible until hover. |
| 3 | **Gallery** and **PublicGallery** | Pins down what `GalleryConfig` actually controls -- `lobby_cols`, `lobby_justify`, `title_align`, `accent_color`, fonts. |
| 4 | **Home / landing** | |
| 5 | **Any modal or dropdown** | Usually stock library components; identifying the library means it can be reused directly rather than rebuilt. |

Two that multiply what can be extracted:

- **A narrow window** (~400px wide) of any screen. The app has only 25 responsive
  utilities total, so what breaks at phone width cannot be inferred -- it has to be seen.
- **A hover state** on a zone or a button. 112 `hover:` utilities do real work here.

Naming: `NN-page-state.png`, e.g. `01-create-zone-panel.png`, `06-gallery-narrow.png`.
