/**
 * Tax display tests for costView.vue.
 *
 * These tests verify that tax_items are rendered in the category summary
 * table and included in total cost calculations.
 *
 * Implemented in Task 12/13: tax handling in categoryCostSummary and totalCostSum.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import ElementPlus from 'element-plus'

// ── Polyfill ResizeObserver for jsdom (required by Element Plus) ──
if (typeof ResizeObserver === 'undefined') {
  global.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as any
}

// ── Mock echarts to avoid ECharts initialization issues in jsdom ──
vi.mock('echarts', () => ({
  init: vi.fn(() => ({
    setOption: vi.fn(),
    dispose: vi.fn(),
    resize: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
  })),
  registerTheme: vi.fn(),
  registerMap: vi.fn(),
  connect: vi.fn(),
  disconnect: vi.fn(),
  default: {
    init: vi.fn(() => ({
      setOption: vi.fn(),
      dispose: vi.fn(),
      resize: vi.fn(),
      on: vi.fn(),
      off: vi.fn(),
    })),
  },
}))

// ── Mock auth store (provide vip_omega so price fetching runs) ──
vi.mock('@/stores/auth', () => ({
  useAuthStore: vi.fn(() => ({
    user: { roles: ['vip_omega'] },
    isAuthenticated: true,
    token: 'mock-token',
  })),
}))

// ── Mock http client ──
vi.mock('@/http', () => ({
  http: {
    get: vi.fn().mockResolvedValue({
      json: vi.fn().mockResolvedValue({ status: 200, data: {} }),
    }),
    post: vi.fn(),
  },
}))

// ── Mock echarts theme utilities ──
vi.mock('@/utils/echartsTheme', () => ({
  getChartThemeColors: vi.fn(() => ({
    text: '#303133',
    textSecondary: '#909399',
    border: '#dcdfe6',
    surface: '#ffffff',
    surfaceSoft: '#f5f7fa',
    primary: '#409eff',
    success: '#67c23a',
    warning: '#e6a23c',
    danger: '#f56c6c',
  })),
  themedTooltip: vi.fn(() => ({})),
  onThemeTokenChange: vi.fn(() => vi.fn()),
}))

// Dynamic import after mocks are set
const { default: CostView } = await import('../costView.vue')

// ── Helper: build mock data ──
interface MockTaxItem {
  name: string
  rate: number
  amount: number
}

function buildMockProduct(overrides?: {
  tax_items?: MockTaxItem[]
  extraChildren?: boolean
}) {
  const children = [
    {
      index_id: 1,
      quantity: 100,
      jita_buy_price: 1000,
      type_id: 123,
      type_name: '三钛合金',
      material_type_node: '矿物',
    },
  ]
  if (overrides?.extraChildren) {
    children.push({
      index_id: 2,
      quantity: 20,
      jita_buy_price: 500,
      type_id: 456,
      type_name: '类晶体胶矿',
      material_type_node: '矿物',
    })
  }
  return {
    children,
    eiv_cost: 50000,
    index_id: 1,
    type_id: 789,
    type_name: '测试产品',
    product_num: 10,
    ...(overrides?.tax_items ? { tax_items: overrides.tax_items } : {}),
  }
}

describe('costView — TAX DISPLAY', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  // ── Test 1: Single tax row ──
  it('should include tax row in categoryCostSummary when tax_items are provided', async () => {
    const mockData = [
      buildMockProduct({
        tax_items: [{ name: '销售税', rate: 0.02, amount: 5000 }],
      }),
    ]

    const wrapper = mount(CostView, {
      global: { plugins: [ElementPlus] },
      props: { PlanCalculateEIVCostTableView: mockData },
    })

    // Wait for Vue reactivity to settle
    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()

    // ASSERT: The rendered page should contain "销售税" in the category summary table
    expect(wrapper.text()).toContain('销售税')
  })

  // ── Test 2: Multiple tax rows ──
  it('should render multiple tax items as separate rows', async () => {
    const mockData = [
      buildMockProduct({
        tax_items: [
          { name: '销售税', rate: 0.02, amount: 5000 },
          { name: '中介税', rate: 0.01, amount: 2500 },
        ],
      }),
    ]

    const wrapper = mount(CostView, {
      global: { plugins: [ElementPlus] },
      props: { PlanCalculateEIVCostTableView: mockData },
    })

    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()

    const text = wrapper.text()
    const foundTaxes = ['销售税', '中介税'].filter((tax) => text.includes(tax))

    // ASSERT: Both tax names should appear as separate category rows
    expect(foundTaxes.length).toBe(2)
  })

  // ── Test 3: Total cost includes tax ──
  it('should include tax amounts in total cost when tax_items exist', async () => {
    const mockData = [
      buildMockProduct({
        tax_items: [{ name: '销售税', rate: 0.02, amount: 5000 }],
      }),
    ]

    // Expected values:
    //   material cost = 100 × 1000 = 100,000
    //   eiv_cost      = 50,000
    //   tax           =  5,000
    //   total (with tax) = 155,000  → formatted = "155,000.00"
    //
    // totalCostSum includes taxTotal from all products' tax_items.

    const wrapper = mount(CostView, {
      global: { plugins: [ElementPlus] },
      props: { PlanCalculateEIVCostTableView: mockData },
    })

    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()

    // ASSERT: The grand total should include the tax amount
    expect(wrapper.text()).toContain('155,000.00')
  })

  // ── Test 4: Tax row DOM elements with formatted ISK ──
  it('should render tax row DOM elements with formatted ISK amounts', async () => {
    const mockData = [
      buildMockProduct({
        tax_items: [{ name: '矿物税', rate: 0.03, amount: 3000 }],
      }),
    ]

    const wrapper = mount(CostView, {
      global: { plugins: [ElementPlus] },
      props: { PlanCalculateEIVCostTableView: mockData },
    })

    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()

    const text = wrapper.text()

    // ASSERT: Tax category name appears as a row in the category summary table
    expect(text).toContain('矿物税')

    // ASSERT: Tax amount rendered in formatted ISK (千分位 + 2 decimal places)
    expect(text).toContain('3,000.00')
  })

  // ── Test 5: Full rendering pipeline — materials + EIV + taxes ──
  it('should render all categories including materials, EIV, and taxes', async () => {
    const mockData = [
      buildMockProduct({
        tax_items: [
          { name: '销售税', rate: 0.02, amount: 5000 },
          { name: '矿物税', rate: 0.03, amount: 3000 },
        ],
        extraChildren: true,
      }),
    ]

    const wrapper = mount(CostView, {
      global: { plugins: [ElementPlus] },
      props: { PlanCalculateEIVCostTableView: mockData },
    })

    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()

    const text = wrapper.text()

    // ASSERT: Material category from children appears
    // (both children have material_type_node: '矿物' → grouped into one row)
    expect(text).toContain('矿物')

    // ASSERT: EIV cost category appears
    expect(text).toContain('EIV成本')

    // ASSERT: Both tax categories appear
    expect(text).toContain('销售税')
    expect(text).toContain('矿物税')

    // ASSERT: All category amounts in formatted ISK
    // 矿物: 100×1000 + 20×500 = 110,000.00
    expect(text).toContain('110,000.00')
    // EIV成本: 50,000.00
    expect(text).toContain('50,000.00')
    // 销售税: 5,000.00
    expect(text).toContain('5,000.00')
    // 矿物税: 3,000.00
    expect(text).toContain('3,000.00')
  })
})

/**
 * Blueprint cost display tests for costView.vue.
 *
 * These tests verify that blueprint_cost is rendered in:
 * - Product table "蓝图成本" column header and cell data
 * - Category summary table "蓝图成本" row when totalBlueprintCost > 0
 * - Total cost calculation (totalCostSum includes blueprintTotal)
 *
 * Implemented in Task 7/8: categoryCostSummary + productCostSummary extended.
 */
