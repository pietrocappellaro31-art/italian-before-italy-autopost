"""
Italian Before Italy (IBI) publisher.

Reads posts.json and publishes approved, due entries to @italianbeforeitaly
through Meta's Instagram Graph API (Instagram API with Facebook Login).
Ported from the proven sister publisher (pietrocappellaro31-art/ib-autopost)
and hardened per the IBI implementation contract:

  * identity check on every non-idle run (username must equal IG_EXPECTED_HANDLE)
  * approval + sha256 asset hashes verified against the bytes Meta will fetch
  * caps: 1 per format per Eastern day, 3 per Eastern day, 21 per Eastern Mon-Sun week
  * no backlog dumps: a slot older than GRACE_HOURS (or from an earlier Eastern day) is
    marked "missed" and never published without a new approval
  * durable state machine:
        approved -> container_created -> publish_pending -> published
        plus retryable_error, blocked, needs_reconciliation, missed, expired
    The state is persisted (and, in CI, pushed to git) BEFORE media_publish is called,
    so a run that dies mid-publish can never cause a blind second publish.
  * idle runs (nothing due) touch no network at all
  * the token never appears in output: it travels in POST bodies / query strings that
    are never printed, and every error body is redacted

Modes:
    python publish.py --dryrun     validate + show what would publish; no network
    python publish.py --selftest   identity, quota, one carousel item container; publishes nothing
    python publish.py              publish what is due (requires PUBLISH_ENABLED=true)

Environment:
    IG_ACCESS_TOKEN      secret (GitHub Actions repository secret only)
    IG_EXPECTED_HANDLE   non-secret, must be "italianbeforeitaly"
    IG_USER_ID           optional non-secret override of the discovered account id
    META_API_VERSION     pinned Graph API version, e.g. v21.0 (verify against Meta docs)
    PUBLISH_ENABLED      repo variable; anything other than "true" means paused
    STATE_PUSH           "1" in CI: commit + push posts.json at each critical step
"""

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")
HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "posts.json")

# ---------------------------------------------------------------- fixed launch rules (owner decision)
FORMATS = ("carousel", "reel", "story")
MAX_PER_FORMAT_PER_DAY = 1
MAX_PER_DAY = 3
MAX_PER_WEEK = 21
GRACE_HOURS = 8            # GitHub cron is unreliable (sister measured gaps of up to 10 h); after this, a slot is missed
MAX_ATTEMPTS = 3           # then the entry is blocked and waits for a person

POLL_SECONDS = 10
POLL_ATTEMPTS = {"carousel": 30, "story": 30, "reel": 60}
HTTP_TIMEOUT = 60

ALLOWED_MEDIA_HOST = "raw.githubusercontent.com"
AUDIO_KINDS = ("native_recording", "none", "approved_non_teaching")
OPEN_STATES = ("container_created", "publish_pending")   # outcome may already exist on Instagram
FINAL_STATES = ("published",)

# Meta error markers that mean "stop everything, a person must look" (sister: OAuthException 200 /
# "API access blocked", subcode 5258005; rate limits 4, 17, 32, 613; spam/limit 368).
STOP_MARKERS = ("API access blocked", "5258005", "temporarily blocked", "unusual activity",
                '"code":368', '"code":4,', '"code":17,', '"code":32,', '"code":613', '"code":190')


class StopRun(Exception):
    """Something a person must resolve: identity, auth, block, rate limit."""


# ---------------------------------------------------------------- small helpers

def utc(stamp):
    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp without timezone: {stamp}")
    return parsed.astimezone(timezone.utc)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def eastern_day(dt):
    return dt.astimezone(EASTERN).date()


def eastern_week(dt):
    """Monday of the Eastern Monday-Sunday week containing dt."""
    d = eastern_day(dt)
    return d - timedelta(days=d.weekday())


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def redact(text):
    token = os.environ.get("IG_ACCESS_TOKEN", "")
    text = str(text)
    if token and len(token) > 8:
        text = text.replace(token, "<token>")
        text = text.replace(urllib.parse.quote(token, safe=""), "<token>")
    return text


