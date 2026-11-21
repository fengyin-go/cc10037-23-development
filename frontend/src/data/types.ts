/** 纯前端数据层的公共类型：与全栈版后端返回的结构保持一致，换回后端时页面不用改。 */

export type EntryRow = {
  id: number
  status: string
  pending: boolean
  abnormal: boolean
  [field: string]: string | number | boolean
}

export type ModuleMeta = {
  key: string
  name: string
  entity: string
  desc: string
  fields: string[]
  statuses: string[]
  actions: string[]
  actionTargets: Record<string, string>
  metrics: string[]
}

export type PageResult = {
  items: EntryRow[]
  total: number
  page: number
  size: number
}

export type ActionResult = {
  ok: boolean
  message: string
}

export type ReferenceBadRow = {
  row_index: number
  store_code: string | number | null
  field: string
  matched: boolean
  reason: string
  引用版本ID: number
  引用版本号: string
  引用列: string
  字典执行日期: string
  字典冻结时间: string
  取值依据: string
  解析地区: Record<string, string> | null
}

export type ReferenceEvidence = {
  ok: boolean
  批次标识: string
  引用了版本?: boolean
  绑定了引用版本: boolean
  引用版本ID?: number
  引用版本号?: string
  引用字典?: string
  引用表?: string
  引用列?: string
  字典执行日期?: string
  字典冻结时间?: string
  字典条目数?: number
  样本行数?: number
  匹配行数?: number
  未匹配行数?: number
  坏行率?: string
  坏行率分子?: number
  坏行率分母?: number
  取值依据?: string
  计算口径?: string
  坏行明细?: ReferenceBadRow[]
  字典条目快照?: Record<string, Record<string, string>>
  原始批次标识?: string
  样本归档?: boolean
  版本状态?: string
  版本是否已确认?: boolean
  按版本重算口径?: { 分子: number; 分母: number }
  message?: string
}

export type ReferenceReviewResult = {
  ok: boolean
  完成: boolean
  message?: string
  批次标识?: string
  引用版本号?: string
  引用列?: string
  字典执行日期?: string
  字典冻结时间?: string
  字典条目数?: number
  样本行数?: number
  匹配行数?: number
  未匹配行数?: number
  坏行率?: string
  坏行率分子?: number
  坏行率分母?: number
  坏行明细?: (ReferenceBadRow & { 原批结论?: string; 复查结论?: string })[]
  原坏行复查通过?: Record<string, unknown>[]
  原坏行复查通过数?: number
  实际使用字典?: Record<string, Record<string, string>>
}

export type ReferenceVersionRow = {
  id: number
  引用版本号: string
  引用字典: string
  引用表: string
  引用列: string
  字典执行日期: string
  字典冻结时间: string
  字典条目数: string
  版本状态: string
  条目快照: Record<string, Record<string, string>>
}

export type ReferenceRuleBinding = {
  ok: boolean
  规则ID: number
  规则名称: string
  校验类型: string
  引用完整性规则: boolean
  引用字典: string
  引用表: string
  引用列: string
  校验字段: string
  阈值设定: string
  校验级别: string
  阈值动作: string
  说明: string
}

export type ReferenceBatchSide = {
  id: number
  批次标识: string
  引用版本ID: number
  引用版本号: string
  字典执行日期: string
  字典冻结时间: string
  字典条目数: number
  坏行率: string
  坏行率分子: string
  坏行率分母: string
  坏行明细: Record<string, unknown>[]
}

export type ReferenceComparison = {
  ok: boolean
  样本行数: number
  原坏行数: number
  新坏行数: number
  原坏行通过数: number
  新增坏行数: number
  原引用版本号: string
  新引用版本号: string
  原坏行通过明细: {
    row_index: number
    store_code: string
    复核结果: string
    新引用版本号: string
    新字典冻结时间: string
    新取值依据: string
    新解析地区: { region_code: string; region_name: string; 来源: string } | null
  }[]
  新增坏行明细: Record<string, unknown>[]
  原批: ReferenceBatchSide
  重算批: ReferenceBatchSide
}

export type ReferenceSummary = {
  batches: {
    id: number
    批次标识: string
    状态: string
    引用版本ID: number
    引用版本号: string
    引用列: string
    字典执行日期: string
    字典冻结时间: string
    字典条目数: string
    分子: string
    分母: string
    坏行率: string
    原始批次标识: string
    解释: string
  }[]
  batch_count: number
  versions: string[]
  unversioned_batches?: {
    id: number
    批次标识: string
    状态: string
    总行数: number | null
    通过行数: number | null
    失败行数: number | null
    说明: string
  }[]
  unversioned_count?: number
}

export type OverviewResult = {
  cards: { label: string; value: number }[]
  modules: { name: string; created: number; pending: number; abnormal: number }[]
}
