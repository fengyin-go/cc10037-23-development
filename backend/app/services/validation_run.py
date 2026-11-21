"""校验批次领域服务：执行质量校验批次、产出校验报告和异常标记。

上游：quality_rule 产出校验规则 → validation_run 执行校验批次
消费：alert_policy 消费校验结果触发告警
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.engine.reference_dictionary import ReferenceDictionaryEngine, ReferenceValidation
from app.services.base import BaseModuleService
from app.services.reference_dictionary import _version_from_row, VERSION_MODULE
from app.store import store


class ValidationRunService(BaseModuleService):
    MODULE = "validation_run"
    ENTITY = "校验批次"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["批次标识", "目标表", "校验分区", "总行数", "通过行数", "失败行数",
                   "校验耗时", "引用版本号", "坏行率"]
    REQUIRED_FIELDS = ["批次标识", "目标表", "校验分区"]
    STATUS_ORDER = ["校验中", "已通过", "未通过", "已阻断"]
    ACTION_RULES = {"确认通过": "校验中", "标记阻断": "未通过"}
    NEGATIVE_ACTIONS = []

    def query_by_table(self, table_name: str) -> list[dict[str, Any]]:
        """按目标表查询校验批次记录。

        从 store 中的校验批次数据里筛选指定表的批次，
        返回批次列表供质量趋势分析消费。
        """
        result: list[dict[str, Any]] = []
        for row in store.rows(self.MODULE):
            if table_name.casefold() in str(row.get("目标表", "")).casefold():
                result.append(dict(row))
        return result

    def compute_pass_rate(self, batch_id: str) -> dict[str, Any]:
        """计算校验批次的通过率。

        基于批次记录中的总行数和通过行数字段，
        计算通过率、失败率等核心质量指标。
        """
        target = None
        for row in store.rows(self.MODULE):
            if row.get("批次标识") == batch_id:
                target = row
                break
        if target is None:
            return {"error": f"批次 {batch_id} 不存在"}

        total = int(target.get("总行数", "0"))
        passed = int(target.get("通过行数", "0"))
        failed = int(target.get("失败行数", "0"))
        pass_rate = round(passed / max(total, 1) * 100, 2)
        fail_rate = round(failed / max(total, 1) * 100, 2)

        return {
            "batch_id": batch_id,
            "table": target.get("目标表"),
            "partition": target.get("校验分区"),
            "total_rows": total,
            "passed_rows": passed,
            "failed_rows": failed,
            "pass_rate_pct": pass_rate,
            "fail_rate_pct": fail_rate,
            "status": "通过" if pass_rate >= 99.9 else "需关注",
            "computed_at": datetime.now().isoformat(),
        }

    def aggregate_by_table(self) -> dict[str, Any]:
        """按目标表汇总校验批次统计。

        汇总所有校验批次数据，产出各表的质量指标总览，
        包括平均通过率和异常批次数量。
        """
        rows = store.rows(self.MODULE)
        table_stats: dict[str, dict[str, int]] = {}
        for row in rows:
            table = str(row.get("目标表", "未知"))
            if table not in table_stats:
                table_stats[table] = {"批次总数": 0, "通过批次": 0, "失败批次": 0, "阻断批次": 0,
                                       "累计总行": 0, "累计通过": 0, "累计失败": 0}
            stats = table_stats[table]
            stats["批次总数"] += 1
            status = str(row.get("status", ""))
            if status == "已通过":
                stats["通过批次"] += 1
            elif status == "未通过":
                stats["失败批次"] += 1
            elif status == "已阻断":
                stats["阻断批次"] += 1
            stats["累计总行"] += int(row.get("总行数", "0"))
            stats["累计通过"] += int(row.get("通过行数", "0"))
            stats["累计失败"] += int(row.get("失败行数", "0"))

        return {
            "tables": len(table_stats),
            "table_stats": {
                t: {
                    **s,
                    "通过率": round(s["累计通过"] / max(s["累计总行"], 1) * 100, 1),
                }
                for t, s in table_stats.items()
            },
            "snapshot_at": datetime.now().isoformat(),
        }

    def detect_degradation(self, table_name: str, threshold_pct: float = 95.0) -> dict[str, Any]:
        """检测数据质量退化趋势。

        对比最新两个校验批次的通过率，当通过率下降到阈值以下时
        标记质量退化并产出告警建议。
        """
        batches = self.query_by_table(table_name)
        if len(batches) < 2:
            return {"table": table_name, "degradation": "数据不足", "batch_count": len(batches)}

        sorted_batches = sorted(
            batches, key=lambda b: str(b.get("批次标识", "")), reverse=True
        )
        current = sorted_batches[0]
        previous = sorted_batches[1]

        cur_pass = int(current.get("通过行数", "0"))
        cur_total = int(current.get("总行数", "1"))
        prev_pass = int(previous.get("通过行数", "0"))
        prev_total = int(previous.get("总行数", "1"))

        cur_rate = round(cur_pass / max(cur_total, 1) * 100, 2)
        prev_rate = round(prev_pass / max(prev_total, 1) * 100, 2)
        delta = round(cur_rate - prev_rate, 2)

        is_degraded = cur_rate < threshold_pct and delta < 0
        return {
            "table": table_name,
            "current_pass_rate": cur_rate,
            "previous_pass_rate": prev_rate,
            "delta_pct": delta,
            "degraded": is_degraded,
            "threshold_pct": threshold_pct,
            "alert_recommendation": "建议触发质量告警" if is_degraded else "质量正常",
            "computed_at": datetime.now().isoformat(),
        }

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry, msg = super().run_action(entry_id, action)
        if entry:
            entry["last_operated_at"] = datetime.now().isoformat()
        return entry, msg

    # ---- 版本化地区引用字典 ----

    def reference_engine(self) -> ReferenceDictionaryEngine:
        """每次都从持久化的版本表重建引擎，历史版本永远可读。"""
        return ReferenceDictionaryEngine(
            _version_from_row(row) for row in store.rows(VERSION_MODULE)
        )

    def _reference_version_id(self, row: dict[str, Any]) -> int | None:
        raw = row.get("引用版本ID")
        if raw in (None, ""):
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def unversioned_batches(self) -> list[dict[str, Any]]:
        """没绑定引用版本的普通校验批次，汇总时单独说明，不与门店样本混算。"""
        result: list[dict[str, Any]] = []
        for row in store.rows(self.MODULE):
            if self._reference_version_id(row) is not None:
                continue
            result.append({
                "id": int(row.get("id", 0)),
                "批次标识": row.get("批次标识"),
                "状态": row.get("status"),
                "总行数": self._as_int(row.get("总行数")),
                "通过行数": self._as_int(row.get("通过行数")),
                "失败行数": self._as_int(row.get("失败行数")),
                "说明": "该批次未绑定引用字典版本，不参与按版本解释坏行率",
            })
        return result

    def reference_evidence(self, entry_id: int) -> dict[str, Any]:
        """按批次保留的证据解释分子分母，并可沿版本找到实际使用的地区条目。"""
        row = store.find(self.MODULE, entry_id)
        if row is None:
            return {"ok": False, "message": f"批次 {entry_id} 不存在或已归档"}

        version_id = self._reference_version_id(row)
        if version_id is None:
            return {
                "ok": False,
                "批次标识": row.get("批次标识"),
                "绑定了引用版本": False,
                "message": "该批次未绑定引用字典版本，无法按版本解释坏行率",
            }

        version = self.reference_engine().get(version_id)
        base = {
            "ok": True,
            "批次标识": row.get("批次标识"),
            "绑定了引用版本": True,
            "引用版本ID": version_id,
            "引用版本号": row.get("引用版本号"),
            "引用字典": row.get("引用字典"),
            "引用表": row.get("引用表"),
            "引用列": row.get("引用列"),
            "字典执行日期": row.get("字典执行日期"),
            "字典冻结时间": row.get("字典冻结时间"),
            "字典条目数": self._as_int(row.get("字典条目数")),
            "样本行数": self._as_int(row.get("样本行数") or row.get("总行数")),
            "匹配行数": self._as_int(row.get("匹配行数")),
            "未匹配行数": self._as_int(row.get("未匹配行数")),
            "坏行率": row.get("坏行率"),
            "坏行率分子": self._as_int(row.get("未匹配行数")),
            "坏行率分母": self._as_int(row.get("样本行数") or row.get("总行数")),
            "取值依据": row.get("取值依据"),
            "计算口径": row.get("计算口径"),
            "坏行明细": row.get("坏行明细") or [],
            "字典条目快照": row.get("字典快照") or {},
            "原始批次标识": row.get("原始批次标识") or "",
            "样本归档": bool(row.get("样本归档")),
            "核算状态": row.get("核算状态", ""),
        }
        if version is not None:
            samples = row.get("样本行") or []
            column_name = str(row.get("引用列") or version.column_name)
            base["版本状态"] = version.status
            base["版本是否已确认"] = version.confirmed
            base["按版本重算口径"] = {
                "分子": sum(
                    1 for sample in samples
                    if str(sample.get(column_name, "")) not in version.entries
                ),
                "分母": len(samples),
            }
        return base

    def reference_summary(self) -> dict[str, Any]:
        """质量执行汇总：每批都用自己保留的字典版本证据解释坏行率。"""
        batches: list[dict[str, Any]] = []
        for row in store.rows(self.MODULE):
            version_id = self._reference_version_id(row)
            if version_id is None:
                continue
            batches.append({
                "id": int(row.get("id", 0)),
                "批次标识": row.get("批次标识"),
                "状态": row.get("status"),
                "引用版本ID": version_id,
                "引用版本号": row.get("引用版本号"),
                "引用列": row.get("引用列"),
                "字典执行日期": row.get("字典执行日期"),
                "字典冻结时间": row.get("字典冻结时间"),
                "字典条目数": row.get("字典条目数"),
                "分子": row.get("未匹配行数"),
                "分母": row.get("样本行数"),
                "坏行率": row.get("坏行率"),
                "原始批次标识": row.get("原始批次标识") or "",
                "解释": row.get("计算口径"),
            })
        return {
            "batches": batches,
            "batch_count": len(batches),
            "versions": sorted({item["引用版本号"] for item in batches}),
            "unversioned_batches": self.unversioned_batches(),
            "unversioned_count": len(self.unversioned_batches()),
            "snapshot_at": datetime.now().isoformat(),
        }

    def review_batch(
        self,
        entry_id: int,
        *,
        version_id: int | None = None,
    ) -> dict[str, Any]:
        """沿批次证据复查坏行；只读，不替换已归档样本计数。"""
        row = store.find(self.MODULE, entry_id)
        if row is None:
            return {"ok": False, "完成": False, "message": f"批次 {entry_id} 不存在或已归档"}

        engine = self.reference_engine()
        resolved_id = version_id if version_id is not None else self._reference_version_id(row)
        if resolved_id is None:
            return {
                "ok": False, "完成": False, "批次标识": row.get("批次标识"),
                "message": "该批次未绑定引用版本，无法复查",
            }
        version = engine.get(resolved_id)
        if version is None:
            return {
                "ok": False, "完成": False, "批次标识": row.get("批次标识"),
                "message": f"引用版本 {resolved_id} 不存在，复查未完成",
            }
        if not version.usable_as_evidence:
            # 历史/已废弃版本仍可作为已归档批次的证据，草稿不行。
            return {
                "ok": False, "完成": False, "批次标识": row.get("批次标识"),
                "message": (
                    f"引用版本 {version.version_no} 没有冻结快照（状态 {version.status}），"
                    "不能用于复查"
                ),
            }

        samples = row.get("样本行") or []
        if not samples:
            return {
                "ok": False, "完成": False, "批次标识": row.get("批次标识"),
                "message": "该批次没有归档样本行，复查未完成；已归档样本计数保持不变",
            }

        column_name = str(row.get("引用列") or version.column_name)
        validation = engine.validate(samples, version, column_name, as_evidence=True)
        original_bad = {
            int(item.get("row_index", -1)): item for item in (row.get("坏行明细") or [])
        }

        reviewed_bad: list[dict[str, Any]] = []
        for item in validation.bad_rows:
            archived = original_bad.get(item["row_index"])
            reviewed_bad.append({
                **item,
                "原批结论": "坏行" if archived else "通过",
                "复查结论": "坏行",
                "是否原批坏行": archived is not None,
            })
        passed_original = [
            {
                "row_index": index,
                "store_code": original_bad[index].get("store_code"),
                "原批结论": "坏行",
                "复查结论": "通过",
                "原取值依据": original_bad[index].get("取值依据"),
                "复查取值依据": engine.match(
                    original_bad[index].get("store_code"), version, column_name,
                )[2],
                "复查引用版本号": version.version_no,
                "复查字典冻结时间": version.frozen_at,
            }
            for index in sorted(set(original_bad) - {item["row_index"] for item in validation.bad_rows})
        ]

        return {
            "ok": True,
            "完成": True,
            "只读复查": True,
            "批次标识": row.get("批次标识"),
            "引用版本ID": version.version_id,
            "引用版本号": version.version_no,
            "引用列": column_name,
            "字典执行日期": version.execution_date,
            "字典冻结时间": version.frozen_at,
            "字典条目数": version.entry_count(),
            "样本行数": validation.sample_count,
            "匹配行数": validation.matched_count,
            "未匹配行数": validation.unmatched_count,
            "坏行率": validation.bad_rate_text,
            "坏行率分子": validation.unmatched_count,
            "坏行率分母": validation.sample_count,
            "坏行明细": reviewed_bad,
            "原坏行复查通过": passed_original,
            "原坏行复查通过数": len(passed_original),
            "实际使用字典": version.snapshot(),
            "消息": "复查完成；未改写已归档批次的样本计数",
        }

    def recompute_batch(
        self,
        entry_id: int,
        *,
        version_id: int,
        batch_id: str | None = None,
        remark: str = "",
    ) -> tuple[dict[str, Any] | None, str]:
        """用指定已确认版本重算同一批行，把使用的版本和证据持久化为新批次。"""
        original = store.find(self.MODULE, entry_id)
        if original is None:
            return None, f"批次 {entry_id} 不存在或已归档"

        samples = original.get("样本行") or []
        if not samples:
            return None, "原批次没有归档样本行，未完成的复查不能替换已归档的样本计数"

        engine = self.reference_engine()
        try:
            version = engine.require_confirmed(int(version_id))
        except (LookupError, ValueError) as exc:
            return None, str(exc)

        column_name = str(original.get("引用列") or version.column_name)
        validation = engine.validate(samples, version, column_name)
        row = self._build_reference_batch(
            batch_id=batch_id or self._next_batch_id(str(original.get("批次标识", ""))),
            partition=str(original.get("校验分区", "")),
            target_table=str(original.get("目标表", "")),
            samples=samples,
            validation=validation,
            original_batch=str(original.get("批次标识", "")),
            remark=remark,
        )
        store.rows(self.MODULE).append(row)
        return row, (
            f"已按 {version.version_no} 重新核算并保存引用版本；"
            f"坏行 {validation.unmatched_count}/{validation.sample_count}"
        )

    def run_reference_rule(
        self,
        *,
        batch_id: str,
        target_table: str,
        partition: str,
        samples: list[dict[str, Any]],
        version_id: int,
        rule_id: int | None = None,
        remark: str = "",
    ) -> tuple[dict[str, Any] | None, str]:
        """用指定已确认版本对一批行首次执行引用规则，结果连同版本证据一起落库。"""
        if not samples:
            return None, "样本行不能为空"
        engine = self.reference_engine()
        try:
            version = engine.require_confirmed(int(version_id))
        except (LookupError, ValueError) as exc:
            return None, str(exc)

        column_name = version.column_name
        if rule_id is not None:
            rule = store.find("quality_rule", int(rule_id))
            if rule is not None:
                column_name = str(rule.get("引用列") or rule.get("校验字段") or column_name)

        validation = engine.validate(samples, version, column_name)
        row = self._build_reference_batch(
            batch_id=batch_id,
            partition=partition,
            target_table=target_table,
            samples=samples,
            validation=validation,
            original_batch="",
            remark=remark or f"按 {version.version_no} 首次执行引用完整性规则",
        )
        store.rows(self.MODULE).append(row)
        return row, (
            f"批次 {batch_id} 已按 {version.version_no} 执行；"
            f"坏行 {validation.unmatched_count}/{validation.sample_count}"
        )

    def _build_reference_batch(
        self,
        *,
        batch_id: str,
        partition: str,
        target_table: str,
        samples: list[dict[str, Any]],
        validation: ReferenceValidation,
        original_batch: str,
        remark: str,
    ) -> dict[str, Any]:
        """把一次基于明确版本的核算结果整理成可持久化批次行。"""
        rows = store.rows(self.MODULE)
        new_id = max((int(row.get("id", 0)) for row in rows), default=0) + 1
        evidence = validation.evidence()
        failed = validation.unmatched_count
        status = "已通过" if failed == 0 else "未通过"
        return {
            "id": new_id,
            "status": status,
            "pending": failed > 0,
            "abnormal": failed > 0,
            "批次标识": batch_id,
            "目标表": target_table,
            "校验分区": partition,
            "总行数": str(validation.sample_count),
            "通过行数": str(validation.matched_count),
            "失败行数": str(failed),
            "校验耗时": "0.0s",
            "引用版本ID": validation.version.version_id,
            "引用版本号": validation.version.version_no,
            "引用字典": validation.version.dictionary_name,
            "引用表": validation.version.table_name,
            "引用列": validation.column_name,
            "字典执行日期": validation.version.execution_date,
            "字典冻结时间": validation.version.frozen_at,
            "字典条目数": str(validation.version.entry_count()),
            "样本行数": str(validation.sample_count),
            "匹配行数": str(validation.matched_count),
            "未匹配行数": str(failed),
            "坏行率": validation.bad_rate_text,
            "取值依据": evidence["取值依据"],
            "计算口径": evidence["坏行率说明"],
            "坏行明细": validation.bad_rows,
            "样本行": [dict(sample) for sample in samples],
            "字典快照": validation.version.snapshot(),
            "原始批次标识": original_batch,
            "样本归档": True,
            "核算状态": "已完成",
            "核算完成时间": datetime.now().isoformat(timespec="seconds"),
            "核算备注": remark,
        }

    def _next_batch_id(self, batch_id: str) -> str:
        existing = {str(row.get("批次标识", "")) for row in store.rows(self.MODULE)}
        base = f"{batch_id}-R"
        index = 1
        while f"{base}{index}" in existing:
            index += 1
        return f"{base}{index}"

    def compare_reference_batches(
        self, original_id: int, candidate_id: int
    ) -> dict[str, Any]:
        """对比原批与重算批：哪些原坏行会通过，坏行率与字典版本分别是什么。"""
        original = store.find(self.MODULE, original_id)
        candidate = store.find(self.MODULE, candidate_id)
        if original is None or candidate is None:
            return {"ok": False, "message": "原批或重算批不存在"}
        if int(original.get("id", 0)) == int(candidate.get("id", 0)):
            return {"ok": False, "message": "同一批行只能按一个经确认的引用版本计算，不能和自己对比"}

        engine = self.reference_engine()
        original_version_id = self._reference_version_id(original)
        candidate_version_id = self._reference_version_id(candidate)
        if original_version_id is None or candidate_version_id is None:
            return {"ok": False, "message": "两个批次都必须绑定引用版本"}

        original_version = engine.get(original_version_id)
        candidate_version = engine.get(candidate_version_id)
        if original_version is None or candidate_version is None:
            return {"ok": False, "message": "引用版本不存在，无法对比"}

        samples = original.get("样本行") or candidate.get("样本行") or []
        # 对比是只读复查：两侧都可能已经是历史版本，但它们的冻结快照仍是各自证据。
        try:
            original_validation = engine.validate(
                samples, original_version,
                str(original.get("引用列") or original_version.column_name),
                as_evidence=True,
            )
            candidate_validation = engine.validate(
                samples, candidate_version,
                str(candidate.get("引用列") or candidate_version.column_name),
                as_evidence=True,
            )
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}
        diff = engine.compare(samples, original_validation, candidate_validation)

        return {
            "ok": True,
            "原批": {
                "id": original.get("id"),
                "批次标识": original.get("批次标识"),
                "引用版本ID": original_version.version_id,
                "引用版本号": original_version.version_no,
                "字典执行日期": original_version.execution_date,
                "字典冻结时间": original_version.frozen_at,
                "字典条目数": original_version.entry_count(),
                "坏行率": original.get("坏行率"),
                "坏行率分子": original.get("未匹配行数"),
                "坏行率分母": original.get("样本行数"),
                "坏行明细": original.get("坏行明细"),
            },
            "重算批": {
                "id": candidate.get("id"),
                "批次标识": candidate.get("批次标识"),
                "引用版本ID": candidate_version.version_id,
                "引用版本号": candidate_version.version_no,
                "字典执行日期": candidate_version.execution_date,
                "字典冻结时间": candidate_version.frozen_at,
                "字典条目数": candidate_version.entry_count(),
                "坏行率": candidate.get("坏行率"),
                "坏行率分子": candidate.get("未匹配行数"),
                "坏行率分母": candidate.get("样本行数"),
                "坏行明细": candidate.get("坏行明细"),
            },
            **diff,
        }