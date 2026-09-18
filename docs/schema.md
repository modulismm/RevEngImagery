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
