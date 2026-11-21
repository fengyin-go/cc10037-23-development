import { request } from './client'
import { moduleMeta } from '@/data/modules'
import type {
  ActionResult,
  EntryRow,
  OverviewResult,
  PageResult,
  ReferenceComparison,
  ReferenceEvidence,
  ReferenceReviewResult,
  ReferenceRuleBinding,
  ReferenceSummary,
  ReferenceVersionRow,
} from '@/data/types'

export { moduleMeta }

export async function listEntries(
  key: string,
  filters: Record<string, string> = {},
): Promise<PageResult> {
  const query = new URLSearchParams(filters).toString()
  const response = await request(`/api/${key}?${query}`)
  if (!response.ok) throw new Error('业务数据读取失败')
  return await response.json()
}

export async function createEntry(
  key: string,
  values: Record<string, string>,
): Promise<ActionResult> {
  const response = await request(`/api/${key}`, {
    method: 'POST',
    body: JSON.stringify({ values }),
  })
  return await response.json()
}

export async function runAction(
  key: string,
  id: number,
  action: string,
): Promise<ActionResult> {
  const response = await request(`/api/${key}/${id}/actions`, {
    method: 'POST',
    body: JSON.stringify({ action }),
  })
  return await response.json()
}

export async function downloadEntries(
  key: string,
  filters: Record<string, string> = {},
): Promise<void> {
  const query = new URLSearchParams(filters).toString()
  const response = await request(`/api/${key}/export?${query}`)
  if (!response.ok) throw new Error('业务数据导出失败')
  const url = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${key}.csv`
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

export async function loadOverview(): Promise<OverviewResult> {
  const response = await request('/api/overview')
  if (!response.ok) throw new Error('运营概览读取失败')
  return await response.json()
}

async function readJson<T>(path: string, init?: RequestInit, fallback = '接口读取失败'): Promise<T> {
  const response = await request(path, init)
  const payload = await response.json().catch(() => null) as Record<string, unknown> | null
  if (!response.ok) {
    const detail = payload && typeof payload.detail === 'string' ? payload.detail : fallback
    throw new Error(detail)
  }
  return payload as T
}

export async function listReferenceVersions(): Promise<ReferenceVersionRow[]> {
  const payload = await readJson<{ items: ReferenceVersionRow[] }>(
    '/api/quality/reference-versions',
    undefined,
    '引用字典版本读取失败',
  )
  return payload.items ?? []
}

export async function loadReferenceEvidence(runId: number): Promise<ReferenceEvidence> {
  return readJson<ReferenceEvidence>(
    `/api/quality/validation-runs/${runId}/reference-evidence`,
    undefined,
    '批次字典版本证据读取失败',
  )
}

export async function loadReferenceSummary(): Promise<ReferenceSummary> {
  return readJson<ReferenceSummary>(
    '/api/quality/validation-runs/reference-summary',
    undefined,
    '质量执行汇总读取失败',
  )
}

export async function reviewReferenceRun(
  runId: number,
  versionId?: number,
): Promise<ReferenceReviewResult> {
  return readJson<ReferenceReviewResult>(
    `/api/quality/validation-runs/${runId}/review`,
    {
      method: 'POST',
      body: JSON.stringify(versionId == null ? {} : { version_id: versionId }),
    },
    '坏行复查失败',
  )
}

export async function recomputeReferenceRun(
  runId: number,
  versionId: number,
): Promise<ActionResult & { entry?: EntryRow }> {
  return readJson<ActionResult & { entry?: EntryRow }>(
    `/api/quality/validation-runs/${runId}/recompute`,
    { method: 'POST', body: JSON.stringify({ version_id: versionId }) },
    '按版本重算失败',
  )
}

export async function compareReferenceRuns(
  originalId: number,
  candidateId: number,
): Promise<ReferenceComparison> {
  return readJson<ReferenceComparison>(
    '/api/quality/validation-runs/compare',
    {
      method: 'POST',
      body: JSON.stringify({ original_id: originalId, candidate_id: candidateId }),
    },
    '批次对比失败',
  )
}

export async function listReferenceRules(): Promise<ReferenceRuleBinding[]> {
  const payload = await readJson<{ items: ReferenceRuleBinding[] }>(
    '/api/quality/reference-rules',
    undefined,
    '引用规则绑定读取失败',
  )
  return payload.items ?? []
}

export async function addRegionEntry(
  baseVersionId: number,
  entry: { store_code: string; region_code: string; region_name: string },
  executionDate: string,
): Promise<ActionResult> {
  return readJson<ActionResult>(
    '/api/quality/reference-versions',
    {
      method: 'POST',
      body: JSON.stringify({
        base_version_id: baseVersionId,
        entries: [entry],
        execution_date: executionDate,
      }),
    },
    '地区条目补录失败',
  )
}

export async function executeReferenceRun(payload: {
  batch_id: string
  target_table: string
  partition: string
  samples: Record<string, string>[]
  version_id: number
  rule_id?: number
}): Promise<ActionResult & { entry?: EntryRow }> {
  return readJson<ActionResult & { entry?: EntryRow }>(
    '/api/quality/validation-runs/execute',
    { method: 'POST', body: JSON.stringify(payload) },
    '引用规则执行失败',
  )
}
