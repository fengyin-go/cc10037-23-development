<template>
  <section class="ref-panel" data-testid="reference-panel">
    <header class="ref-head">
      <div>
        <h3>地区引用字典版本证据</h3>
        <p class="page-desc">
          每个质量执行批次只按一个经确认的引用版本计算，分子分母都由此批冻结的字典版本解释；
          补录地区条目会派生新版本，历史版本继续保留供复查。
        </p>
      </div>
      <button class="btn" type="button" data-testid="reference-refresh" @click="refreshAll">刷新报表</button>
    </header>

    <p v-if="panelError" class="error-text" data-testid="reference-error">{{ panelError }}</p>
    <p v-if="panelMessage" class="ref-message" data-testid="reference-message">{{ panelMessage }}</p>

    <article class="ref-card" data-testid="ref-rules">
      <h4>引用完整性规则绑定</h4>
      <p class="ref-note">规则按引用列绑定到具体字典版本；表名只用于展示来源，不参与版本判定。</p>
      <table class="data-table">
        <thead>
          <tr><th>规则</th><th>引用表</th><th>引用列</th><th>引用字典</th><th>阈值动作</th></tr>
        </thead>
        <tbody>
          <tr v-for="rule in rules" :key="rule.规则ID" :data-testid="`ref-rule-${rule.规则ID}`">
            <td>{{ rule.规则名称 }}</td>
            <td>{{ rule.引用表 }}</td>
            <td>{{ rule.引用列 }}</td>
            <td>{{ rule.引用字典 || '—' }}</td>
            <td>{{ rule.阈值动作 }}</td>
          </tr>
          <tr v-if="!rules.length"><td colspan="5" class="empty-state">暂无引用完整性规则</td></tr>
        </tbody>
      </table>
    </article>

    <div class="ref-grid">
      <article class="ref-card">
        <h4>引用字典版本</h4>
        <table class="data-table">
          <thead>
            <tr><th>版本号</th><th>执行日期</th><th>冻结时间</th><th>条目</th><th>状态</th></tr>
          </thead>
          <tbody>
              <tr v-for="version in versions" :key="version.id"
                :data-testid="`ref-version-${version.引用版本号}`">
                <td>{{ version.引用版本号 }}</td>
                <td>{{ version.字典执行日期 }}</td>
                <td>{{ version.字典冻结时间 }}</td>
                <td>{{ version.字典条目数 }}</td>
                <td>{{ version.版本状态 }}</td>
              </tr>
              <tr v-if="!versions.length"><td colspan="5" class="empty-state">暂无引用版本</td></tr>
          </tbody>
        </table>
      </article>

      <article class="ref-card">
        <h4>质量执行汇总（按批解释分子/分母）</h4>
        <table class="data-table">
          <thead>
            <tr>
              <th>批次</th><th>引用版本</th><th>字典执行日期</th>
              <th>分子/分母</th><th>坏行率</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="batch in batchRows"
              :key="batch.批次标识"
              :data-testid="`ref-summary-${batch.批次标识}`"
              :class="{ selected: selectedBatchId === batch.id }"
            >
              <td>
                <button class="link" type="button" @click="loadEvidence(batch.id)">
                  {{ batch.批次标识 }}
                </button>
              </td>
              <td>{{ batch.引用版本号 }}</td>
              <td>{{ batch.字典执行日期 }}</td>
              <td>{{ batch.分子 }} / {{ batch.分母 }}</td>
              <td>{{ batch.坏行率 }}</td>
            </tr>
            <tr v-if="!batchRows.length"><td colspan="5" class="empty-state">暂无绑定引用版本的批次</td></tr>
          </tbody>
        </table>
        <p v-if="summary.unversioned_count" class="ref-note" data-testid="unversioned-note">
          另有 {{ summary.unversioned_count }} 个校验批次未绑定引用字典版本，不参与按版本解释坏行率：
          <span v-for="batch in summary.unversioned_batches" :key="batch.id">
            {{ batch.批次标识 }}（{{ batch.状态 }}）
          </span>
        </p>
      </article>
    </div>

    <article v-if="evidence" class="ref-card" data-testid="ref-evidence">
      <h4>批次证据：{{ evidence.批次标识 }}</h4>
      <dl class="ref-facts">
        <div><dt>引用版本</dt><dd data-testid="ref-evidence-version">{{ evidence.引用版本号 }}</dd></div>
        <div><dt>引用列</dt><dd>{{ evidence.引用列 }}</dd></div>
        <div><dt>字典执行日期</dt><dd>{{ evidence.字典执行日期 }}</dd></div>
        <div><dt>字典冻结时间</dt><dd>{{ evidence.字典冻结时间 }}</dd></div>
        <div><dt>条目数</dt><dd>{{ evidence.字典条目数 }}</dd></div>
        <div><dt>坏行率</dt><dd data-testid="ref-evidence-rate">{{ evidence.坏行率 }}</dd></div>
        <div><dt>分子 / 分母</dt><dd>{{ evidence.坏行率分子 }} / {{ evidence.坏行率分母 }}</dd></div>
        <div><dt>原始批次</dt><dd>{{ evidence.原始批次标识 || '—' }}</dd></div>
      </dl>
      <p class="ref-note">{{ evidence.计算口径 }}</p>
      <p class="ref-note">{{ evidence.取值依据 }}</p>

      <h5>坏行明细（可沿证据找到实际使用的地区条目）</h5>
      <table class="data-table">
        <thead>
          <tr><th>行号</th><th>门店代码</th><th>引用列</th><th>命中</th><th>取值依据</th></tr>
        </thead>
        <tbody>
          <tr v-for="bad in evidence.坏行明细 || []" :key="bad.row_index">
            <td>{{ bad.row_index }}</td>
            <td>{{ bad.store_code }}</td>
            <td>{{ bad.引用列 }}</td>
            <td>{{ bad.matched ? '是' : '否' }}</td>
            <td class="ref-basis">{{ bad.取值依据 }}</td>
          </tr>
          <tr v-if="!(evidence.坏行明细 || []).length">
            <td colspan="5" class="empty-state">该批次没有坏行</td>
          </tr>
        </tbody>
      </table>

      <h5>字典条目快照</h5>
      <table class="data-table">
        <thead><tr><th>门店代码</th><th>地区编码</th><th>地区名称</th><th>来源</th></tr></thead>
        <tbody>
          <tr v-for="(entry, code) in evidence.字典条目快照 || {}" :key="code">
            <td>{{ code }}</td><td>{{ entry.region_code }}</td>
            <td>{{ entry.region_name }}</td><td>{{ entry.来源 }}</td>
          </tr>
        </tbody>
      </table>

      <div class="ref-actions">
        <button
          class="btn primary"
          type="button"
          data-testid="review-original"
          :disabled="busy"
          @click="reviewBatch(evidence.id)"
        >按原执行结果复查</button>
        <label class="ref-inline">
          <span>重算使用版本</span>
          <select v-model.number="recomputeVersionId" data-testid="recompute-version">
            <option v-for="version in confirmedVersions" :key="version.id" :value="version.id">
              {{ version.引用版本号 }}（{{ version.字典执行日期 }}，{{ version.字典条目数 }} 条）
            </option>
          </select>
        </label>
        <button
          class="btn"
          type="button"
          data-testid="recompute-batch"
          :disabled="busy || !recomputeVersionId"
          @click="recomputeBatch(evidence.id)"
        >用该版本重算</button>
      </div>
      <p class="ref-note">
        重算会另存一个新批次并保存所使用的引用版本，原批的样本计数与坏行明细保持归档不变。
      </p>
    </article>

    <article v-if="review" class="ref-card" data-testid="ref-review">
      <h4>只读复查：{{ review.批次标识 }}（{{ review.引用版本号 }}）</h4>
      <p class="ref-note">
        复查未改写已归档样本计数；坏行率 {{ review.坏行率 }}
        （{{ review.坏行率分子 }} / {{ review.坏行率分母 }}）。
      </p>
      <table class="data-table">
        <thead><tr><th>行号</th><th>门店代码</th><th>原批结论</th><th>复查结论</th><th>复查取值依据</th></tr></thead>
        <tbody>
          <tr v-for="row in review.坏行明细 || []" :key="row.row_index">
            <td>{{ row.row_index }}</td><td>{{ row.store_code }}</td>
            <td>{{ row.原批结论 }}</td><td>{{ row.复查结论 }}</td>
            <td class="ref-basis">{{ row.取值依据 }}</td>
          </tr>
          <tr v-for="row in review.原坏行复查通过 || []" :key="`pass-${row.row_index}`">
            <td>{{ row.row_index }}</td><td>{{ row.store_code }}</td>
            <td>{{ row.原批结论 }}</td><td>{{ row.复查结论 }}</td>
            <td class="ref-basis">{{ row.复查取值依据 }}</td>
          </tr>
          <tr v-if="!(review.坏行明细 || []).length && !(review.原坏行复查通过 || []).length">
            <td colspan="5" class="empty-state">复查后没有坏行</td>
          </tr>
        </tbody>
      </table>
    </article>

    <article class="ref-card" data-testid="ref-compare">
      <h4>原批 vs 重跑批</h4>
      <div class="ref-actions">
        <label class="ref-inline">
          <span>原批</span>
          <select v-model.number="compareOriginalId" data-testid="compare-original">
            <option v-for="batch in batchRows" :key="batch.id" :value="batch.id">
              {{ batch.批次标识 }}
            </option>
          </select>
        </label>
        <label class="ref-inline">
          <span>重算批</span>
          <select v-model.number="compareCandidateId" data-testid="compare-candidate">
            <option v-for="batch in batchRows" :key="batch.id" :value="batch.id">
              {{ batch.批次标识 }}
            </option>
          </select>
        </label>
        <button class="btn" type="button" data-testid="compare-batches" :disabled="busy" @click="compareBatches">
          对比原坏行
        </button>
      </div>
      <div v-if="comparison" class="ref-compare-result" data-testid="compare-result">
        <p>
          原批 {{ comparison.原批.引用版本号 }} 坏行率 {{ comparison.原批.坏行率 }}
          （{{ comparison.原批.坏行率分子 }} / {{ comparison.原批.坏行率分母 }}）；
          重算批 {{ comparison.重算批.引用版本号 }} 坏行率 {{ comparison.重算批.坏行率 }}
          （{{ comparison.重算批.坏行率分子 }} / {{ comparison.重算批.坏行率分母 }}）。
        </p>
        <p data-testid="compare-recovered">
          原坏行通过数：{{ comparison.原坏行通过数 }}，新增坏行数：{{ comparison.新增坏行数 }}
        </p>
        <table class="data-table">
          <thead><tr><th>行号</th><th>门店代码</th><th>复核结果</th><th>新取值依据</th><th>解析地区</th></tr></thead>
          <tbody>
            <tr v-for="row in comparison.原坏行通过明细" :key="`cmp-${row.row_index}`">
              <td>{{ row.row_index }}</td><td>{{ row.store_code }}</td>
              <td>{{ row.复核结果 }}</td><td class="ref-basis">{{ row.新取值依据 }}</td>
              <td>{{ row.新解析地区?.region_name ?? '—' }}</td>
            </tr>
            <tr v-if="!comparison.原坏行通过明细.length">
              <td colspan="5" class="empty-state">没有原坏行在新版本下通过</td>
            </tr>
          </tbody>
        </table>
      </div>
    </article>

    <article class="ref-card" data-testid="ref-supplement">
      <h4>中途补录地区条目</h4>
      <p class="ref-note">
        用旧字典不认识的门店代码跑出坏行后，可在此补上地区对应值：系统会派生新的已确认版本，
        旧版本原样保留，原批与重跑批各自可复查。
      </p>
      <form class="ref-actions" @submit.prevent="supplementEntry">
        <label class="ref-inline">
          <span>基线版本</span>
          <select v-model.number="supplement.baseVersionId" data-testid="supplement-base">
            <option v-for="version in confirmedVersions" :key="version.id" :value="version.id">
              {{ version.引用版本号 }}
            </option>
          </select>
        </label>
        <label class="ref-inline"><span>门店代码</span>
          <input v-model="supplement.storeCode" data-testid="supplement-code" placeholder="S006" required />
        </label>
        <label class="ref-inline"><span>地区编码</span>
          <input v-model="supplement.regionCode" data-testid="supplement-region-code" placeholder="R06" required />
        </label>
        <label class="ref-inline"><span>地区名称</span>
          <input v-model="supplement.regionName" data-testid="supplement-region-name" placeholder="华中-武汉" required />
        </label>
        <label class="ref-inline"><span>执行日期</span>
          <input v-model="supplement.executionDate" data-testid="supplement-date" placeholder="2026-11-21" required />
        </label>
        <button class="btn primary" type="submit" data-testid="supplement-submit" :disabled="busy">
          补录并派生版本
        </button>
      </form>
    </article>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  addRegionEntry,
  compareReferenceRuns,
  listReferenceRules,
  listReferenceVersions,
  loadReferenceEvidence,
  loadReferenceSummary,
  recomputeReferenceRun,
  reviewReferenceRun,
} from '@/api/backend-service'
import type {
  ReferenceComparison,
  ReferenceEvidence,
  ReferenceReviewResult,
  ReferenceRuleBinding,
  ReferenceSummary,
  ReferenceVersionRow,
} from '@/data/types'

