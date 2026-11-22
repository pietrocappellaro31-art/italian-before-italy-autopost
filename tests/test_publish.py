"""Offline tests for publish.py. No token, no network: every Graph call is faked."""

import copy
import hashlib
import os
import sys
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import publish  # noqa: E402
from build import schedule  # noqa: E402

H = hashlib.sha256(b"x").hexdigest()
BASE = "https://raw.githubusercontent.com/pietrocappellaro31-art/italian-before-italy-autopost/main/media/"


def post(pid, kind, when, status="approved", **extra):
    media = {"carousel": ["a.jpg", "b.jpg"], "story": ["s.jpg"], "reel": ["r.mp4"]}[kind]
    p = {"id": pid, "lesson_id": "IBI-L0001", "type": kind, "scheduled_utc": when, "media": media,
         "caption_file": None if kind == "story" else "build/captions/x.clean.txt", "cover": None,
         "audio_kind": "native_recording" if kind == "reel" else "none", "ai_generated": False,
         "approval_id": "IBI-BATCH-TEST", "asset_hashes": {m: H for m in media} | {"caption": H},
         "status": status, "container_id": None, "published_id": None, "published_at_utc": None,
         "attempts": 0, "last_error": None}
    p.update(extra)
    return p


def manifest(*posts):
    return {"brand": "italian-before-italy", "expected_handle": "italianbeforeitaly",
            "media_base": BASE, "selftest_image": "a.jpg", "posts": list(posts)}


NOW = datetime(2026, 12, 1, 18, 0, tzinfo=timezone.utc)   # 13:00 ET, Tuesday


class FakeGraph:
    """Records calls; behaves like a healthy Graph API unless told otherwise."""

    def __init__(self, username="italianbeforeitaly", fail_publish=None, container_code="FINISHED"):
        self.calls, self.username, self.fail_publish, self.code = [], username, fail_publish, container_code
        self.n = 0

    def __call__(self, path, params=None, method="GET"):
        self.calls.append((method, path))
        if path == "me/accounts":
            return {"data": [{"instagram_business_account": {"id": "1784", "username": self.username}}]}
        if path.endswith("content_publishing_limit"):
            return {"data": [{"quota_usage": 0, "config": {"quota_total": 100}}]}
        if path.endswith("/media_publish"):
            if self.fail_publish:
                raise self.fail_publish
            return {"id": f"pub{self.n}"}
        if path.endswith("/media"):
            self.n += 1
            return {"id": f"c{self.n}"}
        return {"status_code": self.code}


