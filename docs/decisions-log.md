# Decisions log (public, sanitized)

## 21 Nov 2026

- **Cadence fixed by the owner:** 1 carousel + 1 native-audio Reel + 1 Story daily (21/week) from the
  first production week. Not to be re-asked.
- **Repo owner: `pietrocappellaro31-art`** (owner asked for "the one that makes the most sense, mindful of
  credit limits"). Reasons: Actions is free on public repos whoever owns them; Codespaces' free quota
  (120 core-hours, 15 GB-month per month) exists only for personal accounts, and is blocked, not charged,
  when exhausted without a payment method; organizations get no free Codespaces. Rendering is done
  mainly outside Codespaces to preserve that quota. No new GitHub account is created.
- **Public repo accepted by the owner**, including finished Reels carrying his voice. Raw recordings
  stay private.
- **API path: Instagram API with Facebook Login, system-user token**, as proven on both sister pages.
  Reels use `video_url` (sister measured resumable upload refusing some 40 s+ files, 16 Nov 2026).
- **Hardening over the sister publisher:** identity check against the expected handle, approval and
  asset-hash gate, per-format/day/week caps, missed slots never dumped, state persisted before
  `media_publish`, unknown outcomes freeze the format, no auto-comments, no automatic AI label
  (set per post after review).
