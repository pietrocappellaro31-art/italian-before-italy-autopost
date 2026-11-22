# Technical facts

Each line says where it came from. "Sister, measured" means observed on a passing or failing
run of a sister page, not read in documentation. Re-verify against Meta's docs before relying on any.

| Fact | Source |
|---|---|
| Images must be JPEG; PNG is rejected | Sister, measured |
| Meta fetches media from a public URL; raw.githubusercontent.com works | Sister, measured |
| Publishing quota read live from `content_publishing_limit` (sister saw 100 / 24 h) | Sister, measured; never hard-coded |
| Unpublished containers expire (sister: 24 h); create close to the slot | Sister, measured |
| Reels: `video_url` reliable; resumable upload refused some 40 s+ files | Sister, measured 16 Nov 2026 |
| `is_ai_generated` accepted on container creation | Sister, Meta changelog 22 Jun 2026 |
| Stories via API: no caption, no stickers | Sister, measured |
| New developer accounts can hit "API access blocked" (OAuthException 200, subcode 5258005) soon after first API publishes; owner clears an identity checkpoint | Sister, 2 and 16 Nov 2026 |
| Apps created from the Instagram use case ship with no permissions; add them by hand ("No permissions available" otherwise) | Sister, measured |
| GitHub cron is not punctual: sister saw about 7 fires/day with gaps up to 10 h | Sister, measured 1-16 Nov 2026 |
| Actions free for standard runners on public repos | GitHub docs, checked 21 Nov 2026 |
| Codespaces free: 120 core-hours + 15 GB-month per month, personal accounts only; blocked when used up | GitHub docs, checked 21 Nov 2026 |
