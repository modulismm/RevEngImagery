# UI/UX review — static, 2026-09-18

**Method and its limits:** no browser was available this session (no Claude-in-Chrome extension),
so this is static analysis of the served markup, the 76 KB stylesheet and the 505 KB bundle —
**nothing was rendered or clicked**. The bundle is minified, so utility/handler counts conflate
app code with library code; where that matters it is called out. Treat these as leads to confirm
in a browser, not as verified defects.

### 🔴 The core interaction has no keyboard path
The app triggers sounds from **cursor position over zones**. Across the whole bundle there are
**112 `hover:` utilities and zero app-level keyboard handlers** — the single `onKeyDown` belongs to
a library component (`tabIndex:-1` + `displayName`, i.e. a dialog). There is no tab order through
zones, no arrow-key traversal, no activation key. **So the entire purpose of the app is unreachable
by keyboard, and inaudible to a screen reader.** Only 1 `aria-label` and 6 `alt` in the bundle.
Cheapest real fix: render each sound zone as a focusable button with an `aria-label` of its
`sound_name`, firing the same play on focus/Enter as on hover.

### 🟡 `text-gray-500` fails WCAG AA (14 uses)
Computed against the backgrounds actually used (`bg-gray-800` ×36, `gray-900` ×7, `gray-950` ×5):

| text | on gray-800 | on gray-900 | on gray-950 |
|---|---|---|---|
| `gray-300` | 9.96 ✅ | 12.04 ✅ | 13.66 ✅ |
| `gray-400` | 5.78 ✅ | 6.99 ✅ | 7.93 ✅ |
| `gray-500` | **3.04 ❌** | **3.67 ❌** | **4.16 ❌** |

AA needs 4.5 for normal text. `gray-500` fails on every background in use; it only passes as
*large* text. `gray-400` is comfortably fine. **Fix is a find-and-replace: `text-gray-500` →
`text-gray-400`.** Low-opacity borders (`border-white/10` ×22, `border-white/20` ×18) are likely
below the 3.0 non-text threshold too.

### 🟡 `touch-action` is never set on a drag-to-place canvas
Touch *is* handled (`onTouchStart` ×5, `onTouchMove` ×3, `onTouchEnd` ×3), but `touch-action`
appears **0 times**. Dragging a zone on mobile will fight the browser's native scroll/pinch.
Standard fix: `touch-action: none` on the canvas surface.

### 🟡 Responsive coverage is thin
Only **25 responsive utilities total** (13 `sm:`, 8 `md:`, 4 `lg:`) for an app with an editor, a
gallery and a public lobby. The stylesheet has the full Tailwind breakpoint set, so this is
under-use rather than absence. Matches the earlier code-review finding U6 (*not responsive*).

### ✅ Holding up well
- **Autoplay unlock is handled properly** — `AudioContext.resume()` on both `onMouseDown` and
  `onTouchStart`, with `state === "suspended"` guarded in 4 places. Worth confirming in a browser
  that a *hover-only* entry (no click first) still unlocks, since `mousemove` is not a qualifying
  user gesture under Chrome's autoplay policy.
- **i18n is clean** — `en` and `fr`, **79 keys each, exact parity, no drift in either direction**.
- **Per-route SEO is done properly** — distinct `og:`/`twitter:` title, description and URL per
  route, plus `manifest.json` and HSTS.
