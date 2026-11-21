"""地区引用字典版本与按版本核算的回归测试。

只依赖标准库，直接对领域服务和引擎断言：
    cd backend && .venv/bin/python -m unittest discover -s tests -v
"""
from __future__ import annotations

import copy
import unittest

from app.engine.reference_dictionary import (
    ReferenceDictionaryEngine,
    ReferenceEntry,
    ReferenceVersion,
)
from app.services.quality_rule import QualityRuleService
from app.services.reference_dictionary import service as version_service
from app.services.validation_run import ValidationRunService
from app.store import store
from app.seed import SEED_ROWS


def reset_store() -> None:
    store._tables = {name: [copy.deepcopy(row) for row in rows]
                     for name, rows in SEED_ROWS.items()}


class ReferenceVersionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        reset_store()
        self.runs = ValidationRunService()
        self.rules = QualityRuleService()
        self.versions = version_service

    def test_same_batch_uses_exactly_one_confirmed_version(self) -> None:
        draft, _ = self.versions.create_entry({
            "引用版本号": "REGION-draft",
            "引用列": "store_code",
            "字典执行日期": "2026-11-21",
        })
        self.assertIsNotNone(draft)
        self.assertEqual(draft["status"], "草稿")

        row, message = self.runs.recompute_batch(5, version_id=draft["id"])
        self.assertIsNone(row)
        self.assertIn("尚未确认", message)

        row, _ = self.runs.recompute_batch(5, version_id=2)
        self.assertIsNotNone(row)
        self.assertEqual(row["引用版本ID"], 2)
        self.assertEqual(row["引用列"], "store_code")
        self.assertEqual(row["样本行数"], "8")

    def test_evidence_explains_numerator_and_denominator(self) -> None:
        evidence = self.runs.reference_evidence(5)
        self.assertTrue(evidence["ok"])
        self.assertEqual(evidence["引用版本号"], "REGION-v1")
        self.assertEqual(evidence["坏行率分子"], 1)
        self.assertEqual(evidence["坏行率分母"], 8)
        self.assertEqual(evidence["坏行率"], "12.5%")
        self.assertEqual(evidence["字典执行日期"], "2026-11-17")
        self.assertEqual(evidence["引用列"], "store_code")
        self.assertEqual(evidence["版本状态"], "历史")
        self.assertIn("S006", evidence["坏行明细"][0]["取值依据"])

    def test_review_is_read_only_and_keeps_archived_counts(self) -> None:
        before = copy.deepcopy(store.find("validation_run", 5))
        review = self.runs.review_batch(5)
        after = store.find("validation_run", 5)
        self.assertTrue(review["完成"])
        self.assertTrue(review["只读复查"])
        self.assertEqual(before["失败行数"], after["失败行数"])
        self.assertEqual(before["坏行明细"], after["坏行明细"])
        self.assertEqual(review["坏行率"], "12.5%")

    def test_incomplete_review_does_not_replace_archived_counts(self) -> None:
        batch = store.find("validation_run", 5)
        batch["样本行"] = []
        result = self.runs.review_batch(5)
        self.assertFalse(result["完成"])
        self.assertIn("样本计数保持不变", result["message"])

    def test_supplement_derives_new_version_and_keeps_history(self) -> None:
        new_row = self.versions.add_version(
            base_version_id=2,
            entries=[{"store_code": "S007", "region_code": "R07", "region_name": "西北-西安"}],
            execution_date="2026-11-21",
            frozen_at="2026-11-21T09:00:00",
        )
        self.assertEqual(new_row["引用版本号"], "REGION-v3")
        self.assertEqual(new_row["版本状态"], "已确认")
        self.assertEqual(new_row["字典条目数"], "7")
        self.assertEqual(store.find("reference_dictionary_version", 2)["版本状态"], "历史")
        # 历史版本仍然可读，条目不变
        old = self.versions.engine().get(1)
        self.assertIsNotNone(old)
        self.assertEqual(old.entry_count(), 5)
        self.assertNotIn("S006", old.entries)

    def test_cannot_derive_from_historical_version(self) -> None:
        with self.assertRaises(ValueError):
            self.versions.add_version(
                base_version_id=1,
                entries=[{"store_code": "S009", "region_code": "R09", "region_name": "测试"}],
            )

    def test_recompute_persists_version_without_touching_original(self) -> None:
        original_before = copy.deepcopy(store.find("validation_run", 5))
        row, _ = self.runs.recompute_batch(5, version_id=2)
        self.assertIsNotNone(row)
        self.assertEqual(row["引用版本ID"], 2)
        self.assertEqual(row["引用版本号"], "REGION-v2")
        self.assertEqual(row["失败行数"], "0")
        self.assertEqual(row["原始批次标识"], original_before["批次标识"])
        self.assertEqual(store.find("validation_run", 5), original_before)
        # 新批次可独立复查，旧批次仍按原版本复查
        self.assertEqual(self.runs.review_batch(row["id"])["引用版本号"], "REGION-v2")
        self.assertEqual(self.runs.review_batch(5)["引用版本号"], "REGION-v1")

    def test_compare_reports_rows_recovered_by_new_version(self) -> None:
        new_row, _ = self.runs.recompute_batch(5, version_id=2)
        comparison = self.runs.compare_reference_batches(5, new_row["id"])
        self.assertTrue(comparison["ok"])
        self.assertEqual(comparison["原坏行通过数"], 1)
        self.assertEqual(comparison["新增坏行数"], 0)
        recovered = comparison["原坏行通过明细"][0]
        self.assertEqual(recovered["store_code"], "S006")
        self.assertEqual(recovered["新解析地区"]["region_name"], "华中-武汉")
        self.assertEqual(comparison["原批"]["引用版本号"], "REGION-v1")
        self.assertEqual(comparison["重算批"]["引用版本号"], "REGION-v2")

    def test_compare_rejects_same_batch(self) -> None:
        result = self.runs.compare_reference_batches(5, 5)
        self.assertFalse(result["ok"])

    def test_rule_binding_uses_reference_column_not_table_name(self) -> None:
        binding = self.rules.reference_rule(7)
        self.assertTrue(binding["引用完整性规则"])
        self.assertEqual(binding["引用列"], "store_code")
        self.assertEqual(binding["引用表"], "dim.dim_region_reference")

    def test_deprecated_version_still_serves_as_review_evidence(self) -> None:
        # 已归档批次绑定的版本即使被废弃，也必须还能只读复查。
        self.versions.run_action(2, "废弃版本")
        review = self.runs.review_batch(6)
        self.assertTrue(review["完成"])
        self.assertEqual(review["引用版本号"], "REGION-v2")
        self.assertEqual(review["坏行率"], "0.0%")
        # 但它不能再用于任何新计算。
        row, message = self.runs.recompute_batch(5, version_id=2)
        self.assertIsNone(row)
        self.assertIn("已废弃", message)

    def test_compare_works_after_both_versions_become_history(self) -> None:
        new_row, _ = self.runs.recompute_batch(5, version_id=2)
        # 再派生一版，让原批和重算批绑定的版本都退为历史
        self.versions.add_version(
            base_version_id=2,
            entries=[{"store_code": "S007", "region_code": "R07", "region_name": "西北-西安"}],
        )
        self.assertEqual(store.find("reference_dictionary_version", 2)["版本状态"], "历史")
        comparison = self.runs.compare_reference_batches(5, new_row["id"])
        self.assertTrue(comparison["ok"])
        self.assertEqual(comparison["原坏行通过数"], 1)
        self.assertEqual(comparison["原批"]["引用版本号"], "REGION-v1")

    def test_history_version_cannot_be_reconfirmed(self) -> None:
        entry, message = self.versions.run_action(1, "确认版本")
        self.assertIsNone(entry)
        self.assertIn("历史版本", message)


