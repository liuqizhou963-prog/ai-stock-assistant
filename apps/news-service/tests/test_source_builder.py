import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_sources
# build_sources（信息源维护模块）


def make_source(name, url, hint="ai"):
    # make_source（创建测试信息源）
    return {
        "name": name,
        "hint": hint,
        "type": "rss",
        "url": url,
    }


class SourceBuilderTests(unittest.TestCase):
    def test_transient_failure_is_retried(self):
        attempts = []

        def checker(source):
            attempts.append(source["name"])

            if len(attempts) == 1:
                raise TimeoutError("测试超时")

            return {
                "ok": True,
                "entries": 3,
            }

        result = build_sources.inspect_source(
            make_source("测试源", "https://example.com/feed"),
            checker=checker,
            attempts=3,
            checked_at="2026-07-28T12:00:00+08:00",
        )

        self.assertEqual(result["status"], "active")
        self.assertEqual(result["attempts"], 2)

    def test_duplicate_url_is_blocked(self):
        candidates = [
            make_source("源 A", "https://example.com/feed"),
            make_source("源 B", "https://example.com/feed"),
        ]

        report = build_sources.build_report(
            candidates,
            checker=lambda source: {"ok": True, "entries": 1},
            checked_at="2026-07-28T12:00:00+08:00",
        )

        self.assertEqual(
            report["duplicates"],
            {"https://example.com/feed": ["源 A", "源 B"]},
        )

        with self.assertRaises(ValueError):
            build_sources.build_proposed_config(
                {"sources": candidates},
                report,
            )

    def test_single_failure_becomes_pending_review(self):
        source = make_source(
            "暂时失败的源",
            "https://example.com/temporary",
        )

        report = build_sources.build_report(
            [source],
            checker=lambda item: {"ok": False, "entries": 0},
            attempts=3,
            checked_at="2026-07-28T12:00:00+08:00",
        )

        self.assertEqual(len(report["inactive"]), 1)
        self.assertEqual(
            report["inactive"][0]["review"],
            "needs_review",
        )

    def test_inactive_existing_source_is_not_deleted(self):
        source = make_source(
            "现有源",
            "https://example.com/existing",
        )
        current = {"sources": [source]}

        report = build_sources.build_report(
            [source],
            checker=lambda item: {"ok": False, "entries": 0},
            attempts=3,
            checked_at="2026-07-28T12:00:00+08:00",
        )

        proposed = build_sources.build_proposed_config(
            current,
            report,
        )

        self.assertEqual(proposed["sources"], [source])
        self.assertEqual(
            proposed["maintenance"]["pending_review"],
            ["现有源"],
        )

    def test_new_active_source_appears_in_diff(self):
        old_source = make_source(
            "旧源",
            "https://example.com/old",
        )
        new_source = make_source(
            "新源",
            "https://example.com/new",
        )

        report = build_sources.build_report(
            [old_source, new_source],
            checker=lambda item: {"ok": True, "entries": 2},
            checked_at="2026-07-28T12:00:00+08:00",
        )

        old_config = {"sources": [old_source]}
        new_config = build_sources.build_proposed_config(
            old_config,
            report,
        )
        diff = build_sources.source_diff(
            old_config,
            new_config,
        )

        self.assertEqual(
            [source["name"] for source in diff["added"]],
            ["新源"],
        )
        self.assertEqual(diff["removed"], [])

    def test_config_requires_approval_before_writing(self):
        config = {
            "sources": [
                make_source("测试源", "https://example.com/feed"),
            ]
        }

        with TemporaryDirectory() as directory:
            path = Path(directory) / "sources.json"

            with self.assertRaises(PermissionError):
                build_sources.write_config(
                    config,
                    path,
                    approved=False,
                )

            build_sources.write_config(
                config,
                path,
                approved=True,
            )

            saved = json.loads(
                path.read_text(encoding="utf-8")
            )

        self.assertEqual(saved, config)


if __name__ == "__main__":
    unittest.main()
