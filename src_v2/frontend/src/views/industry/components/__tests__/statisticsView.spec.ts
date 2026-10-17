import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'
import StatisticsView from '../assetViewComponent/statisticsView.vue'

// ---------------------------------------------------------------------------
// Mock 掉 echarts 与主题工具，避免 jsdom 下的 canvas / 主题监听
// ---------------------------------------------------------------------------
vi.mock('echarts', () => ({
    init: vi.fn(() => ({
        setOption: vi.fn(),
        resize: vi.fn(),
        dispose: vi.fn(),
    })),
}))

vi.mock('@/utils/echartsTheme', () => ({
    getChartThemeColors: () => ({
        text: '#303133',
        textSecondary: '#909399',
        surface: '#ffffff',
        border: '#e4e7ed',
    }),
    themedTooltip: () => ({}),
    onThemeTokenChange: () => () => { },
}))

// ---------------------------------------------------------------------------
// 测试数据
// ---------------------------------------------------------------------------
interface RawAsset {
    type_id: number
    type_name: string
    type_name_zh: string
    quantity: number
    price: number
    class_type: string
}

interface RawContainer {
    container_id: number
    name: string
    assets: Record<number, RawAsset>
}

const makeAsset = (type_id: number, quantity: number, price: number, class_type: string): RawAsset => ({
    type_id,
    type_name: `Type${type_id}`,
    type_name_zh: `物品${type_id}`,
    quantity,
    price,
    class_type,
})

// 机库A（同名容器合并后）：101 = 30，102 = 60，103 = 10，合计 100
// 机库B：102 = 60，104 = 4，合计 64
// 分类「矿物」：101 = 30，103 = 10，合计 40
// 分类「舰船」：102 = 120，104 = 4，合计 124
const assetViewFixture: Record<number, RawContainer> = {
    1: {
        container_id: 1,
        name: '机库A',
        assets: {
            101: makeAsset(101, 1, 10, '矿物'),
            102: makeAsset(102, 2, 30, '舰船'),
            103: makeAsset(103, 2, 5, '矿物'),
        },
    },
    2: {
        container_id: 2,
        name: '机库A',
        assets: {
            101: makeAsset(101, 2, 10, '矿物'),
        },
    },
    3: {
        container_id: 3,
        name: '机库B',
        assets: {
            102: makeAsset(102, 2, 30, '舰船'),
            104: makeAsset(104, 4, 1, '舰船'),
        },
    },
}

// ---------------------------------------------------------------------------
// Element Plus stub
// ---------------------------------------------------------------------------
const globalStubs = {
    'el-card': {
        template: '<div class="el-card-stub"><slot name="header" /><slot /></div>',
    },
    'el-button': {
        template: '<button class="el-button-stub" @click="$emit(\'click\', $event)"><slot /></button>',
        emits: ['click'],
    },
    'el-dialog': {
        template: '<div v-if="modelValue" class="el-dialog-stub"><slot /></div>',
        props: ['modelValue'],
        emits: ['update:modelValue'],
    },
    'el-avatar': {
        template: '<div class="el-avatar-stub"><slot /></div>',
    },
    'el-tag': {
        template: '<span class="el-tag-stub"><slot /></span>',
    },
    'el-statistic': {
        template: '<div class="el-statistic-stub"></div>',
    },
    'el-empty': {
        template: '<div class="el-empty-stub"></div>',
    },
}

const createWrapper = (): VueWrapper => {
    return mount(StatisticsView, {
        props: {
            loading: false,
            assetView: assetViewFixture,
            sid: 'test-sid',
            view_type: 'statistics',
            config: {},
            lastUpdateTime: Date.now(),
        },
        global: {
            stubs: globalStubs,
            directives: { loading: {} },
        },
        attachTo: document.body,
    })
}

// 打开指定的详情弹窗
const openDetailDialog = async (wrapper: VueWrapper, label: string) => {
    const button = wrapper.findAll('button').find(item => item.text().includes(label))
    expect(button, `未找到按钮: ${label}`).toBeTruthy()
    await button?.trigger('click')
    await nextTick()
}

// 展开第一个外层卡片
const expandFirstCard = async (wrapper: VueWrapper) => {
    const buttons = wrapper.findAll('.expand-button')
    expect(buttons.length).toBeGreaterThan(0)
    await buttons[0].trigger('click')
    await nextTick()
}

// 展开的资产卡片中的物品名称顺序
const getExpandedAssetNames = (wrapper: VueWrapper): string[] => {
    return wrapper.findAll('.asset-name-en').map(item => item.text())
}

// 展开的资产卡片中背景进度的宽度（百分比数值）
const getPercentFillWidths = (wrapper: VueWrapper): number[] => {
    return wrapper
        .findAll('.asset-percent-fill')
        .map(item => parseFloat((item.element as HTMLElement).style.width))
}

describe('statisticsView — 详情弹窗展开卡片排序与占比背景进度', () => {
    let wrapper: VueWrapper | null = null

    beforeEach(() => {
        vi.stubGlobal(
            'ResizeObserver',
            class {
                observe() { }
                unobserve() { }
                disconnect() { }
            },
        )
    })

    afterEach(() => {
        wrapper?.unmount()
        wrapper = null
        vi.unstubAllGlobals()
    })

    it('容器详情：展开的卡片按占比从大到小排列', async () => {
        wrapper = createWrapper()
        await nextTick()

        await openDetailDialog(wrapper, '容器详情')
        await expandFirstCard(wrapper)

        // 机库A 合计 100：102 占 60%，101 占 30%，103 占 10%
        expect(getExpandedAssetNames(wrapper)).toEqual(['Type102', 'Type101', 'Type103'])
    })

    it('容器详情：卡片背景进度按占比填充，且同名容器的同种资产已合并', async () => {
        wrapper = createWrapper()
        await nextTick()

        await openDetailDialog(wrapper, '容器详情')
        await expandFirstCard(wrapper)

        expect(getPercentFillWidths(wrapper)).toEqual([60, 30, 10])

        // 同名容器（机库A）中的 type 101 合并为 3 个，仅展示 3 张卡片
        const innerCards = wrapper.findAll('.inner-card')
        expect(innerCards.length).toBe(3)
        const type101Card = innerCards.find(card => card.text().includes('Type101'))
        expect(type101Card?.text()).toContain('3.00')
    })

    it('分类详情：展开的卡片按占比从大到小排列并按占比填充', async () => {
        wrapper = createWrapper()
        await nextTick()

        await openDetailDialog(wrapper, '分类详情')
        await expandFirstCard(wrapper)

        // 舰船 合计 124：102 占 96.77%，104 占 3.23%
        expect(getExpandedAssetNames(wrapper)).toEqual(['Type102', 'Type104'])

        const widths = getPercentFillWidths(wrapper)
        expect(widths.length).toBe(2)
        expect(widths[0]).toBeCloseTo(96.77, 1)
        expect(widths[1]).toBeCloseTo(3.23, 1)
    })
})
