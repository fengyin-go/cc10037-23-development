"""引用字典版本领域服务。

质量规则若只按表名读取地区字典，历史批次会随字典变化而“漂移”，坏行无法解释。
本服务把字典版本做成持久化的一等对象：
- 每个版本记录执行日期、引用列、冻结时间与完整条目快照；
- 补录门店地区对应值时派生新版本，旧版本继续保留；
- 校验只能绑定一个已确认版本，逐行留下门店代码取值依据。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.engine.reference_dictionary import (
    ReferenceDictionaryEngine,
    ReferenceEntry,
    ReferenceVersion,
)
from app.services.base import BaseModuleService
from app.store import store

VERSION_MODULE = "reference_dictionary_version"
CHANGE_MODULE = "reference_dictionary_change"


def _version_from_row(row: dict[str, Any]) -> ReferenceVersion:
    raw_entries = row.get("条目快照") or {}
    entries: dict[str, ReferenceEntry] = {}
    if isinstance(raw_entries, dict):
        for code, payload in raw_entries.items():
            if not isinstance(payload, dict):
                continue
            entries[str(code)] = ReferenceEntry(
                store_code=str(code),
                region_code=str(payload.get("region_code", "")),
                region_name=str(payload.get("region_name", "")),
                source=str(payload.get("来源", "")),
                effective_date=str(payload.get("生效日期", "")),
            )
    return ReferenceVersion(
        version_id=int(row.get("id", 0)),
        version_no=str(row.get("引用版本号", f"v{row.get('id', 0)}")),
        dictionary_name=str(row.get("引用字典", "地区引用字典")),
        dictionary_key=str(row.get("引用字典键", "region_reference")),
        table_name=str(row.get("引用表", "dim.dim_region_reference")),
        column_name=str(row.get("引用列", "store_code")),
        execution_date=str(row.get("字典执行日期", "")),
        frozen_at=str(row.get("字典冻结时间", "")),
        status=str(row.get("版本状态") or row.get("status") or ""),
        entries=entries,
        source_batch=str(row.get("来源批次", "")),
        note=str(row.get("版本说明", "")),
    )


def _next_id(rows: list[dict[str, Any]]) -> int:
    return max((int(row.get("id", 0)) for row in rows), default=0) + 1


class ReferenceDictionaryService(BaseModuleService):
    MODULE = VERSION_MODULE
    ENTITY = "引用字典版本"
    LIST_FIELDS = ["引用版本号", "引用字典", "引用表", "引用列", "字典执行日期",
                   "字典冻结时间", "字典条目数", "版本状态"]
    REQUIRED_FIELDS = ["引用版本号", "引用列"]
    STATUS_ORDER = ["草稿", "已确认", "历史", "已废弃"]
    ACTION_RULES = {"确认版本": "已确认", "废弃版本": "已废弃"}
    NEGATIVE_ACTIONS = ["废弃版本"]

    # ---- 读取 ----

    def versions(self) -> list[ReferenceVersion]:
        return [_version_from_row(row) for row in store.rows(VERSION_MODULE)]

    def engine(self) -> ReferenceDictionaryEngine:
        return ReferenceDictionaryEngine(self.versions())

    def version_row(self, version_id: int) -> dict[str, Any] | None:
        return store.find(VERSION_MODULE, version_id)

    def require_version(self, version_id: int) -> ReferenceVersion:
        return self.engine().require_confirmed(version_id)

    # ---- 写入 ----

    def add_version(
        self,
        *,
        base_version_id: int | None,
        entries: list[dict[str, Any]],
        execution_date: str | None = None,
        frozen_at: str | None = None,
        source_batch: str = "",
        note: str = "",
    ) -> dict[str, Any]:
        """在基线版本上补录地区条目，派生并持久化一个已确认的新版本。"""
        base = self.require_version(base_version_id) if base_version_id else None
        if base is None:
            raise ValueError("补录地区条目必须指定已确认的基线引用版本")
        if base.status != "已确认":
            raise ValueError(
                f"基线版本 {base.version_no} 状态为 {base.status}，"
                "只能从已确认的当前版本派生新版本，历史版本仅用于复查"
            )

        new_entries: dict[str, ReferenceEntry] = {}
        for raw in entries:
            code = str(raw.get("store_code") or raw.get("门店代码") or "").strip()
            if not code:
                raise ValueError("地区条目缺少门店代码 store_code")
            new_entries[code] = ReferenceEntry(
                store_code=code,
                region_code=str(raw.get("region_code") or raw.get("地区编码") or "").strip(),
                region_name=str(raw.get("region_name") or raw.get("地区名称") or "").strip(),
                source=str(raw.get("来源") or raw.get("source") or "人工补录"),
                effective_date=str(
                    raw.get("生效日期") or raw.get("effective_date") or execution_date or ""
                ),
            )
        if not new_entries:
            raise ValueError("至少需要一条地区条目")

        rows = store.rows(VERSION_MODULE)
        new_id = _next_id(rows)
        exec_date = execution_date or datetime.now().strftime("%Y-%m-%d")
        frozen = frozen_at or datetime.now().isoformat(timespec="seconds")
        version = self.engine().derive_version(
            base,
            new_entries,
            new_version_id=new_id,
            execution_date=exec_date,
            frozen_at=frozen,
            source_batch=source_batch,
            note=note or f"在 {base.version_no} 基础上补录 {len(new_entries)} 条地区条目",
        )

        row: dict[str, Any] = {
            "id": new_id,
            "status": "已确认",
            "pending": False,
            "abnormal": False,
            "版本ID": new_id,
            "引用版本号": version.version_no,
            "引用字典": version.dictionary_name,
            "引用字典键": version.dictionary_key,
            "引用表": version.table_name,
            "引用列": version.column_name,
            "字典执行日期": version.execution_date,
            "字典冻结时间": version.frozen_at,
            "字典条目数": str(version.entry_count()),
            "版本状态": "已确认",
            "基线版本": base.version_no,
            "来源批次": source_batch,
            "版本说明": version.note,
            "条目快照": version.snapshot(),
        }
        rows.append(row)

        # 历史版本保留，只把状态标记为历史，不删除、不改快照。
        base_row = self.version_row(base.version_id)
        if base_row is not None and base.status == "已确认":
            base_row["版本状态"] = "历史"
            base_row["status"] = "历史"

        change_rows = store.rows(CHANGE_MODULE)
        for code, entry in sorted(new_entries.items()):
            change_rows.append({
                "id": _next_id(change_rows),
                "status": "已确认",
                "pending": False,
                "abnormal": False,
                "变更类型": "ADD_ENTRY",
                "引用版本号": version.version_no,
                "基线版本号": base.version_no,
                "门店代码": code,
                "地区编码": entry.region_code,
                "地区名称": entry.region_name,
                "执行日期": version.execution_date,
                "冻结时间": version.frozen_at,
                "变更说明": version.note,
            })

        return row

    def snapshot_for(self, version_id: int) -> dict[str, dict[str, Any]]:
        version = self.engine().get(version_id)
        if version is None:
            return {}
        return version.snapshot()

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return None, f"{self.ENTITY} {entry_id} 不存在或已归档"
        if action == "确认版本" and entry.get("版本状态") == "历史":
            # 历史版本是已归档证据，不能再被“重新确认”覆盖。
            return None, "历史版本的条目快照已归档，不能重新确认；如需补录请从当前版本派生"
        if action == "确认版本" and not (entry.get("条目快照") or {}):
            # 空版本一旦确认会让所有门店代码都变成坏行，必须先有冻结快照。
            return None, "该版本还没有条目快照，不能确认；请先补录地区条目"
        entry, message = super().run_action(entry_id, action)
        if entry is not None:
            # 版本状态与通用 status 保持同步，避免两套状态字段漂移。
            entry["版本状态"] = entry.get("status")
        return entry, message


service = ReferenceDictionaryService()


class ReferenceDictionaryChangeService(BaseModuleService):
    """地区条目补录台账：每条补录都可回到派生出的字典版本。"""

    MODULE = CHANGE_MODULE
    ENTITY = "字典变更"
    LIST_FIELDS = ["变更类型", "引用版本号", "基线版本号", "门店代码", "地区编码",
                   "地区名称", "执行日期", "冻结时间"]
    REQUIRED_FIELDS = ["引用版本号", "门店代码"]
    STATUS_ORDER = ["待确认", "已确认", "已废弃"]
    ACTION_RULES = {"确认补录": "已确认", "废弃补录": "已废弃"}
    NEGATIVE_ACTIONS = ["废弃补录"]


change_service = ReferenceDictionaryChangeService()
