# Recovered data model

Reconstructed 2026-09-18 from the minified bundle and live API responses. Not from source.

## Entities

| Entity | Operations the app uses |
|---|---|
| `SoundImage` | create, get, list, filter, update, delete |
| `CustomSound` | create, filter, update, delete |
| `GalleryRoom` | create, list, update, delete |
| `GalleryConfig` | create, list, update |

Only integration in use: `Core.UploadFile`.
Pages: Home, Create, Gallery, PublicGallery, Upload, Layout.

## Fields

`sound_zones`, `image_url`, `room_id`, `published`, `thumbnail_canvas_id`, `sound_name`,
`file_url`, `created_by`, `user_id`, `created_date`.

Gallery theming: `gallery_title`, `gallery_subtitle`, `accent_color`, `bg_color`,
`title_font`, `title_align`, `subtitle_font`, `subtitle_align`, `room_title_font`,
`lobby_cols`, `lobby_justify`, `auth_required`.

## A sound zone

```json
{
  "id": "1789566035958",
  "sound_name": "Son 1",
  "x": 40.188419117647065,
  "y": 24.941176470588236,
  "radius": 225.93804460515253,
  "volume": 0.7,
  "startTime": 0,
  "endTime": 2.1,
  "type": "custom",
  "sound_url": null,
  "url": "https://base44.app/api/apps/<APP_ID>/files/mp/public/<APP_ID>/<hash>_recording.webm",
  "effects": {
    "reverbLevel": 0, "pitch": 0,
    "highFreq": 0, "midFreq": 0, "lowFreq": 0,
    "isReversed": false
  }
}
```

**`x` and `y` are percentages** of image dimensions. **`radius` is not** -- it appears to be
in pixels; confirm against a screenshot before relying on it.

**The gotcha:** `sound_url` is **null** in practice and the real recording lives in **`url`**.
Anything parsing an export must follow `url`.

## API

The app is `public_without_login`, so entity reads need no token -- only an `X-App-Id` header:

```
GET https://imagery.base44.app/api/apps/<APP_ID>/entities/<Entity>
    -H "X-App-Id: <APP_ID>"

GET https://imagery.base44.app/api/apps/public/prod/public-settings/by-id/<APP_ID>
```

App id: `68a26cc71947ac0be6d6a35c`. Media URLs are public and need no auth.

## Export format

The app's own per-canvas export/import. Import validates `export_version`, `name` and
`sound_zones`, then creates a `SoundImage` -- so it is a real round-trip.

```json
{ "name", "image_url", "sound_zones", "created_date", "export_version": "1.0" }
```

## Audio engine (recovered from the bundle, 2026-09-18)

Complete and exactly replicable. Per zone the chain is:

```
input(gain)
  -> lowshelf   f=320Hz          gain = effects.lowFreq
  -> peaking    f=1000Hz  Q=1    gain = effects.midFreq
  -> highshelf  f=3200Hz         gain = effects.highFreq
  -> dry gain (1-k) ----------------.
  \-> convolver -> wet gain (k) ----+-> master gain -> destination
```

`k = effects.reverbLevel / 100`. Master gain starts at 0.

**Reverb impulse response** is generated, not a file: 2 channels x `sampleRate * 2` samples
(2 seconds), each sample `(Math.random()*2-1) * Math.pow(1 - i/len, 2)` -- white noise under a
squared decay envelope.

**Pitch** is `playbackRate = Math.pow(2, semitones/12)`, slider range -12..+12 step 1. Plain
resampling, so duration changes with pitch. No `detune`, no phase vocoder.

**Trigger and falloff**, on pointer move, per zone:

```js
d = hypot(px - zx, py - zy)
if (d <= zone.radius / 2) {
    gain = (zone.volume || 0.7) * (1 - Math.min(1, d / (zone.radius / 2)))
    masterGain.setTargetAtTime(gain, now, 0.05)      // smoothing tc = 50ms
} else {
    masterGain.linearRampToValueAtTime(0, now + 0.2) // 200ms fade, then pause
}
```

So volume falls off **linearly** from full at the centre to zero at the edge -- not binary.

**Looping:** on `timeupdate`, `currentTime >= endTime` resets to `startTime`, so a zone loops
within its trimmed window.

Custom sounds play through an `<audio>` element routed into the graph, not an
`AudioBufferSourceNode`.