const versions = ref<ReferenceVersionRow[]>([])
const rules = ref<ReferenceRuleBinding[]>([])
const summary = ref<ReferenceSummary>({ batches: [], batch_count: 0, versions: [] })
const selectedBatchId = ref<number | null>(null)
const evidence = ref<(ReferenceEvidence & { id: number }) | null>(null)
const review = ref<ReferenceReviewResult | null>(null)
const comparison = ref<ReferenceComparison | null>(null)
const panelError = ref('')
const panelMessage = ref('')
const busy = ref(false)
const recomputeVersionId = ref<number | null>(null)
const compareOriginalId = ref<number | null>(null)
const compareCandidateId = ref<number | null>(null)
const supplement = ref({
  baseVersionId: null as number | null,
  storeCode: '',
  regionCode: '',
  regionName: '',
  executionDate: '2026-11-21',
})

const batchRows = computed(() => summary.value.batches)

// 只有已确认版本可用于重算/派生；历史版本仅保留供复查。
const confirmedVersions = computed(() =>
  versions.value.filter((version) => version.版本状态 === '已确认'),
)

function reportError(error: unknown, fallback: string) {
  panelError.value = error instanceof Error ? error.message : fallback
}

async function refreshAll() {
  panelError.value = ''
  try {
    const [versionRows, summaryPayload, ruleRows] = await Promise.all([
      listReferenceVersions(),
      loadReferenceSummary(),
      listReferenceRules(),
    ])
    versions.value = versionRows
    rules.value = ruleRows
    summary.value = summaryPayload
    const confirmedIds = confirmedVersions.value.map((version) => version.id)
    if (!recomputeVersionId.value || !confirmedIds.includes(recomputeVersionId.value)) {
      recomputeVersionId.value = confirmedIds[0] ?? null
    }
    if (!supplement.value.baseVersionId || !confirmedIds.includes(supplement.value.baseVersionId)) {
      supplement.value.baseVersionId = confirmedIds[0] ?? null
    }
    if (!compareOriginalId.value && batchRows.value.length) {
      compareOriginalId.value = batchRows.value[0].id
    }
    if (!compareCandidateId.value && batchRows.value.length > 1) {
      compareCandidateId.value = batchRows.value[batchRows.value.length - 1].id
    }
  } catch (error) {
    reportError(error, '引用版本报表读取失败')
  }
}

