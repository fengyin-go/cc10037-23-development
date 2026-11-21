"""地区引用字典与按版本核算的质量执行接口。

这里的路径全部是静态前缀，必须在通用资源路由 `/api/{module}` 之前注册，
否则会被动态段抢先匹配。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.services.quality_rule import QualityRuleService
from app.services.reference_dictionary import change_service, service as version_service
from app.services.validation_run import ValidationRunService
from app.store import store

router = APIRouter(prefix="/api/quality", tags=["质量引用版本"])

_run_service = ValidationRunService()
_rule_service = QualityRuleService()


# ---- 引用字典版本 ----

@router.get("/reference-versions")
def list_reference_versions() -> dict[str, Any]:
    """列出全部地区引用字典版本（含历史版本）。"""
    rows = [dict(row) for row in version_service.list_entries(size=1000)[0]]
    return {"items": rows, "total": len(rows)}


@router.get("/reference-versions/{version_id}")
def get_reference_version(version_id: int) -> dict[str, Any]:
    """读取单个版本，返回条目快照与版本级证据头。"""
    engine = version_service.engine()
    version = engine.get(version_id)
    if version is None:
        raise HTTPException(status_code=404, detail=f"引用版本 {version_id} 不存在")
    return {
        **version.header(),
        "版本说明": version.note,
        "来源批次": version.source_batch,
        "版本是否已确认": version.confirmed,
        "条目快照": version.snapshot(),
    }


@router.post("/reference-versions")
def create_reference_version(body: dict[str, Any]) -> dict[str, Any]:
    """补录地区条目，派生并持久化新版本；旧版本保留为历史。

    body:
      base_version_id, entries: [{store_code, region_code, region_name}],
      execution_date, frozen_at, source_batch, note
    """
    try:
        row = version_service.add_version(
            base_version_id=body.get("base_version_id"),
            entries=body.get("entries", []),
            execution_date=body.get("execution_date"),
            frozen_at=body.get("frozen_at"),
            source_batch=str(body.get("source_batch", "")),
            note=str(body.get("note", "")),
        )
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "message": f"已派生引用版本 {row.get('引用版本号')}", "entry": row}


@router.get("/reference-changes")
def list_reference_changes() -> dict[str, Any]:
    """列出地区条目补录台账。"""
    rows = [dict(row) for row in change_service.list_entries(size=1000)[0]]
    return {"items": rows, "total": len(rows)}


# ---- 质量执行：按版本核算 ----

@router.get("/rules/{entry_id}/reference-binding")
def get_rule_reference_binding(entry_id: int) -> dict[str, Any]:
    """查看引用完整性规则绑定的引用表、引用列和引用字典。"""
    result = _rule_service.reference_rule(entry_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result["message"])
    return result


@router.get("/reference-rules")
def list_reference_rules() -> dict[str, Any]:
    """列出所有引用完整性规则及其引用列绑定。"""
    items = []
    for row in store.rows("quality_rule"):
        if str(row.get("校验类型", "")).upper() != "REFERENCE" and not row.get("引用列"):
            continue
        items.append(_rule_service.reference_rule(int(row.get("id", 0))))
    return {"items": items, "total": len(items)}


@router.get("/validation-runs/{entry_id}/reference-evidence")
def get_reference_evidence(entry_id: int) -> dict[str, Any]:
    """读取批次保留的字典版本证据：执行日期、引用列、分子分母与门店代码取值依据。"""
    result = _run_service.reference_evidence(entry_id)
    if not result.get("ok") and "不存在" in str(result.get("message", "")):
        raise HTTPException(status_code=404, detail=result["message"])
    return result


@router.get("/validation-runs/reference-summary")
def get_reference_summary() -> dict[str, Any]:
    """质量执行汇总：每批用自己保留的字典版本证据解释坏行率。"""
    return _run_service.reference_summary()


@router.post("/validation-runs/{entry_id}/review")
def review_validation_run(entry_id: int, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """只读复查坏行；可指定 version_id 沿证据找到实际使用的地区条目。"""
    body = body or {}
    version_id = body.get("version_id")
    result = _run_service.review_batch(
        entry_id, version_id=int(version_id) if version_id is not None else None,
    )
    if not result.get("ok") and "不存在" in str(result.get("message", "")):
        raise HTTPException(status_code=404, detail=result["message"])
    return result


@router.post("/validation-runs/{entry_id}/recompute")
def recompute_validation_run(entry_id: int, body: dict[str, Any]) -> dict[str, Any]:
    """用指定已确认版本重算原批样本，保存使用的引用版本。

    body: version_id, batch_id (可选), remark (可选)
    """
    if "version_id" not in body:
        raise HTTPException(status_code=400, detail="缺少 version_id：重算必须指定已确认的引用版本")
    row, message = _run_service.recompute_batch(
        entry_id,
        version_id=int(body["version_id"]),
        batch_id=body.get("batch_id"),
        remark=str(body.get("remark", "")),
    )
    if row is None:
        raise HTTPException(status_code=400, detail=message)
    return {"ok": True, "message": message, "entry": row}


@router.post("/validation-runs/compare")
def compare_validation_runs(body: dict[str, Any]) -> dict[str, Any]:
    """对比原批与重算批，列出原坏行中会通过的行。"""
    try:
        original_id = int(body["original_id"])
        candidate_id = int(body["candidate_id"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=400, detail="需要 original_id 与 candidate_id")
    result = _run_service.compare_reference_batches(original_id, candidate_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message", "对比失败"))
    return result


@router.post("/validation-runs/execute")
def execute_reference_run(body: dict[str, Any]) -> dict[str, Any]:
    """用指定版本首次执行引用规则。

    body: batch_id, target_table, partition, samples, version_id, rule_id (可选)
    """
    missing = [key for key in ("batch_id", "version_id", "samples") if key not in body]
    if missing:
        raise HTTPException(status_code=400, detail=f"缺少参数：{'、'.join(missing)}")
    row, message = _run_service.run_reference_rule(
        batch_id=str(body["batch_id"]),
        target_table=str(body.get("target_table", "dw.dwd_order_wide")),
        partition=str(body.get("partition", "")),
        samples=list(body["samples"]),
        version_id=int(body["version_id"]),
        rule_id=body.get("rule_id"),
        remark=str(body.get("remark", "")),
    )
    if row is None:
        raise HTTPException(status_code=400, detail=message)
    return {"ok": True, "message": message, "entry": row}