class Base(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"IG_ACCESS_TOKEN": "dummy-token-123456", "PUBLISH_ENABLED": "true",
                                                "IG_EXPECTED_HANDLE": "italianbeforeitaly"}, clear=False)
        self.env.start()
        os.environ.pop("IG_USER_ID", None)
        os.environ.pop("STATE_PUSH", None)
        for target, value in (("verify_public_media", lambda m, p, fetch=None: None),
                              ("read_caption", lambda p: "caption"), ("time.sleep", lambda s: None)):
            patcher = mock.patch(f"publish.{target}", value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        self.env.stop()

    def run_publish(self, m, graph, now=NOW):
        with mock.patch("publish.call_graph", graph):
            return publish.run_publish(m, now, persist_fn=lambda msg: None)


class Validation(Base):
    def test_valid_manifest(self):
        self.assertEqual(publish.validate_manifest(manifest(post("a", "carousel", "2026-12-01T13:10:00Z"))), [])

    def test_placeholder_media_base_and_approval(self):
        m = manifest(post("a", "carousel", "2026-12-01T13:10:00Z", approval_id="OWNER-APPROVED-BATCH-ID"))
        m["media_base"] = "https://raw.githubusercontent.com/OWNER/REPO/main/media/"
        problems = " ".join(publish.validate_manifest(m))
        self.assertIn("media_base", problems)
        self.assertIn("placeholder", problems)

    def test_duplicate_ids_and_traversal(self):
        a = post("a", "carousel", "2026-12-01T13:10:00Z")
        b = post("a", "story", "2026-12-01T12:30:00Z", media=["../secret.jpg"])
        problems = " ".join(publish.validate_manifest(manifest(a, b)))
        self.assertIn("duplicate id", problems)
        self.assertIn("not allowed", problems)

    def test_ai_flag_must_be_reviewed(self):
        problems = publish.validate_manifest(manifest(post("a", "reel", "2026-12-01T17:35:00Z", ai_generated=None)))
        self.assertTrue(any("ai_generated" in p for p in problems))

    def test_story_has_no_caption(self):
        problems = publish.validate_post(post("s", "story", "2026-12-01T12:30:00Z", caption_file="x"))
        self.assertTrue(any("no caption" in p for p in problems))


class Scheduling(Base):
    def test_dst_slots(self):
        # 07:30 ET is 11:30 UTC in summer (EDT) and 12:30 UTC in winter (EST); 2026 DST ends 1 Nov.
        from datetime import date
        self.assertEqual(schedule.slot_utc(date(2026, 10, 31), "story"), "2026-10-31T11:30:00Z")
        self.assertEqual(schedule.slot_utc(date(2026, 11, 1), "story"), "2026-11-01T12:30:00Z")
        self.assertEqual(schedule.slot_utc(date(2027, 3, 14), "reel"), "2027-03-14T16:35:00Z")

    def test_one_per_format_per_day(self):
        m = manifest(post("c1", "carousel", "2026-12-01T13:10:00Z"), post("c2", "carousel", "2026-12-01T13:11:00Z"))
        due, _ = publish.select_due(m, NOW)
        self.assertEqual([p["id"] for p in due], ["c1"])

    def test_cap_exempt_second_reel(self):
        m = manifest(post("r1", "reel", "2026-12-01T17:35:00Z"), post("r2", "reel", "2026-12-01T17:40:00Z", cap_exempt="owner"))
        due, _ = publish.select_due(m, NOW)
        self.assertEqual([p["id"] for p in due], ["r1", "r2"])

    def test_weekly_cap(self):
        done = [post(f"p{i}", "story", "2026-11-30T12:30:00Z", status="published", published_id=str(i),
                     published_at_utc="2026-11-30T13:00:00+00:00") for i in range(21)]
        m = manifest(*done, post("c", "carousel", "2026-12-01T13:10:00Z"))
        due, _ = publish.select_due(m, NOW)
        self.assertEqual(due, [])

    def test_stale_backlog_is_missed_not_dumped(self):
        m = manifest(post("old", "carousel", "2026-11-29T13:10:00Z"), post("new", "carousel", "2026-12-01T13:10:00Z"))
        due, missed = publish.select_due(m, NOW)
        self.assertEqual([p["id"] for p in due], ["new"])
        self.assertEqual([p["id"] for p in missed], ["old"])

    def test_quiz_sequence_dependency(self):
        m = manifest(post("q1", "story", "2026-11-30T12:30:00Z", status="missed"),
                     post("q2", "story", "2026-12-01T12:30:00Z", requires_published="q1"))
        due, _ = publish.select_due(m, NOW)
        self.assertEqual(due, [])


class Publishing(Base):
    def test_idle_run_touches_no_network(self):
        graph = FakeGraph()
        self.assertEqual(self.run_publish(manifest(), graph), 0)
        self.assertEqual(graph.calls, [])

    def test_paused_flag(self):
        os.environ["PUBLISH_ENABLED"] = "false"
        graph = FakeGraph()
        m = manifest(post("c", "carousel", "2026-12-01T13:10:00Z"))
        self.run_publish(m, graph)
        self.assertEqual(graph.calls, [])
        self.assertEqual(m["posts"][0]["status"], "approved")

    def test_happy_path_all_formats(self):
        m = manifest(post("s", "story", "2026-12-01T12:30:00Z"), post("c", "carousel", "2026-12-01T13:10:00Z"),
                     post("r", "reel", "2026-12-01T17:35:00Z"))
        self.assertEqual(self.run_publish(m, FakeGraph()), 0)
        self.assertTrue(all(p["status"] == "published" and p["published_id"] for p in m["posts"]))

    def test_account_mismatch_stops_everything(self):
        graph = FakeGraph(username="805scorelab")
        m = manifest(post("c", "carousel", "2026-12-01T13:10:00Z"))
        self.assertEqual(self.run_publish(m, graph), 1)
        self.assertFalse(any(path.endswith("/media") for _, path in graph.calls))
        self.assertEqual(m["posts"][0]["status"], "approved")

    def test_timeout_after_publish_is_never_republished(self):
        m = manifest(post("c", "carousel", "2026-12-01T13:10:00Z"))
        self.run_publish(m, FakeGraph(fail_publish=TimeoutError("read timed out")))
        self.assertEqual(m["posts"][0]["status"], "needs_reconciliation")
        # next run: container says PUBLISHED -> still no new container, no media_publish
        graph = FakeGraph(container_code="PUBLISHED")
        self.run_publish(m, graph, now=NOW)
        self.assertFalse(any(path.endswith(("/media", "/media_publish")) for _, path in graph.calls))

    def test_died_between_publish_and_write(self):
        # state was persisted as publish_pending, then the job vanished
        m = manifest(post("c", "carousel", "2026-12-01T13:10:00Z", status="publish_pending", container_id="c9"))
        graph = FakeGraph(container_code="PUBLISHED")
        self.run_publish(m, graph)
        self.assertEqual(m["posts"][0]["status"], "needs_reconciliation")
        self.assertFalse(any(path.endswith("/media_publish") for _, path in graph.calls))

    def test_auth_failure_stops_without_retry_loop(self):
        def broken(path, params=None, method="GET"):
            raise publish.StopRun('Graph API 400: {"code":190}')
        m = manifest(post("c", "carousel", "2026-12-01T13:10:00Z"))
        with mock.patch("publish.call_graph", broken):
            self.assertEqual(publish.run_publish(m, NOW, persist_fn=lambda msg: None), 1)

    def test_token_redacted(self):
        self.assertNotIn("dummy-token-123456", publish.redact("error ... dummy-token-123456 ..."))


if __name__ == "__main__":
    unittest.main()
