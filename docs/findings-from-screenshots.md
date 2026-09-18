# Findings from the UI screenshots

Captured 2026-09-18 (4 screenshots, `screenshots/`). These **correct two earlier conclusions**
that were drawn from the bundle alone.

## 🔴 The French translation exists, is complete, and is not being used

The language selector reads **FR**, yet the UI renders in English: *Sound Gallery*, *Canvas*,
*Gallery*, *Hide Zones*, *Update Canvas*, *Sound Library*, *Add Custom Sound*, *Import Canvas*.

Those strings **are** in the i18n table, and they **do** have good French values:

| key | en | fr |
|---|---|---|
| `canvas` | Canvas | Canevas |
| `gallery` | Gallery | Galerie |
| `hideZones` | Hide Zones | Masquer les Zones |
| `updateCanvas` | Update Canvas | Mettre à Jour le Canevas |
| `exitEdit` | Exit Edit | Quitter l'Édition |

**76 of 79 keys are genuinely translated** (the 3 identical ones -- `nature`, `musical`,
`volume` -- are legitimately the same word in both languages). So the translation work is done
and simply is not reaching the screen: either the selector does not propagate, or these
components never call the translator and render the `en` fallback.

**This corrects the earlier "i18n is clean" note.** Key *parity* was real and is not the issue;
key parity was measuring the wrong thing. Only a screenshot could show this.

Meanwhile, the only French actually on screen is **hardcoded**, bypassing i18n entirely:
`Configurer la galerie et les salles`, `Lien galerie publique`, `Publier dans une salle`,
`Enregistrer un son`, plus the tagline `Interactive Audio Canvas`. So the app shows English
where it has French, and French where it has no translation at all -- exactly backwards.

## ✅ `radius` resolved: a true radius, in absolute CSS pixels

Previously listed as a known unknown. Measured from the resize handle, which sits exactly on
the circle's edge at the same `y` as the centre:

| zone | centre (px) | handle (px) | measured radius | stored `radius` |
|---|---|---|---|---|
| Son 2 | 1614, 1047 | 2079, 1047 | **465** | **464.353** |

Better than 0.2% agreement, so `radius` is a genuine radius in CSS px -- not a diameter, not a
percentage.

**But the data model mixes units:** `x`/`y` are percentages of the image box while `radius` is
absolute pixels. Derived from the two zone centres, the image renders at ~2515×1683 px
(25.15 px per 1% horizontally, 16.83 px per 1% vertically) -- and 2515/1683 = 1.494 against the
source image's 1280/854 = 1.499, so the percentage mapping is confirmed.

**Consequence, inferred but not yet observed:** if the image renders at a different size, zone
positions will scale and their radii will not, so zones drift off their targets. Both screenshots
happen to show the image at the same 2515 px width, so this was *not* directly observed.
**To test: resize the browser window and watch whether a zone stays on its subject.**

## 🟡 The Sound Library panel covers the toolbar

With the panel open (`02-editor-sound-library-open.png`) it overlays *Hide Zones*, *Sounds* and
*Update Canvas* -- "Hide Zones" is visibly clipped mid-word. It is an overlay with no offset or
reflow, so the primary save control is unreachable while choosing a sound. Compare
`03-editor-zones-shown.png`, the same screen with the panel closed and the full toolbar visible.

## Zone rendering spec

Semi-transparent indigo fill with a lighter border; zones overlap and their fills blend
additively. Each zone in edit mode carries three controls:

- a **red circular trash** button, offset above and right of the zone
- a **white circular disc with a pencil** at the exact centre (also the drag handle)
- a **small white dot** on the right edge at centre height -- the resize handle

## Chrome and layout

- **Header:** violet rounded-square logo + "Imagery" / "Interactive Audio Canvas", right-aligned
  `FR` globe selector, then `Canvas` and `Gallery` tabs (active tab = solid violet fill).
- **Editor toolbar:** New · Exit Edit · Hide/Show Zones (eye / eye-off icon) · Sounds ·
  **Update Canvas** (solid green, the only green in the app).
- **Gallery card:** thumbnail with a `2 Sounds` speaker badge bottom-left and a pencil top-right,
  then title, `Created Sep 16, 2026`, a presentation-text field, a "publish to a room" select,
  and a row of Edit / download / delete (red).
- **Palette:** violet primary, green for save, red for destructive, near-black page background.