class ReferenceDictionaryEngineTestCase(unittest.TestCase):
    def _version(self, version_id: int = 1, status: str = "已确认") -> ReferenceVersion:
        return ReferenceVersion(
            version_id=version_id,
            version_no="REGION-v1",
            dictionary_name="地区引用字典",
            dictionary_key="region_reference",
            table_name="dim.dim_region_reference",
            column_name="store_code",
            execution_date="2026-11-17",
            frozen_at="2026-11-18T05:00:00",
            status=status,
            entries={
                "S001": ReferenceEntry("S001", "R01", "华东-上海"),
            },
        )

    def test_validate_emits_per_row_evidence(self) -> None:
        engine = ReferenceDictionaryEngine([self._version()])
        result = engine.validate(
            [{"order_id": "A", "store_code": "S001"}, {"order_id": "B", "store_code": "S999"}],
            self._version(),
        )
        self.assertEqual((result.matched_count, result.unmatched_count), (1, 1))
        bad = result.bad_rows[0]
        self.assertEqual(bad["store_code"], "S999")
        self.assertEqual(bad["引用版本号"], "REGION-v1")
        self.assertEqual(bad["字典执行日期"], "2026-11-17")
        self.assertIn("store_code=S999", bad["取值依据"])

    def test_draft_version_cannot_validate(self) -> None:
        draft = self._version(status="草稿")
        engine = ReferenceDictionaryEngine([draft])
        with self.assertRaises(ValueError):
            engine.validate([{"store_code": "S001"}], draft)
        with self.assertRaises(ValueError):
            engine.require_confirmed(1)

    def test_compare_matches_rows_by_index(self) -> None:
        old = self._version(version_id=1)
        new = ReferenceVersion(
            version_id=2, version_no="REGION-v2", dictionary_name=old.dictionary_name,
            dictionary_key=old.dictionary_key, table_name=old.table_name,
            column_name=old.column_name, execution_date="2026-11-19",
            frozen_at="2026-11-19T10:30:00", status="已确认",
            entries={**old.entries, "S999": ReferenceEntry("S999", "R99", "测试区")},
        )
        engine = ReferenceDictionaryEngine([old, new])
        rows = [{"store_code": "S001"}, {"store_code": "S999"}]
        diff = engine.compare(rows, engine.validate(rows, old), engine.validate(rows, new))
        self.assertEqual(diff["原坏行通过数"], 1)
        self.assertEqual(diff["新增坏行数"], 0)
        self.assertEqual(diff["原坏行通过明细"][0]["新解析地区"]["region_code"], "R99")


if __name__ == "__main__":
    unittest.main()