def log(msg):
    print(redact(msg), flush=True)


def warn(msg):
    print(redact(msg), file=sys.stderr, flush=True)


# ---------------------------------------------------------------- manifest

def load_manifest(path=MANIFEST):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def save_manifest(manifest, path=MANIFEST):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.replace(tmp, path)


def persist(manifest, message, path=MANIFEST):
    """Save state; in CI also commit and push it. If the push fails we must not go on to publish."""
    save_manifest(manifest, path)
    if os.environ.get("STATE_PUSH") != "1":
        return
    cmds = [["git", "add", os.path.relpath(path, HERE)],
            ["git", "commit", "-q", "-m", f"state: {message}"]]
    for cmd in cmds:
        subprocess.run(cmd, cwd=HERE, check=False, capture_output=True)
    for _ in range(3):
        pushed = subprocess.run(["git", "push", "-q"], cwd=HERE, capture_output=True)
        if pushed.returncode == 0:
            return
        subprocess.run(["git", "pull", "--rebase", "-q"], cwd=HERE, capture_output=True)
        time.sleep(3)
    raise StopRun(f"could not push state '{message}'; refusing to continue")


def validate_manifest(manifest):
    """Return a list of problems. An empty list means the manifest is structurally safe to act on."""
    problems = []
    expected = os.environ.get("IG_EXPECTED_HANDLE", "italianbeforeitaly")
    if manifest.get("brand") != "italian-before-italy":
        problems.append("brand must be italian-before-italy")
    if manifest.get("expected_handle") != expected:
        problems.append(f"expected_handle must be {expected}")
    base = manifest.get("media_base", "")
    parsed = urllib.parse.urlparse(base)
    if "OWNER/REPO" in base or parsed.scheme != "https" or parsed.netloc != ALLOWED_MEDIA_HOST:
        problems.append("media_base must be a real https://raw.githubusercontent.com/... URL")
    seen = set()
    for post in manifest.get("posts", []):
        pid = post.get("id", "<missing id>")
        if pid in seen:
            problems.append(f"{pid}: duplicate id")
        seen.add(pid)
        problems += [f"{pid}: {p}" for p in validate_post(post)]
    return problems


def validate_post(post):
    p = []
    kind = post.get("type")
    if kind not in FORMATS:
        return [f"unsupported type {kind!r}"]
    for field in ("id", "lesson_id", "scheduled_utc", "media", "status", "approval_id", "asset_hashes"):
        if field not in post:
            p.append(f"missing {field}")
    if p:
        return p
    try:
        utc(post["scheduled_utc"])
    except ValueError as error:
        p.append(str(error))
    media = post["media"]
    if not isinstance(media, list) or not media:
        p.append("media must be a non-empty list")
        return p
    for name in media + ([post["cover"]] if post.get("cover") else []):
        if name.startswith(("/", "http")) or ".." in name or "\\" in name:
            p.append(f"media path not allowed: {name}")
    if kind == "carousel":
        if not 2 <= len(media) <= 10:
            p.append("carousel needs 2-10 slides")
        if not all(m.lower().endswith((".jpg", ".jpeg")) for m in media):
            p.append("carousel slides must be JPEG")
    if kind == "story" and (len(media) != 1 or not media[0].lower().endswith((".jpg", ".jpeg"))):
        p.append("story needs exactly one JPEG")
    if kind == "story" and post.get("caption_file"):
        p.append("stories take no caption via the API")
    if kind == "reel":
        if len(media) != 1 or not media[0].lower().endswith(".mp4"):
            p.append("reel needs exactly one MP4")
        if post.get("audio_kind") not in AUDIO_KINDS:
            p.append("reel audio_kind must be native_recording, none or approved_non_teaching")
    if kind in ("carousel", "reel") and not post.get("caption_file"):
        p.append("missing caption_file")
    if post["status"] in ("approved",) + OPEN_STATES + FINAL_STATES:
        if not isinstance(post.get("ai_generated"), bool):
            p.append("ai_generated must be reviewed and set true/false before approval")
        if "PLACEHOLDER" in post["approval_id"] or "OWNER-APPROVED-BATCH-ID" in post["approval_id"]:
            p.append("approval_id is a placeholder")
        needed = media + ([post["cover"]] if post.get("cover") else [])
        if kind in ("carousel", "reel"):
            needed.append("caption")
        missing = [n for n in needed if not post["asset_hashes"].get(n)]
        if missing:
            p.append(f"missing asset hashes for {missing}")
    if post["status"] == "published" and not post.get("published_id"):
        p.append("published without published_id")
    return p