describe('costView — BLUEPRINT COST', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  // ── Helper: build a product with blueprint_cost ──
  function buildBpProduct(blueprint_cost: number, overrides?: {
    extraChildren?: boolean
    tax_items?: Array<{ name: string; rate: number; amount: number }>
  }) {
    const children = [
      { index_id: 1, quantity: 100, jita_buy_price: 1000, type_id: 123, type_name: '三钛合金', material_type_node: '矿物' },
    ]
    if (overrides?.extraChildren) {
      children.push({
        index_id: 2, quantity: 20, jita_buy_price: 500, type_id: 456, type_name: '类晶体胶矿', material_type_node: '矿物',
      })
    }
    return {
      children,
      eiv_cost: 50000,
      index_id: 1,
      type_id: 789,
      type_name: '测试产品',
      product_num: 10,
      blueprint_cost,
      ...(overrides?.tax_items ? { tax_items: overrides.tax_items } : {}),
    }
  }

  // ── Test 1: Column header + data renders when blueprint_cost > 0 ──
  it('should render "蓝图成本" column header and data when product has blueprint_cost > 0', async () => {
    const mockData = [buildBpProduct(10000)]

    const wrapper = mount(CostView, {
      global: { plugins: [ElementPlus] },
      props: { PlanCalculateEIVCostTableView: mockData },
    })

    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()

    const text = wrapper.text()

    // ASSERT: "蓝图成本" column header appears in the products table
    expect(text).toContain('蓝图成本')

    // ASSERT: Formatted blueprint cost value appears (10,000.00)
    expect(text).toContain('10,000.00')
  })

  // ── Test 2: blueprint_cost = 0 renders as "0.00" ──
  it('should render blueprint_cost = 0.00 correctly when data present with 0 value', async () => {
    const mockData = [buildBpProduct(0)]

    const wrapper = mount(CostView, {
      global: { plugins: [ElementPlus] },
      props: { PlanCalculateEIVCostTableView: mockData },
    })

    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()

    const text = wrapper.text()

    // ASSERT: "蓝图成本" column header still appears
    expect(text).toContain('蓝图成本')

    // ASSERT: blueprint_cost = 0 renders as "0.00"
    expect(text).toContain('0.00')

    // ASSERT: Total cost does NOT include blueprint (material 100,000 + eiv 50,000 = 150,000.00)
    expect(text).toContain('150,000.00')
  })

  // ── Test 3: "蓝图成本" category row + total includes blueprint_cost ──
  it('should include "蓝图成本" category in category table when products have blueprint_cost', async () => {
    const mockData = [buildBpProduct(10000)]

    const wrapper = mount(CostView, {
      global: { plugins: [ElementPlus] },
      props: { PlanCalculateEIVCostTableView: mockData },
    })

    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()

    const text = wrapper.text()

    // ASSERT: "蓝图成本" appears (column header + category row)
    expect(text).toContain('蓝图成本')

    // ASSERT: Grand total includes blueprint cost
    // material 100,000 + eiv 50,000 + blueprint 10,000 = 160,000.00
    expect(text).toContain('160,000.00')
  })
})