async function loadEvidence(batchId: number) {
  panelError.value = ''
  review.value = null
  try {
    const payload = await loadReferenceEvidence(batchId)
    evidence.value = { ...payload, id: batchId }
    selectedBatchId.value = batchId
  } catch (error) {
    reportError(error, '批次字典版本证据读取失败')
  }
}

async function reviewBatch(batchId: number) {
  busy.value = true
  panelError.value = ''
  try {
    review.value = await reviewReferenceRun(batchId)
    panelMessage.value = review.value.message ?? '复查完成'
  } catch (error) {
    reportError(error, '坏行复查失败')
  } finally {
    busy.value = false
  }
}

async function recomputeBatch(batchId: number) {
  if (!recomputeVersionId.value) return
  busy.value = true
  panelError.value = ''
  try {
    const result = await recomputeReferenceRun(batchId, recomputeVersionId.value)
    panelMessage.value = result.message
    await refreshAll()
    await loadEvidence(batchId)
  } catch (error) {
    reportError(error, '按版本重算失败')
  } finally {
    busy.value = false
  }
}

async function compareBatches() {
  if (!compareOriginalId.value || !compareCandidateId.value) return
  busy.value = true
  panelError.value = ''
  try {
    comparison.value = await compareReferenceRuns(compareOriginalId.value, compareCandidateId.value)
  } catch (error) {
    reportError(error, '批次对比失败')
  } finally {
    busy.value = false
  }
}