# ---------------------------------------------------------------- selection: caps, grace, sequences

def published_at(post):
    stamp = post.get("published_at_utc")
    return utc(stamp) if stamp else None


def counts_toward_caps(post):
    """Published posts, and posts whose outcome is unknown, both count: an unknown might be live."""
    return post.get("status") in FINAL_STATES + OPEN_STATES + ("needs_reconciliation",)


def cap_time(post):
    return published_at(post) or utc(post["scheduled_utc"])


def select_due(manifest, now):
    """Return (due, newly_missed). Applies every cadence rule; never mutates anything but marks missed slots."""
    posts = manifest["posts"]
    by_id = {p["id"]: p for p in posts}
    today, week = eastern_day(now), eastern_week(now)
    counted = [p for p in posts if counts_toward_caps(p)]
    day_total = sum(1 for p in counted if eastern_day(cap_time(p)) == today)
    week_total = sum(1 for p in counted if eastern_week(cap_time(p)) == week)
    day_format = {f: sum(1 for p in counted if p["type"] == f and eastern_day(cap_time(p)) == today) for f in FORMATS}

    # A format with an unresolved publish outcome publishes nothing until a person confirms it.
    frozen = {p["type"] for p in posts if p.get("status") == "needs_reconciliation"}
    due, missed = [], []
    candidates = sorted((p for p in posts if p.get("status") in ("approved", "retryable_error")),
                        key=lambda p: p["scheduled_utc"])
    for post in candidates:
        slot = utc(post["scheduled_utc"])
        if slot > now:
            continue
        if eastern_day(slot) != today or now - slot > timedelta(hours=GRACE_HOURS):
            missed.append(post)          # never dumped later; needs a fresh approval and slot
            continue
        if post["type"] in frozen:
            log(f"Holding {post['id']}: an earlier {post['type']} needs reconciliation")
            continue
        dep = post.get("requires_published")   # e.g. a quiz-answer Story needs its question Story live
        if dep and by_id.get(dep, {}).get("status") != "published":
            log(f"Holding {post['id']}: depends on {dep}, which is not published")
            continue
        exempt = bool(post.get("cap_exempt"))            # owner-approved one-off; day and week caps still apply
        if ((day_format[post["type"]] >= MAX_PER_FORMAT_PER_DAY and not exempt) or day_total >= MAX_PER_DAY
                or week_total >= MAX_PER_WEEK):
            log(f"Cap reached, holding {post['id']}")
            continue
        due.append(post)
        day_format[post["type"]] += 1
        day_total += 1
        week_total += 1
    return due, missed


# ---------------------------------------------------------------- Graph API

def graph_root():
    version = os.environ.get("META_API_VERSION") or "v21.0"   # pin via repo variable after checking Meta docs
    return f"https://graph.facebook.com/{version}"


