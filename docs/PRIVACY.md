# Personal information in Imagery (Quebec Law 25)

Participants record their own voice. That makes this an application holding
**personal information about identifiable people**, most of them elderly, and
Law 25 applies. This is what the software does and does not do about that; the
policy decisions remain with whoever runs the workshops.

## What is collected

| Item | Where it lives | Why |
|---|---|---|
| Chosen name (often a full name) | `user.display_name` | So pictures are attributable within a group |
| Passphrase | `user.pass_hash`, scrypt | So someone returns to their own work |
| Consent timestamp | `user.consent_at` | Evidence that consent was given, and when |
| Photographs | `/data/uploads/image/` | The participant's own picture |
| Voice recordings | `/data/uploads/audio/` | The oral history they record |
| Sign-in attempts | `login_attempt` (IP + name, 7 days) | Rate limiting only |

Nothing leaves the server. There is no analytics, no third-party service, and
no outbound request of any kind from the application.

## What the software provides

- **Consent is collected before an account exists.** A participant cannot join a
  group without ticking the box, and the time is recorded.
- **Right of access / portability**: `GET /api/users/<id>/export` returns
  everything held about one person as JSON, including the urls of their media.
- **Right to erasure**: `DELETE /api/users/<id>` removes the person, their
  pictures, and **the underlying files on disk** -- not merely the database rows.
  Files still referenced by someone else's canvas are left alone.
- **Scoped access**: a participant sees their own work and their group's
  collective gallery. Groups cannot see each other.
- **A recording belongs to the person who made it.** Uploads record their owner.
  A sound spot may point only at the shared bank or at a file that canvas's
  owner uploaded, so one participant cannot attach another's voice to their own
  picture by copying its URL.
- **Media is not public.** `/media/` requires authorisation: the owner, an
  administrator, that group's facilitator, or someone entitled to view a canvas
  that uses the file. A URL on its own is not enough, and responses are
  `no-store` so recordings do not sit in shared caches.
- **Signing out gives up gallery access too.** These iPads are shared and passed
  along; signing out is the handover, and the next person must enter the code.
- **Revocation**: changing a group's code immediately invalidates every device
  that had entered the old one.

## What it does not do, and you must decide

1. **Retention.** Nothing expires. Decide how long a group's material is kept
   after the workshop ends, and who deletes it.
2. **Who may listen.** Everyone in a group can play everyone's recordings. If
   that is not acceptable, it needs a per-person privacy setting.
3. **The consent wording.** The current text is deliberately plain but it is not
   legal advice, and it does not name the organisation, the purpose, the
   retention period, or who to contact. Replace it with wording your
   organisation stands behind.
4. **A privacy officer and a breach procedure.** Law 25 requires both. Neither
   is a software feature.
5. **Backups are personal information too.** `tools/backup.sh` writes
   unencrypted archives. Decide where they live and who can read them.
6. **Facilitators can read everything** in groups they own. That is deliberate,
   but participants should be told.

## Practical notes

- Erasure is immediate and cannot be undone. Export first if there is any doubt.
- A backup taken before an erasure still contains the person's data, so the
  retention window for backups is the real retention window.
