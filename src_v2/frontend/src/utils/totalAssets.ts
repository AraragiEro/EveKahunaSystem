// 统一的「总资产估值」口径：钱包 + 订单 + 运行中 + 标记资产 + 非标记资产

export type NumericValue = number | Record<string, number> | null | undefined

export interface TotalAssetSource {
  walletValue?: NumericValue
  orderValue?: NumericValue
  runningProcessValue?: number
  markedAssetValue?: number
  unmarkedAssetValue?: number
}

/** 把「数字或按角色拆分的对象」归一成数字 */
export function getNumericValue(value: NumericValue): number {
  if (value === null || value === undefined) return 0
  if (typeof value === 'number') return Number.isNaN(value) ? 0 : value
  if (typeof value === 'object') {
    return Object.values(value).reduce(
      (sum: number, item: number) => sum + (typeof item === 'number' ? item : 0),
      0,
    )
  }
  return 0
}

/** 唯一的总资产公式，任何页面都只能调这个，不要再各自加 */
export function calculateTotalAssets(
  source: TotalAssetSource | null | undefined,
): number {
  if (!source) return 0
  return (
    getNumericValue(source.walletValue) +
    getNumericValue(source.orderValue) +
    (source.runningProcessValue ?? 0) +
    (source.markedAssetValue ?? 0) +
    (source.unmarkedAssetValue ?? 0)
  )
}