def call_graph(path, params=None, method="GET"):
    """One Graph API request. Raises StopRun on block/auth/rate-limit signals, RuntimeError otherwise."""
    params = dict(params or {})
    params["access_token"] = os.environ["IG_ACCESS_TOKEN"]
    url = f"{graph_root()}/{path}"
    data = urllib.parse.urlencode(params)
    if method == "GET":
        request = urllib.request.Request(f"{url}?{data}")
    else:
        request = urllib.request.Request(url, data=data.encode(), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        body = redact(error.read().decode(errors="replace"))[:600]
        message = f"Graph API {error.code} on {path.split('?')[0]}: {body}"
        if any(m in body for m in STOP_MARKERS) or error.code in (401, 403, 429):
            raise StopRun(message) from None
        raise RuntimeError(message) from None
    except (urllib.error.URLError, TimeoutError) as error:
        raise TimeoutError(f"network problem on {path.split('?')[0]}: {redact(error)}") from None


def resolve_identity():
    """Find the IG account and refuse anything that is not the expected handle."""
    expected = os.environ.get("IG_EXPECTED_HANDLE", "italianbeforeitaly")
    explicit = os.environ.get("IG_USER_ID", "").strip()
    if explicit:
        account = call_graph(explicit, {"fields": "id,username"})
        found = [(account.get("id"), account.get("username"))]
    else:
        pages = call_graph("me/accounts", {"fields": "instagram_business_account{id,username}"})
        found = [(p["instagram_business_account"]["id"], p["instagram_business_account"].get("username"))
                 for p in pages.get("data", []) if p.get("instagram_business_account")]
    matches = [(i, u) for i, u in found if u == expected]
    if not found:
        raise StopRun("No Instagram professional account reachable from this token: check the Page link, the "
                      "system user's asset assignment and the token's permissions.")
    if len(matches) != 1:
        raise StopRun(f"Identity mismatch: expected @{expected}, token reaches {len(found)} account(s), "
                      f"{len(matches)} matching. Stopping everything.")
    log(f"Identity verified: @{expected}")
    return matches[0][0]


def remaining_quota(ig_user_id):
    result = call_graph(f"{ig_user_id}/content_publishing_limit", {"fields": "quota_usage,config"})
    entry = (result.get("data") or [{}])[0]
    total = entry.get("config", {}).get("quota_total")
    if total is None:
        raise RuntimeError("content_publishing_limit did not report quota_total")
    return total - entry.get("quota_usage", 0)


def container_status(container_id):
    return call_graph(container_id, {"fields": "status_code"}).get("status_code")


def wait_until_finished(container_id, kind):
    for _ in range(POLL_ATTEMPTS[kind]):
        code = container_status(container_id)
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED", "PUBLISHED"):
            raise RuntimeError(f"container ended as {code}")
        time.sleep(POLL_SECONDS)
    raise RuntimeError("container never finished processing")


# ---------------------------------------------------------------- media checks

def media_url(manifest, name):
    return manifest["media_base"] + urllib.parse.quote(name)


def verify_public_media(manifest, post, fetch=None):
    """Fetch every public URL Meta will use and check its bytes against the approved hash."""
    fetch = fetch or _fetch
    names = post["media"] + ([post["cover"]] if post.get("cover") else [])
    for name in names:
        data = fetch(media_url(manifest, name))
        if not data:
            raise RuntimeError(f"{name}: empty response")
        if sha256(data) != post["asset_hashes"][name]:
            raise RuntimeError(f"{name}: public bytes do not match the approved hash")


def _fetch(url):
    if urllib.parse.urlparse(url).netloc != ALLOWED_MEDIA_HOST:
        raise RuntimeError("media host not allowed")
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()


def read_caption(post):
    path = os.path.normpath(os.path.join(HERE, post["caption_file"]))
    if not path.startswith(os.path.join(HERE, "build", "captions") + os.sep):
        raise RuntimeError("caption_file must live in build/captions/")
    with open(path, encoding="utf-8") as handle:
        caption = handle.read().strip()
    if sha256(caption.encode()) != post["asset_hashes"].get("caption"):
        raise RuntimeError("caption text does not match its approved hash")
    return caption


# ---------------------------------------------------------------- containers

def create_container(ig_user_id, manifest, post):
    kind = post["type"]
    if kind == "story":
        return call_graph(f"{ig_user_id}/media",
                          {"media_type": "STORIES", "image_url": media_url(manifest, post["media"][0])},
                          "POST")["id"]
    caption = read_caption(post)
    if kind == "carousel":
        children = []
        for name in post["media"]:
            children.append(call_graph(f"{ig_user_id}/media",
                                       {"image_url": media_url(manifest, name), "is_carousel_item": "true"},
                                       "POST")["id"])
        params = {"media_type": "CAROUSEL", "children": ",".join(children), "caption": caption}
        if post.get("ai_generated"):
            params["is_ai_generated"] = "true"
        return call_graph(f"{ig_user_id}/media", params, "POST")["id"]
    # reel: sister measured video_url as reliable (resumable refused some 40 s+ files, 16 Nov 2026)
    params = {"media_type": "REELS", "video_url": media_url(manifest, post["media"][0]),
              "caption": caption, "share_to_feed": "true"}
    if post.get("cover"):
        params["cover_url"] = media_url(manifest, post["cover"])
    if post.get("ai_generated"):
        params["is_ai_generated"] = "true"
    return call_graph(f"{ig_user_id}/media", params, "POST")["id"]


def publish_post(ig_user_id, manifest, post, persist_fn):
    """Run one post through the state machine. Every state change is persisted before the next API call."""
    post["attempts"] = post.get("attempts", 0) + 1
    post["last_attempt_utc"] = now_iso()
    post["container_id"] = create_container(ig_user_id, manifest, post)
    post["status"] = "container_created"
    persist_fn(f"{post['id']} container_created")

    wait_until_finished(post["container_id"], post["type"])
    post["status"] = "publish_pending"
    persist_fn(f"{post['id']} publish_pending")      # durable BEFORE media_publish

    result = call_graph(f"{ig_user_id}/media_publish", {"creation_id": post["container_id"]}, "POST")
    post["published_id"] = result["id"]
    post["published_at_utc"] = now_iso()
    post["status"] = "published"
    post["last_error"] = None
    persist_fn(f"{post['id']} published")
    log(f"  published {post['id']} ({post['type']})")


def reconcile(post):
    """A post whose outcome is unknown. Never create a new container while it may be live."""
    cid = post.get("container_id")
    if not cid:
        post["status"] = "needs_reconciliation"
        post["last_error"] = "open state without container id"
        return
    code = container_status(cid)
    if code == "PUBLISHED":
        # It is live but we lost the media id. A person confirms the id; nothing is republished.
        post["status"] = "needs_reconciliation"
        post["last_error"] = "container reports PUBLISHED; confirm the media id on the profile"
    elif code == "FINISHED" and post["status"] == "container_created":
        post["status"] = "retryable_error"           # safe: never published, a fresh run may publish it
        post["last_error"] = "container finished, publish never attempted"
    elif code in ("EXPIRED", "ERROR"):
        post["status"] = "retryable_error"
        post["container_id"] = None
        post["last_error"] = f"container {code}; never published"
    else:
        post["status"] = "needs_reconciliation"
        post["last_error"] = f"publish outcome unknown (container {code}); manual check required"


# ---------------------------------------------------------------- modes

def run_dryrun(manifest, now):
    problems = validate_manifest(manifest)
    for problem in problems:
        warn(f"INVALID: {problem}")
    due, missed = select_due(manifest, now)
    for post in missed:
        log(f"Would mark missed: {post['id']} (slot {post['scheduled_utc']})")
    if not due:
        log("Nothing due.")
    for post in due:
        log(f"Would publish: {post['id']} ({post['type']}, slot {post['scheduled_utc']})")
    return 1 if problems else 0


def run_publish(manifest, now, persist_fn=None):
    persist_fn = persist_fn or (lambda msg: persist(manifest, msg))
    if os.environ.get("PUBLISH_ENABLED", "false").lower() != "true":
        log("Publishing is paused (PUBLISH_ENABLED is not true). Nothing touched.")
        return 0
    problems = validate_manifest(manifest)
    if problems:
        for problem in problems:
            warn(f"INVALID: {problem}")
        warn("Manifest invalid: nothing published.")
        return 1

    open_posts = [p for p in manifest["posts"] if p.get("status") in OPEN_STATES]
    due, missed = select_due(manifest, now)
    if not due and not open_posts and not missed:
        log("Nothing due.")                       # idle: no network has been touched
        return 0
    for post in missed:
        post["status"] = "missed"
        post["last_error"] = "slot passed without a publish; needs re-approval and a new slot"
        log(f"Missed slot logged: {post['id']}")
    if missed:
        persist_fn("missed slots logged")
    if not due and not open_posts:
        return 0

    try:
        ig_user_id = resolve_identity()
        for post in open_posts:
            reconcile(post)
            log(f"Reconciled {post['id']}: {post['status']}")
        if open_posts:
            persist_fn("reconciliation")
            if any(p["status"] == "needs_reconciliation" for p in manifest["posts"]):
                warn("A publish outcome is unknown: that format is frozen until it is confirmed by hand.")
            due, _ = select_due(manifest, now)
        quota = remaining_quota(ig_user_id)
        log(f"{len(due)} due, {quota} left in Meta's 24 h window")
        due = due[:max(quota, 0)]
    except StopRun as error:
        warn(f"STOP: {error}")
        return 1

    failures = 0
    for post in due:
        log(f"Publishing {post['id']} ({post['type']})")
        try:
            verify_public_media(manifest, post)
            publish_post(ig_user_id, manifest, post, persist_fn)
        except StopRun as error:
            post["last_error"] = str(error)[:300]
            if post["status"] in ("approved", "retryable_error"):
                post["status"] = "retryable_error"
            persist_fn(f"{post['id']} stopped")
            warn(f"STOP: {error}")
            return 1
        except TimeoutError as error:
            # The request may have reached Meta. Never retry blindly.
            failures += 1
            post["last_error"] = str(error)[:300]
            if post["status"] in OPEN_STATES:
                post["status"] = "needs_reconciliation"
            else:
                post["status"] = "retryable_error"
            persist_fn(f"{post['id']} timeout")
            warn(f"  TIMEOUT: {error}")
        except Exception as error:
            failures += 1
            post["last_error"] = redact(error)[:300]
            if post["status"] == "publish_pending":
                post["status"] = "needs_reconciliation"
            else:
                post["status"] = "blocked" if post.get("attempts", 0) >= MAX_ATTEMPTS else "retryable_error"
            persist_fn(f"{post['id']} failed")
            warn(f"  FAILED: {redact(error)}")
    return 1 if failures else 0


def run_selftest(manifest):
    """Identity, quota and one unpublished carousel item container. Never publishes."""
    problems = validate_manifest(manifest)
    if problems:
        for problem in problems:
            warn(f"INVALID: {problem}")
        return 1
    image = manifest.get("selftest_image")
    if not image:
        warn("selftest_image is not set in posts.json")
        return 1
    try:
        ig_user_id = resolve_identity()
        log(f"Quota left in Meta's 24 h window: {remaining_quota(ig_user_id)}")
        cid = call_graph(f"{ig_user_id}/media",
                         {"image_url": media_url(manifest, image), "is_carousel_item": "true"}, "POST")["id"]
        wait_until_finished(cid, "carousel")
    except (StopRun, RuntimeError, TimeoutError) as error:
        warn(f"SELFTEST FAILED: {error}")
        return 1
    log("PASS: identity, quota, image hosting and container creation work. Nothing was published.")
    return 0


def main(argv):
    now = datetime.now(timezone.utc)
    manifest = load_manifest()
    if "--dryrun" in argv:
        return run_dryrun(manifest, now)
    if "--selftest" not in argv and os.environ.get("PUBLISH_ENABLED", "false").lower() != "true":
        log("Publishing is paused (PUBLISH_ENABLED is not true). Nothing touched.")
        return 0                      # paused scheduled runs stay green and never need the token
    if not os.environ.get("IG_ACCESS_TOKEN"):
        warn("IG_ACCESS_TOKEN is not set")
        return 1
    if "--selftest" in argv:
        return run_selftest(manifest)
    return run_publish(manifest, now)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
