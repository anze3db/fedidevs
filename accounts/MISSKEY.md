# Misskey-family instance support

Notes on how fedidevs ingests **Misskey-family forks** (Catodon, Akkoma, Sharkey,
Firefish, Iceshrimp) alongside vanilla Mastodon. Use this when adding a new
instance, debugging a 404 from the crawler, or wondering why a Catodon user
appears in conferences but not in starter packs.

The adapter lives in `accounts/misskey.py`. The dispatch logic lives in
`accounts/management/commands/crawler.py`.

## API compatibility per fork

| Endpoint | Mastodon | Catodon / Akkoma / Sharkey / Firefish / Iceshrimp | Pure Misskey |
|---|---|---|---|
| `/.well-known/nodeinfo` | ✅ | ✅ | ✅ |
| `/api/v1/instance` | ✅ | ✅ (full Mastodon-compat payload) | ❌ |
| `/api/v2/instance` | ✅ | ❌ 404 | ❌ |
| `/api/v1/directory` (crawler) | ✅ | ❌ 404 | ❌ |
| `/api/v1/timelines/tag/{tag}` (stattag) | ✅ | ✅ Mastodon-shaped statuses | ❌ |
| `/api/v1/accounts/lookup` | ✅ | ⚠️ 500 on some forks | ❌ |
| `POST /api/users` (Misskey-native) | ❌ | ✅ | ✅ |
| `POST /api/notes/search-by-tag` (Misskey-native) | ❌ | ✅ | ✅ |

**Pure Misskey** (no Mastodon-compat layer) won't be indexed at all — the
`instances` command needs `/api/v1/instance` to populate an `Instance` row. If we
ever want to support pure Misskey, we'd need a nodeinfo-based path that maps
`/api/meta` → `Instance` fields.

## Crawler dispatch flow

`crawler.py` keeps a per-`Command` cache `self._adapters: dict[str, str]` with
values `"mastodon"`, `"misskey"`, or `"unknown"`. On the first page for an
instance:

1. `GET /api/v1/directory` → if 200, cache as `"mastodon"` and use the result.
2. On 404, `POST /api/users` with `{sort: "+follower", state: "alive", origin: "local", offset, limit}` → if 200, cache as `"misskey"` and convert via `accounts.misskey.user_to_mastodon`.
3. Otherwise cache as `"unknown"` so subsequent pages return `[]` immediately.

Subsequent pages skip the probe and use the cached adapter directly.

## Field mapping (Misskey `/api/users` → Mastodon directory shape)

| Mastodon field | Misskey source | Notes |
|---|---|---|
| `id` | `id` | string |
| `username` | `username` | required |
| `acct` | `username` (local) or `f"{username}@{host}"` (remote) | |
| `display_name` | `name` → fallback `username` | Misskey allows null `name` |
| `locked` | `isLocked` | |
| `bot` | `isBot` | |
| `group` | `isGroup` | |
| `noindex` | `noindex` | directly mapped |
| **`discoverable`** | **`not noindex`** | ⚠️ Misskey has no `discoverable` field. See below. |
| `created_at` | `createdAt` | |
| `last_status_at` | **`updatedAt`** | ⚠️ proxy — Misskey doesn't expose last-post time on user listings |
| `followers_count` | `followersCount` | |
| `following_count` | `followingCount` | |
| `statuses_count` | `notesCount` | |
| `note` | `description` | |
| `url` | `url` → fallback `https://{instance}/@{username}` | `url` is null for local users |
| `uri` | `uri` → fallback `https://{instance}/users/{id}` | ⚠️ actor URI uses the Misskey **id**, not the `@handle`. Both `url`/`uri` are null for local users; the fallback must NOT reuse `url` (the profile URL) or `activitypub_id` is wrong. |
| `avatar` / `avatar_static` | `avatarUrl` → fallback `""` | |
| `header` / `header_static` | `bannerUrl` → fallback `""` | |
| `emojis` | `emojis` dict → list `[{shortcode, url, static_url, visible_in_picker}]` | |
| `roles` | `badgeRoles` (shape differs but stored as JSON) | |
| `fields` | `fields` | same shape |

### Why `discoverable = not noindex`

Misskey forks don't have Mastodon's opt-in `discoverable` concept. They expose
`noindex` as an opt-out lever instead. Catodon's `/api/v1/instance`
Mastodon-compat layer hardcodes `discoverable: false` on every embedded account
because the field doesn't exist natively.

