import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import ReferenceWorkbench from './ReferenceWorkbench.vue'

const versions = [
  { id: 1, 引用版本号: 'REGION-v1', 引用字典: '地区引用字典', 引用表: 'dim.dim_region_reference',
    引用列: 'store_code', 字典执行日期: '2026-11-17', 字典冻结时间: '2026-11-18T05:00:00',
    字典条目数: '5', 版本状态: '历史', 条目快照: {} },
  { id: 2, 引用版本号: 'REGION-v2', 引用字典: '地区引用字典', 引用表: 'dim.dim_region_reference',
    引用列: 'store_code', 字典执行日期: '2026-11-19', 字典冻结时间: '2026-11-19T10:30:00',
    字典条目数: '6', 版本状态: '已确认', 条目快照: {} },
]
const summary = {
  batch_count: 2,
  versions: ['REGION-v1', 'REGION-v2'],
  batches: [
    { id: 5, 批次标识: 'VAL-STORE-20261118-001', 状态: '未通过', 引用版本ID: 1, 引用版本号: 'REGION-v1',
      引用列: 'store_code', 字典执行日期: '2026-11-17', 字典冻结时间: '2026-11-18T05:00:00',
      字典条目数: '5', 分子: '1', 分母: '8', 坏行率: '12.5%', 原始批次标识: '', 解释: '坏行率 = 1 / 8' },
    { id: 6, 批次标识: 'VAL-STORE-20261119-002', 状态: '已通过', 引用版本ID: 2, 引用版本号: 'REGION-v2',
      引用列: 'store_code', 字典执行日期: '2026-11-19', 字典冻结时间: '2026-11-19T10:30:00',
      字典条目数: '6', 分子: '0', 分母: '8', 坏行率: '0.0%', 原始批次标识: 'VAL-STORE-20261118-001',
      解释: '坏行率 = 0 / 8' },
  ],
}
const rules = [
  { ok: true, 规则ID: 7, 规则名称: '门店地区引用完整性校验', 校验类型: 'REFERENCE',
    引用完整性规则: true, 引用字典: 'region_reference', 引用表: 'dim.dim_region_reference',
    引用列: 'store_code', 校验字段: 'store_code', 阈值设定: '0.01', 校验级别: 'BLOCK',
    阈值动作: '阻断', 说明: '按引用列绑定版本' },
]
const evidence = {
  ok: true, 批次标识: 'VAL-STORE-20261118-001', 绑定了引用版本: true, 引用版本ID: 1,
  引用版本号: 'REGION-v1', 引用字典: '地区引用字典', 引用表: 'dim.dim_region_reference',
  引用列: 'store_code', 字典执行日期: '2026-11-17', 字典冻结时间: '2026-11-18T05:00:00',
  字典条目数: 5, 样本行数: 8, 匹配行数: 7, 未匹配行数: 1, 坏行率: '12.5%',
  坏行率分子: 1, 坏行率分母: 8, 计算口径: '坏行率 = 1 / 8', 取值依据: '按 REGION-v1 冻结条目匹配',
  坏行明细: [{ row_index: 3, store_code: 'S006', field: 'store_code', matched: false, reason: '引用缺失',
    引用版本ID: 1, 引用版本号: 'REGION-v1', 引用列: 'store_code', 字典执行日期: '2026-11-17',
    字典冻结时间: '2026-11-18T05:00:00', 取值依据: '行字段 store_code=S006 无对应条目', 解析地区: null }],
  字典条目快照: { S001: { region_code: 'R01', region_name: '华东-上海', 来源: '主数据同步' } },
  原始批次标识: '', 样本归档: true, 版本状态: '历史', 版本是否已确认: true,
}

function respond(payload: unknown) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(payload) } as Response)
}

describe('ReferenceWorkbench', () => {
  it('renders versions, summary, evidence, review and compare', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('reference-summary')) return respond(summary)
      if (url.includes('reference-versions')) return respond({ items: versions })
      if (url.includes('reference-rules')) return respond({ items: rules })
      if (url.includes('reference-evidence')) return respond(evidence)
      if (url.includes('/review')) {
        return respond({ ok: true, 完成: true, 批次标识: 'VAL-STORE-20261118-001',
          引用版本号: 'REGION-v1', 坏行率: '12.5%', 坏行率分子: 1, 坏行率分母: 8,
          坏行明细: [], 原坏行复查通过: [], 原坏行复查通过数: 0, message: '复查完成' })
      }
      if (url.includes('/compare')) {
        return respond({ ok: true, 原坏行通过数: 1, 新增坏行数: 0,
          原批: { 引用版本号: 'REGION-v1', 坏行率: '12.5%', 坏行率分子: '1', 坏行率分母: '8' },
          重算批: { 引用版本号: 'REGION-v2', 坏行率: '0.0%', 坏行率分子: '0', 坏行率分母: '8' },
          原坏行通过明细: [{ row_index: 3, store_code: 'S006', 复核结果: '通过',
            新取值依据: '命中 REGION-v2 条目', 新解析地区: { region_code: 'R06', region_name: '华中-武汉' } }] })
      }
      return respond({})
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(ReferenceWorkbench)
    await flushPromises()

    expect(wrapper.text()).toContain('地区引用字典版本证据')
    expect(wrapper.text()).toContain('REGION-v1')
    expect(wrapper.text()).toContain('门店地区引用完整性校验')
    expect(wrapper.get('[data-testid="ref-summary-VAL-STORE-20261118-001"]').text()).toContain('1 / 8')

    await wrapper.get('[data-testid="ref-summary-VAL-STORE-20261118-001"] button').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="ref-evidence"]').text()).toContain('S006')
    expect(wrapper.get('[data-testid="ref-evidence"]').text()).toContain('行字段 store_code=S006')

    await wrapper.get('[data-testid="review-original"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="ref-review"]').text()).toContain('复查未改写已归档样本计数')

    await wrapper.get('[data-testid="compare-batches"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="compare-recovered"]').text()).toContain('原坏行通过数：1')
    expect(wrapper.get('[data-testid="compare-result"]').text()).toContain('华中-武汉')
  })
})
