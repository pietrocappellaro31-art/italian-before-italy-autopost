# italian-before-italy-autopost

Native-audio Italian language education and Instagram publishing pipeline for **@italianbeforeitaly**.

This repository is **public** on purpose: Meta fetches images and videos from their
`raw.githubusercontent.com` URLs, and Actions minutes are free on public repos. Only
sanitized code and **final, owner-approved public assets** live here. Raw voice
recordings, scripts awaiting approval, plans and anything personal live in the private
production workspace and never enter this repo or its Actions logs (`build/verify_public.py`
enforces this in CI).

## How it works

| Piece | Where |
|---|---|
| Publisher | `publish.py` (stdlib only) |
| Schedule | `posts.json`, UTC timestamps, one entry per post |
| Queueing | `build/schedule.py` (computes DST-safe slots, records sha256 of every asset) |
| Scheduler | `.github/workflows/publish.yml` |
| Checks | `.github/workflows/check.yml`: safety scan, offline tests, dry run |
| Final media | `media/` (JPEG slides/Stories, MP4 Reels, JPEG covers) |

Fixed cadence: Story 07:30, Carousel 08:10, Reel 12:35 (America/New_York), every day.
Hard caps in code: 1 per format per Eastern day, 3 per day, 21 per Monday-Sunday week.
A slot missed by more than 8 hours is logged as `missed`, never dumped later.

## Safety switches

- Repo variable `PUBLISH_ENABLED` must be `true` for anything to publish. It starts unset (paused).
- `workflow_dispatch` modes: `dryrun` (default, no network), `selftest` (publishes nothing), `publish`.
- Every non-idle run checks that the token reaches exactly `@italianbeforeitaly`.
- Publishing state is committed **before** `media_publish`; an unknown outcome freezes that
  format until a person confirms it on the profile. Nothing is ever deleted automatically.

## Secrets and variables

| Name | Kind | Value |
|---|---|---|
| `IG_ACCESS_TOKEN` | secret | pasted by the owner directly into Settings → Secrets and variables → Actions |
| `PUBLISH_ENABLED` | variable | `true` only after the acceptance tests pass |
| `META_API_VERSION` | variable | pinned Graph API version, verified against Meta's docs |
| `IG_USER_ID` | variable (optional) | the account id, if discovery is ambiguous |

## Run locally

```bash
python -m unittest discover -s tests -v   # offline tests
python build/verify_public.py              # must say "clean" before any push
python publish.py --dryrun                 # what would publish now, no network
```