If we defaulted `discoverable` to `False` in the adapter, every Misskey user
would fail `Account.should_index()` and the starter-pack hide filter (which
excludes anything where `discoverable != True`). So we set `discoverable = not noindex`:
users who explicitly opt out of indexing are correctly hidden, everyone else
appears.

## The `discoverable` self-healing lifecycle (Catodon → conferences)

When `stattag` ingests a post from a Catodon-hosted conference hashtag, the
embedded account has `discoverable: false` (because Catodon hardcodes it).
`process_posts` inserts a new `Account` row with `discoverable=False`.

The nightly job order is `crawler` → `indexer` → … → `stattag`:

1. **Day N hourly `stattag`**: Alice posts under a conference hashtag → row inserted with `discoverable=False`.
2. **Day N+1 daily `crawler`**: hits bohio.icu, Misskey adapter returns Alice with `discoverable = not noindex` (i.e. `True`). The crawler's `update_fields` **includes** `discoverable` (`crawler.py:129`), so the False gets overwritten.
3. **Day N+1 daily `stattag`** (after the crawler in the same job): Alice already exists. `process_posts`'s `update_fields` is `["last_sync_at", "followers_count", "following_count", "statuses_count", "instance_model"]` — it does **not** include `discoverable`, so the True stays put.

Net effect: Catodon accounts are invisible in starter packs for at most one day after first being discovered through conferences, then self-correct.

### Edge case: stale-profile Catodon users

The Misskey adapter uses `updatedAt` as the `last_status_at` proxy. If a user's
profile hasn't been updated in `> --skip-inactive-for` days (default 3), the
`/api/users` listing filter drops them, the crawler never picks them up, and
their `discoverable=False` from `stattag` persists. They'll still show on
conference pages (those don't gate on `discoverable`) but stay hidden from
starter packs.

In practice this is rare — anyone active enough to post under a conference
hashtag almost always has a recent `updatedAt`. Not worth fixing unless we see
it in the wild.

## Adding a new instance (operational steps)

```bash
# 1. Run the crawler against a specific instance (will auto-create the Instance row).
uv run python manage.py crawler --instances example.social

# 2. Or add it to the seed set in accounts/management/commands/instances.py
#    and let the nightly job pick it up.

# 3. To force-ingest all (including inactive) accounts:
uv run python manage.py crawler --instances example.social --skip-inactive-for 0
```

The crawler will:
- Call `process_instances([...])` first to populate the `Instance` row via `/api/v2/instance` (with `/api/v1/instance` fallback). This is required for accounts to have a non-null `instance_model_id`.
- Auto-detect Mastodon vs Misskey on first page and remember the choice.
- Skip the instance with a yellow warning if no `Instance` row could be created (truly unreachable host).

## Notable bugs that were fixed when this support landed

These are documented here because git blame on the touched lines might be
confusing without context:

- **`instances.py`**: the `/api/v1/instance` fallback was dead code. The outer `fetch()` had `if response.status_code == 404: return None` *inside the try block*, which short-circuited before reaching the `elif response.status_code == 404: return await fetch_v1(...)` below. Any instance returning 404 on `/api/v2/instance` (Catodon, Akkoma, older Mastodon) was being rejected even though the v1 endpoint would have worked. Fixed by removing the early return.
- **`crawler.py`**: `--instances X` for an instance not yet in the DB crashed at `inst.domain.lower()` because `instance_models.get(X)` returned `None`, and accounts were created with `instance_model_id=NULL`. Those NULL-FK rows then failed the starter-pack hide filter (`instance_model__isnull=False`) and showed as "hidden due to privacy settings." Fixed by calling `process_instances(missing)` before the fetch loop and skipping instances that still have no row after that.

## Quick reference: privacy-flag semantics

The starter-pack listing query (in `starter_packs/views.py:share_starter_pack`) requires:

```python
discoverable=True
instance_model__isnull=False
instance_model__deleted_at__isnull=True
```

`Account.should_index()` requires `discoverable=True AND not noindex`.

For the bohio.icu user audit on 2026-05-27, of 9 local Catodon users:
- 4 have `noindex=True` (`admin`, `Carmen`, `Jennifer`, `test2`) → correctly excluded.
- 5 have `noindex=False` → indexable, subject to the activity filter.
