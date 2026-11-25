import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

PLUGIN = Path(__file__).resolve().parents[1] / "plugins/usage-analytics"
sys.path.insert(0, str(PLUGIN))
import analytics

# Native collector's request schema before its additive client migration.
SCHEMA = """CREATE TABLE requests (
    id TEXT PRIMARY KEY, stamp REAL NOT NULL, model TEXT NOT NULL, source TEXT NOT NULL,
    input INTEGER NOT NULL, output INTEGER NOT NULL, read INTEGER NOT NULL, write INTEGER NOT NULL
)"""


class UsageAnalyticsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.path = self.home / ".local/share/cage/token-usage/counters.sqlite3"
        self.path.parent.mkdir(parents=True)
        variable = patch.dict(os.environ, {"TZ": "UTC", "HOME": str(self.home)})
        variable.start()
        time.tzset()
        self.addCleanup(time.tzset)
        self.addCleanup(variable.stop)
        self.stamp = datetime(2026, 11, 25, 12, tzinfo=timezone.utc).timestamp()
        clock = patch.object(analytics.time, "localtime", return_value=time.localtime(self.stamp))
        clock.start()
        self.addCleanup(clock.stop)
        self.db = sqlite3.connect(self.path)
        self.addCleanup(self.db.close)
        self.db.execute(SCHEMA)
        self.db.commit()

    def insert(self, id="digest", stamp=None, model="claude-test", counts=(8, 31, 70, 22)):
        self.db.execute(
            'INSERT INTO requests(id, stamp, model, source, input, output, "read", "write") '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (id, self.stamp if stamp is None else stamp, model, "private-source", *counts),
        )
        self.db.commit()

    def read(self, **args):
        return analytics.read_usage(args, self.path)

    def test_four_counters_and_weighted_hit_rate(self):
        self.insert()
        self.insert("second", counts=(10, 2, 1, 9))
        result = self.read()
        totals = result["totals"]
        self.assertEqual(totals, {
            "input": 18, "output": 33, "read": 71, "write": 31,
            "requests": 2, "cache_hit_rate": 71 / 120,
        })
        self.assertEqual(len(result["trend"]), 7)
        for key, value in totals.items():
            self.assertEqual(result["trend"][-1][key], value)
        self.assertEqual(result["trend"][0]["requests"], 0)
        self.assertIsNone(result["trend"][0]["cache_hit_rate"])
        self.assertEqual(result["rows"][0]["client"], "unknown")
        self.assertNotIn("id", result["rows"][0])
        self.assertNotIn("source", result["rows"][0])

    def test_output_only_and_missing_rows_have_no_hit_rate(self):
        self.insert(counts=(0, 32, 0, 0))
        self.assertIsNone(self.read()["totals"]["cache_hit_rate"])
        filtered = self.read(model="absent")
        self.assertEqual(filtered["totals"]["requests"], 0)
        self.assertEqual(filtered["rows"], [])
        self.assertIsNone(filtered["totals"]["cache_hit_rate"])

    def test_exact_model_filter_and_model_catalog(self):
        self.insert()
        self.insert("other", model="different")
        self.insert("escaped", model="x' OR 1=1 --")
        result = self.read(model="x' OR 1=1 --")
        self.assertEqual(result["models"], ["claude-test", "different", "x' OR 1=1 --"])
        self.assertEqual(result["totals"]["requests"], 1)
        self.assertEqual(result["rows"][0]["model"], "x' OR 1=1 --")
        self.assertEqual(self.read(model="Claude-test")["rows"], [])

    def test_legacy_client_migration_is_visible_without_plugin_restart(self):
        self.insert()
        self.assertEqual(self.read()["rows"][0]["client"], "unknown")
        self.db.execute("ALTER TABLE requests ADD COLUMN client TEXT NOT NULL DEFAULT 'terminal'")
        self.db.commit()
        self.assertEqual(self.read()["rows"][0]["client"], "terminal")

    def test_stable_pagination_and_native_reset(self):
        for index in range(55):
            self.insert(f"digest-{index:03d}", counts=(index, 0, 0, 0))
        self.assertEqual([row["input"] for row in self.read(page=2)["rows"]], list(range(29, 4, -1)))
        last = self.read(page=100000)
        self.assertEqual((last["page"], last["last_page"]), (3, 3))
        self.assertEqual([row["input"] for row in last["rows"]], [4, 3, 2, 1, 0])
        self.db.execute("DELETE FROM requests")
        self.db.commit()
        cleared = self.read(page=3)
        self.assertEqual((cleared["page"], cleared["last_page"]), (1, 1))
        self.assertEqual(cleared["totals"]["requests"], 0)

    def test_matches_native_sqlite_local_day_across_dst(self):
        with patch.dict(os.environ, {"TZ": "America/New_York"}):
            time.tzset()
            self.addCleanup(time.tzset)
            self.addCleanup(os.environ.__setitem__, "TZ", "UTC")
            self.insert("previous", datetime(2026, 11, 1, 3, 59, tzinfo=timezone.utc).timestamp())
            self.insert("first", datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc).timestamp())
            self.insert("second", datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc).timestamp())
            self.insert("next", datetime(2026, 11, 2, 5, tzinfo=timezone.utc).timestamp())
            native = self.db.execute(
                "SELECT date(stamp, 'unixepoch', 'localtime'), count(*) FROM requests GROUP BY 1"
            ).fetchall()
            self.assertEqual(native, [("2026-10-31", 1), ("2026-11-01", 2), ("2026-11-02", 1)])
            report = self.read(days=30)
            self.assertEqual([(row["day"], row["requests"]) for row in report["trend"] if row["requests"]], native)

    def test_concurrent_writer_keeps_a_single_read_snapshot(self):
        self.db.execute("PRAGMA journal_mode=WAL")
        self.insert("before")
        original = analytics.report

        def with_writer(db, *args):
            self.insert("committed-during-read")
            return original(db, *args)

        with patch.object(analytics, "report", side_effect=with_writer):
            snapshot = self.read()
        self.assertEqual(snapshot["totals"]["requests"], 1)
        self.assertEqual(len(snapshot["rows"]), 1)
        self.assertEqual(self.read()["totals"]["requests"], 2)

    def test_read_only_connection_leaves_database_and_directory_unchanged(self):
        self.insert()
        before = hashlib.sha256(self.path.read_bytes()).digest()
        original = analytics.report

        def check_connection(db, *args):
            self.assertEqual(db.execute("PRAGMA query_only").fetchone()[0], 1)
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("DELETE FROM requests")
            db.execute("PRAGMA query_only = OFF")
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("DELETE FROM requests")
            return original(db, *args)

        with patch.object(analytics, "report", side_effect=check_connection):
            self.read()
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).digest(), before)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_missing_invalid_schema_and_link_fail_without_raw_paths(self):
        self.path.unlink()
        with self.assertRaisesRegex(analytics.UsageError, "^missing_database$"):
            self.read()
        self.assertFalse(self.path.exists())
        try:
            self.path.symlink_to(self.home / "unrelated")
            with self.assertRaisesRegex(analytics.UsageError, "^unavailable$"):
                self.read()
        finally:
            self.path.unlink(missing_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE requests (id TEXT)")
        with self.assertRaisesRegex(analytics.UsageError, "^unsupported_schema$"):
            self.read()

    def test_busy_is_reported_without_blocking_indefinitely(self):
        self.db.execute("BEGIN EXCLUSIVE")
        start = time.monotonic()
        with self.assertRaisesRegex(analytics.UsageError, "^busy$"):
            self.read()
        self.assertLess(time.monotonic() - start, 2)

    def test_invalid_filters(self):
        for args in ({"days": True}, {"days": 365}, {"model": "x\ny"}, {"page": 0},
                     {"page": True}, {"path": "anything"}, {"model": "x" * 129}):
            with self.subTest(args=args), self.assertRaisesRegex(analytics.UsageError, "^invalid_filters$"):
                self.read(**args)

    def test_stdio_mcp_tool_is_app_only_and_recovers_after_error(self):
        self.insert(stamp=time.time())
        messages = [
            {"id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"method": "notifications/initialized"},
            {"id": 2, "method": "tools/list"},
            {"id": 3, "method": "tools/call", "params": {
                "name": "usage_analytics_report", "arguments": {"days": 365}}},
            {"id": 4, "method": "tools/call", "params": {"name": "usage_analytics_report"}},
        ]
        exchange = subprocess.run(
            [sys.executable, "-B", str(PLUGIN / "server.py")], text=True,
            input="\n".join(json.dumps({"jsonrpc": "2.0", **message}) for message in messages) + "\n",
            capture_output=True, check=True, timeout=5,
        )
        replies = {reply["id"]: reply["result"] for reply in map(json.loads, exchange.stdout.splitlines())}
        self.assertEqual(set(replies), {1, 2, 3, 4})
        self.assertEqual(replies[1]["protocolVersion"], "2025-06-18")
        self.assertEqual(replies[2]["tools"][0]["_meta"]["ui"]["visibility"], ["app"])
        self.assertEqual(replies[3]["content"][0]["text"], "invalid_filters")
        payload = replies[4]["structuredContent"]
        self.assertEqual(payload["totals"]["requests"], 1)
        self.assertEqual(payload, json.loads(replies[4]["content"][0]["text"]))
        self.assertNotIn("private-source", exchange.stdout)


if __name__ == "__main__":
    unittest.main()
