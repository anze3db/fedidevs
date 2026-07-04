# GoToSocial instance support

Notes on how fedidevs handles **GoToSocial** (nodeinfo `software.name:
"gotosocial"`), issue #192. Everything below was verified against GTS 0.22
(gts.superseriousbusiness.org, plantsand.coffee, goblin.technology), the GTS
swagger spec, and the GTS example config — not against Mastodon docs, because
GTS deliberately diverges on authentication.

## The core constraint: almost everything needs a token

GTS implements the Mastodon client API but gates nearly all of it behind OAuth.
Unauthenticated status codes observed on GTS 0.22:

| Endpoint | Unauthenticated | Notes |
|---|---|---|
| `/.well-known/nodeinfo`, `/nodeinfo/2.0` | ✅ 200 | software detection |
| `/api/v1/instance`, `/api/v2/instance` | ✅ 200 | Mastodon-shaped; `instances` command works |
| `POST /api/v1/apps` | ✅ 200 | OAuth app registration works → login works |
| `/api/v1/directory` | ⚠️ 401 by default | 200 only with `instance-directory-mode: "open"`; 404 on older GTS without the endpoint |
| `/api/v1/timelines/tag/{tag}` (stattag) | ❌ 401 always | **no config option exists** to open this (only `instance-expose-public-timeline`, which covers `/timelines/public` only) |
| `/api/v1/accounts/{id}/statuses` (statuser) | ❌ 401 | |
| `/api/v1/accounts/lookup` | ❌ 401 | the ActivityPub fallback (`accounts/activitypub.py`) exists for this |

`instance-directory-mode` (GTS example config): `"off"` / `"webonly"`
(default) / `"open"`. Only `"open"` serves the directory API without a token.
The directory contains **only local accounts that opted in to discoverability**
— typically a handful of users.

## Crawler behavior (`crawler.py`)

- `GET /api/v1/directory` → **200**: normal Mastodon path. GTS output is
  Mastodon-shaped with two quirks:
  - `last_status_at` is date-only (`"2026-06-27"`) — same as Mastodon ≥ 3.1,
    already handled by `convert_last_status_at`.
  - **No `uri` field** (Mastodon only added it in 4.2). Since `activitypub_id`
    feeds starter-pack ActivityPub payloads, the crawler resolves the actor id
    via WebFinger (`_fill_missing_actor_uris`), gated on nodeinfo saying
    `gotosocial` so we don't WebFinger entire directories of pre-4.2 Mastodon
    servers. GTS actor ids look like `https://{host}/users/{username}`.
- → **401/403**: deterministic server config, so the adapter is cached as
  `"unknown"` (no re-probe per page, no Misskey probe) and a yellow message
  names the software (via nodeinfo) and, for GTS, the config fix:
  `instance-directory-mode: "open"`.
- → **404**: unchanged (Misskey probe; old GTS without the directory endpoint
  ends up `"unknown"` after the Misskey probe 404s too).

## What can't work without server-side changes

- **Conference posts (`stattag`)**: tag timelines always require a token on
  GTS; there is no exposure config. Also `stattag` queries instances with
  `local=true`, so GTS users' conference posts federated to Mastodon servers
  are filtered out there too. Supporting this would need per-instance API
  tokens (admin cooperation) or dropping `local=true` (dedup implications).
- **Post ingestion (`statuser`)**: per-account statuses are 401. Same token
  story. Note GTS status/account ids are ULIDs, not snowflakes — the numeric
  `min_id` seed in `stattag` would filter out everything (ULIDs starting with
  `01…` sort before `111054…`) if this were ever wired up.
- **`findinstances`** verifies candidate conference instances by fetching
  their tag timeline, so GTS instances correctly never get added as conference
  sources.

## What works with no changes

- **Login** with a GTS instance: standard OAuth path (`/api/v1/apps` +
  `/oauth/authorize` + `/oauth/token`); all Mastodon.py clients use
  `version_check_mode="none"` so GTS's `0.22.0+git-…` version string is fine.
- **Starter packs**: adding a GTS account resolves through the logged-in
  user's own instance (federated `resolve=true` search) or the ActivityPub
  actor fallback; follows go through the follower's instance, not the GTS
  server.

## Ops: indexing a GoToSocial instance

Only possible if the admin sets `instance-directory-mode: "open"`. Then:

```bash
uv run python manage.py crawler --instances example.gts.instance --skip-inactive-for 0
```

Verified end-to-end against plantsand.coffee (open directory): Instance row
via `/api/v2/instance`, account row with WebFinger-resolved `activitypub_id`.
As of 2026-07-02, of the 20 largest GTS instances (per FediDB), 6 ran open
directories.