async function supplementEntry() {
  if (!supplement.value.baseVersionId) return
  busy.value = true
  panelError.value = ''
  try {
    const result = await addRegionEntry(
      supplement.value.baseVersionId,
      {
        store_code: supplement.value.storeCode,
        region_code: supplement.value.regionCode,
        region_name: supplement.value.regionName,
      },
      supplement.value.executionDate,
    )
    panelMessage.value = result.message
    await refreshAll()
  } catch (error) {
    reportError(error, '地区条目补录失败')
  } finally {
    busy.value = false
  }
}

onMounted(refreshAll)
</script>

<style scoped>
.ref-panel { margin-top: 20px; }
.ref-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.ref-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px; }
.ref-card { background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 12px; margin-bottom: 12px; }
.ref-card h4 { margin: 0 0 8px; font-size: 14px; }
.ref-card h5 { margin: 14px 0 6px; font-size: 13px; }
.ref-facts { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 0; }
.ref-facts dt { font-size: 12px; color: var(--muted); }
.ref-facts dd { margin: 2px 0 0; font-size: 13px; }
.ref-note { font-size: 12px; color: var(--muted); margin: 6px 0; }
.ref-basis { font-size: 12px; color: #334155; max-width: 420px; }
.ref-actions { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; margin-top: 12px; }
.ref-inline { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
.ref-inline select, .ref-inline input { padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; }
.ref-message { color: #166534; font-size: 13px; }
.selected { background: #eff6ff; }
</style>
