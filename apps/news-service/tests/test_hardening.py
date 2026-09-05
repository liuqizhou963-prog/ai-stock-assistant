import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import data_store
# data_store（网页数据契约和原子写入模块）


def valid_data():
    # valid_data（创建合法的网页数据样本）
    return {
        "schema_version": 1,
        "generated_at": "2026-07-28T12:00:00+08:00",
        "recent_days": 7,
        "industries": [],
        "stats": {},
        "has_ai": False,
    }


class DataStoreTests(unittest.TestCase):
    def test_write_adds_schema_version(self):
        data = valid_data()
        data.pop("schema_version")

        with TemporaryDirectory() as directory:
            path = Path(directory) / "data.js"
            data_store.write_data_file(data, path)
            loaded = data_store.load_data_file(path)

        self.assertEqual(loaded["schema_version"], 1)

    def test_invalid_data_is_rejected_before_replacement(self):
        old_data = valid_data()

        with TemporaryDirectory() as directory:
            path = Path(directory) / "data.js"
            data_store.write_data_file(old_data, path)

            invalid = dict(old_data)
            invalid.pop("industries")

            with self.assertRaises(ValueError):
                data_store.write_data_file(invalid, path)

            self.assertEqual(
                data_store.load_data_file(path),
                old_data,
            )

    def test_replace_failure_keeps_previous_file(self):
        old_data = valid_data()
        new_data = dict(old_data)
        new_data["generated_at"] = "2026-07-28T13:00:00+08:00"

        with TemporaryDirectory() as directory:
            path = Path(directory) / "data.js"
            data_store.write_data_file(old_data, path)

            with patch(
                "data_store.os.replace",
                side_effect=OSError("测试中断"),
            ):
                with self.assertRaises(OSError):
                    data_store.write_data_file(new_data, path)

            self.assertEqual(
                data_store.load_data_file(path),
                old_data,
            )
            self.assertFalse(Path(str(path) + ".candidate").exists())


if __name__ == "__main__":
    unittest.main()
