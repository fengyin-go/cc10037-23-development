"""地区引用字典（版本化）校验引擎。

质量规则的 REFERENCE 校验不能只按表名去读“当前”字典，否则历史坏行无法回溯：
同一行在不同时间执行，命中的地区条目可能不同，坏行率也就无法解释。

这里把“表名”换成一个明确冻结的字典版本（ReferenceVersion）：
- 每个版本保存执行日期、引用列和完整条目快照，版本一经确认不可变；
- 新增条目不会改动旧版本，而是派生出后继版本，旧版本继续保留为历史证据；
- 一批行只允许绑定一个引用版本，坏行明细里逐行记录取值依据和解析到的地区。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


# 只有“已确认”的当前版本能参与新的计算；历史/已废弃版本退出计算范围，
# 但它们的冻结快照仍可作为已归档批次的复查证据（见 usable_as_evidence）。
CONFIRMED_STATUSES = frozenset({"已确认"})


@dataclass(frozen=True)
class ReferenceEntry:
    """字典版本里的一条门店地区条目。"""

    store_code: str
    region_code: str
    region_name: str
    source: str = ""
    effective_date: str = ""

    def evidence(self, version: "ReferenceVersion") -> str:
        return (
            f"{version.version_no} 快照行 store_code={self.store_code} "
            f"→ region_code={self.region_code}({self.region_name})，"
            f"执行日期 {version.execution_date}"
        )


@dataclass(frozen=True)
class ReferenceVersion:
    """一个冻结的引用字典版本。"""

    version_id: int
    version_no: str
    dictionary_name: str
    dictionary_key: str
    table_name: str
    column_name: str
    execution_date: str
    frozen_at: str
    status: str
    entries: dict[str, ReferenceEntry] = field(default_factory=dict)
    source_batch: str = ""
    note: str = ""

    @property
    def confirmed(self) -> bool:
        return self.status in CONFIRMED_STATUSES

    @property
    def usable_as_evidence(self) -> bool:
        """版本一旦冻结过，就永久可作为该批行的复查证据。

        草稿没有冻结快照，不能用于任何计算或复查；历史/已废弃版本只是
        退出了“可用于新计算”的范围，旧批次的证据链仍然有效。
        """
        return bool(self.entries) and self.status != "草稿"

    def entry_count(self) -> int:
        return len(self.entries)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        """输出可直接持久化的条目快照（含每条取值依据）。"""
        return {
            code: {
                "region_code": entry.region_code,
                "region_name": entry.region_name,
                "来源": entry.source,
                "生效日期": entry.effective_date,
                "取值依据": entry.evidence(self),
            }
            for code, entry in sorted(self.entries.items())
        }

    def header(self) -> dict[str, Any]:
        """版本级证据头：执行日期、引用列、冻结时间、条目数。"""
        return {
            "引用版本ID": self.version_id,
            "引用版本号": self.version_no,
            "引用字典": self.dictionary_name,
            "引用字典键": self.dictionary_key,
            "引用表": self.table_name,
            "引用列": self.column_name,
            "字典执行日期": self.execution_date,
            "字典冻结时间": self.frozen_at,
            "字典条目数": self.entry_count(),
            "字典版本状态": self.status,
        }


@dataclass
class ReferenceValidation:
    """一列门店代码按单个字典版本校验后的完整证据。"""

    version: ReferenceVersion
    column_name: str
    sample_rows: list[dict[str, Any]]
    bad_rows: list[dict[str, Any]]
    sample_count: int
    matched_count: int
    unmatched_count: int
    bad_rate: float

    @property
    def bad_rate_text(self) -> str:
        return f"{self.bad_rate:.1f}%"

    def evidence(self) -> dict[str, Any]:
        header = self.version.header()
        numerator = self.unmatched_count
        denominator = self.sample_count
        return {
            **header,
            **{
                "样本行数": denominator,
                "匹配行数": self.matched_count,
                "未匹配行数": numerator,
                "坏行率": self.bad_rate_text,
                "坏行率分子": numerator,
                "坏行率分母": denominator,
                "坏行率说明": (
                    f"坏行率 = 未匹配行数(分子) {numerator} / 样本行数(分母) {denominator}"
                    f" = {self.bad_rate_text}；分母取本批冻结样本，分子取"
                    f" {self.version.version_no} 中找不到对应地区条目的门店代码行数"
                ),
                "取值依据": (
                    f"行字段 {self.column_name} 逐行取值，按 {self.version.version_no}"
                    f" 于 {self.version.frozen_at} 冻结的 {self.version.entry_count()}"
                    f" 条地区条目匹配（执行日期 {self.version.execution_date}，"
                    f"引用列 {self.column_name}）"
                ),
                "字典快照": self.version.snapshot(),
            },
        }


class ReferenceDictionaryEngine:
    """按明确版本执行门店地区引用完整性校验。"""

    def __init__(self, versions: Iterable[ReferenceVersion] = ()) -> None:
        self._versions: dict[int, ReferenceVersion] = {
            version.version_id: version for version in versions
        }

    def register(self, version: ReferenceVersion) -> None:
        self._versions[version.version_id] = version

    def get(self, version_id: int) -> ReferenceVersion | None:
        return self._versions.get(version_id)

    def require_confirmed(self, version_id: int) -> ReferenceVersion:
        """同一批行只能使用一个已确认的引用版本，草稿版本直接拒绝。"""
        version = self.get(version_id)
        if version is None:
            raise LookupError(f"引用字典版本 {version_id} 不存在")
        if not version.confirmed:
            raise ValueError(
                f"引用字典版本 {version.version_no} 尚未确认（状态 {version.status}），"
                "不能用于校验"
            )
        return version

    def require_evidence(self, version_id: int) -> ReferenceVersion:
        """复查路径：只要求版本曾经冻结过，历史/已废弃版本仍可作为证据。"""
        version = self.get(version_id)
        if version is None:
            raise LookupError(f"引用字典版本 {version_id} 不存在")
        if not version.usable_as_evidence:
            raise ValueError(
                f"引用字典版本 {version.version_no} 没有冻结快照（状态 {version.status}），"
                "不能用于复查"
            )
        return version

    def match(
        self, value: Any, version: ReferenceVersion, column_name: str
    ) -> tuple[bool, ReferenceEntry | None, str]:
        """返回 (是否匹配, 命中的地区条目, 逐值取值依据)。"""
        code = "" if value is None else str(value)
        entry = version.entries.get(code)
        if entry is not None:
            return True, entry, (
                f"行字段 {column_name}={code}；命中 {version.version_no} 条目："
                f"region_code={entry.region_code}({entry.region_name})，"
                f"执行日期 {version.execution_date}，引用列 {column_name}"
            )
        if code == "":
            reason = (
                f"行字段 {column_name} 为空；{version.version_no} 无法匹配"
            )
        else:
            reason = (
                f"行字段 {column_name}={code}；按 {version.version_no}"
                f"（执行日期 {version.execution_date}，引用列 {column_name}）"
                f"冻结的 {version.entry_count()} 条地区条目匹配，无对应地区条目"
            )
        return False, None, reason

    def validate(
        self,
        rows: list[dict[str, Any]],
        version: ReferenceVersion,
        column_name: str = "store_code",
        *,
        as_evidence: bool = False,
    ) -> ReferenceValidation:
        """对整批行按同一个版本执行引用校验，产出逐行证据。

        as_evidence=True 用于复查已归档批次：此时历史/已废弃版本仍可用，
        因为它们当初确实冻结过这批行；草稿永远不可用。
        """
        allowed = version.usable_as_evidence if as_evidence else version.confirmed
        if not allowed:
            state = "草稿" if not version.entries or version.status == "草稿" else version.status
            raise ValueError(
                f"引用字典版本 {version.version_no} 状态为 {state}，不能用于校验"
            )
        matched = 0
        bad_rows: list[dict[str, Any]] = []
        sample_rows: list[dict[str, Any]] = []
        for index, row in enumerate(rows):
            value = row.get(column_name)
            ok, entry, basis = self.match(value, version, column_name)
            record = {
                "row_index": index,
                "order_id": row.get("order_id", ""),
                column_name: value,
            }
            sample_rows.append(record)
            if ok:
                matched += 1
                continue
            bad_rows.append({
                "row_index": index,
                "order_id": row.get("order_id", ""),
                column_name: value,
                "store_code": value,
                "field": column_name,
                "matched": False,
                "reason": f"引用缺失: {value if value not in (None, '') else 'NULL'}"
                          f" 不在 {version.table_name}({version.version_no}) 中",
                "引用版本ID": version.version_id,
                "引用版本号": version.version_no,
                "引用列": column_name,
                "字典执行日期": version.execution_date,
                "字典冻结时间": version.frozen_at,
                "取值依据": basis,
                "解析地区": None,
            })
        total = len(rows)
        bad_rate = round(len(bad_rows) / total * 100, 1) if total else 0.0
        return ReferenceValidation(
            version=version,
            column_name=column_name,
            sample_rows=sample_rows,
            bad_rows=bad_rows,
            sample_count=total,
            matched_count=matched,
            unmatched_count=len(bad_rows),
            bad_rate=bad_rate,
        )

    def compare(
        self,
        rows: list[dict[str, Any]],
        original: ReferenceValidation,
        candidate: ReferenceValidation,
    ) -> dict[str, Any]:
        """对比同一批行在两个版本下的结果，找出原坏行中会通过的与新增坏行。"""
        original_bad = {row["row_index"] for row in original.bad_rows}
        candidate_bad = {row["row_index"] for row in candidate.bad_rows}
        recovered = sorted(original_bad - candidate_bad)
        regressed = sorted(candidate_bad - original_bad)

        recovered_detail: list[dict[str, Any]] = []
        for row in original.bad_rows:
            if row["row_index"] not in recovered:
                continue
            value = row.get(candidate.column_name)
            _, entry, basis = self.match(
                value, candidate.version, candidate.column_name,
            )
            recovered_detail.append({
                **row,
                "复核结果": "通过",
                "新引用版本ID": candidate.version.version_id,
                "新引用版本号": candidate.version.version_no,
                "新字典执行日期": candidate.version.execution_date,
                "新字典冻结时间": candidate.version.frozen_at,
                "新引用列": candidate.column_name,
                "新取值依据": basis,
                "新解析地区": (
                    {
                        "store_code": value,
                        "region_code": entry.region_code,
                        "region_name": entry.region_name,
                        "来源": entry.source,
                        "生效日期": entry.effective_date,
                    }
                    if entry is not None else None
                ),
            })

        return {
            "样本行数": len(rows),
            "原坏行数": len(original_bad),
            "新坏行数": len(candidate_bad),
            "原坏行通过数": len(recovered),
            "新增坏行数": len(regressed),
            "原引用版本号": original.version.version_no,
            "新引用版本号": candidate.version.version_no,
            "原坏行通过明细": recovered_detail,
            "新增坏行明细": [
                row for row in candidate.bad_rows if row["row_index"] in regressed
            ],
        }

    def next_version_no(self, version_no: str) -> str:
        """REGION-v2 → REGION-v3；不改变历史版本号。"""
        prefix, _, suffix = version_no.rpartition("-v")
        if not prefix or not suffix.isdigit():
            return f"{version_no}-v2"
        return f"{prefix}-v{int(suffix) + 1}"

    def derive_version(
        self,
        base: ReferenceVersion,
        entries: dict[str, ReferenceEntry],
        *,
        new_version_id: int,
        execution_date: str,
        frozen_at: str,
        source_batch: str = "",
        note: str = "",
    ) -> ReferenceVersion:
        """在旧版本基础上补录条目，派生新的已确认版本，旧版本原样保留。"""
        merged = dict(base.entries)
        merged.update({code: entry for code, entry in entries.items()})
        return ReferenceVersion(
            version_id=new_version_id,
            version_no=self.next_version_no(base.version_no),
            dictionary_name=base.dictionary_name,
            dictionary_key=base.dictionary_key,
            table_name=base.table_name,
            column_name=base.column_name,
            execution_date=execution_date,
            frozen_at=frozen_at,
            status="已确认",
            entries=merged,
            source_batch=source_batch,
            note=note or f"在 {base.version_no} 基础上补录 {len(entries)} 条地区条目",
        )
