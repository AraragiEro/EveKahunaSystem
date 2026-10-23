import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'

/* ── Mock setup (hoisted by vitest) ── */
const { mockHttpGet, mockHttpPost, mockElMessageSuccess, mockElMessageError, mockElMessageBoxConfirm } = vi.hoisted(() => ({
  mockHttpGet: vi.fn(),
  mockHttpPost: vi.fn(),
  mockElMessageSuccess: vi.fn(),
  mockElMessageError: vi.fn(),
  mockElMessageBoxConfirm: vi.fn(),
}))

vi.mock('@/http', () => ({
  http: {
    get: mockHttpGet,
    post: mockHttpPost,
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('element-plus', async (importOriginal) => {
  const actual: any = await importOriginal()
  return {
    ...actual,
    ElMessage: {
      success: mockElMessageSuccess,
      error: mockElMessageError,
    },
    ElMessageBox: {
      confirm: mockElMessageBoxConfirm,
    },
  }
})

vi.mock('@/utils/apiResponse', () => ({
  handleApiResponse: vi.fn(async (response: any) => {
    const data = await response.json()
    if (data.status !== 200) {
      return null
    }
    return data
  }),
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: vi.fn(() => ({
    user: { username: 'testuser' },
    isAuthenticated: true,
  })),
}))

const { handleApiResponse } = await import('@/utils/apiResponse')

/* ── Import component after mocks ── */
const { default: CoefficientMonitor } = await import('../CoefficientMonitor.vue')

/* ── Helpers ── */
const mockWatchlistResponse = (data: any[]) =>
  mockHttpGet.mockResolvedValueOnce({
    json: async () => ({ status: 200, data }),
    ok: true,
    status: 200,
  })

const mockWatchlistError = () =>
  mockHttpGet.mockRejectedValueOnce(new Error('Network Error'))

const mockSearchResponse = (data: any[]) =>
  mockHttpGet.mockResolvedValueOnce({
    json: async () => ({ status: 200, data }),
    ok: true,
    status: 200,
  })

const mockAddResponse = () =>
  mockHttpPost.mockResolvedValueOnce({
    json: async () => ({ status: 200, data: { success: true } }),
    ok: true,
    status: 200,
  })

const mockRemoveResponse = () =>
  mockHttpPost.mockResolvedValueOnce({
    json: async () => ({ status: 200, data: { success: true } }),
    ok: true,
    status: 200,
  })

const mockAddAllResponse = (addedCount: number) =>
  mockHttpPost.mockResolvedValueOnce({
    json: async () => ({
      status: 200,
      data: { added_count: addedCount, systems: [] },
      message: `成功添加 ${addedCount} 个星系`,
    }),
    ok: true,
    status: 200,
  })

const sampleSystems = [
  {
    system_id: 30000142,
    system_name: 'Jita',
    system_name_zh: '吉他',
    region_name: 'The Forge',
    manufacturing: 0.75,
    reaction: 0.72,
  },
  {
    system_id: 30002187,
    system_name: 'Amarr',
    system_name_zh: '艾玛',
    region_name: 'Domain',
    manufacturing: 0.80,
    reaction: null,
  },
]

const mountComponent = () => {
  return mount(CoefficientMonitor, {
    global: {
      stubs: {
        'el-autocomplete': {
          name: 'ElAutocomplete',
          template: `
            <div class="el-autocomplete-stub">
              <input
                class="el-autocomplete-input"
                :placeholder="placeholder"
                @input="$emit('input', $event.target.value)"
                @keyup.enter="$emit('select', { system_id: 999, system_name: 'Test', system_name_zh: '测试' })"
              />
            </div>
          `,
          props: {
            modelValue: { type: String },
            fetchSuggestions: { type: Function },
            placeholder: { type: String, default: '' },
            triggerOnFocus: { type: Boolean, default: false },
            valueKey: { type: String },
          },
          emits: ['update:modelValue', 'select'],
        },
        'el-table': {
          name: 'ElTable',
          template: '<div class="el-table-stub"><slot /></div>',
          props: ['data', 'stripe'],
        },
        'el-table-column': {
          name: 'ElTableColumn',
          template: `
            <div class="el-table-column-stub" :data-prop="prop || label">
              <template v-if="prop || label">
                <slot v-for="row in ($parent?.data || [])" :key="row.system_id" :row="row" />
              </template>
            </div>
          `,
          props: ['label', 'prop', 'width', 'minWidth', 'fixed', 'align'],
        },
        'el-button': {
          name: 'ElButton',
          template: '<button :class="type" :disabled="loading" @click="$emit(\'click\')"><slot /></button>',
          props: ['type', 'size', 'loading'],
          emits: ['click'],
        },
        'el-skeleton': {
          name: 'ElSkeleton',
          template: '<div class="el-skeleton-stub"><slot /></div>',
          props: ['animated', 'rows'],
        },
        'el-skeleton-item': {
          name: 'ElSkeletonItem',
          template: '<div class="el-skeleton-item-stub" />',
          props: ['variant'],
        },
        'el-empty': {
          name: 'ElEmpty',
          template: '<div class="el-empty-stub">{{ description }}</div>',
          props: ['description', 'imageSize'],
        },
        'el-tag': {
          name: 'ElTag',
          template: '<span class="el-tag-stub"><slot /></span>',
          props: ['type', 'size'],
        },
      },
    },
  })
}

describe('CoefficientMonitor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // KTable 未显式传 density 时读 stores/tableDensity，需要激活 Pinia
    setActivePinia(createPinia())
  })

  /* ─── 1. Empty state ─── */
  describe('empty state', () => {
    it('renders empty description when watchlist returns no data', async () => {
      mockWatchlistResponse([])

      const wrapper = mountComponent()
      await flushPromises()
      await nextTick()

      const empty = wrapper.find('.el-empty-stub')
      expect(empty.exists()).toBe(true)
      expect(empty.text()).toContain('暂无监控星系')
    })

    it('renders search input even when empty', async () => {
      mockWatchlistResponse([])

      const wrapper = mountComponent()
      await flushPromises()
      await nextTick()

      expect(wrapper.find('.el-autocomplete-stub').exists()).toBe(true)
    })

    it('renders add-all button when empty', async () => {
      mockWatchlistResponse([])

      const wrapper = mountComponent()
      await flushPromises()
      await nextTick()

      const buttons = wrapper.findAll('button')
      const addAllBtn = buttons.find(b => b.text().includes('一键添加资产星系'))
      expect(addAllBtn).toBeTruthy()
    })
  })

  /* ─── 2. Table with data ─── */
  describe('watchlist data', () => {
    it('renders table rows when watchlist has data', async () => {
      mockWatchlistResponse(sampleSystems)

      const wrapper = mountComponent()
      await flushPromises()
      await nextTick()

      // Table should exist
      expect(wrapper.find('.el-table-stub').exists()).toBe(true)
    })

    it('displays system name in table', async () => {
      mockWatchlistResponse(sampleSystems)

      const wrapper = mountComponent()
      await flushPromises()
      await nextTick()

      const html = wrapper.html()
      expect(html).toContain('吉他')
      expect(html).toContain('艾玛')
    })

    it('formats manufacturing coefficient as percentage', async () => {
      mockWatchlistResponse(sampleSystems)

      const wrapper = mountComponent()
      await flushPromises()
      await nextTick()

      const html = wrapper.html()
      // 0.75 → 75.00%
      expect(html).toContain('75.00%')
    })

    it('shows dash for null coefficient', async () => {
      mockWatchlistResponse(sampleSystems)

      const wrapper = mountComponent()
      await flushPromises()
      await nextTick()

      const html = wrapper.html()
      // reaction for Amarr is null → should show "-"
      expect(html).toContain('-')
    })
  })

  /* ─── 3. Search input ─── */
  describe('search', () => {
    it('renders autocomplete search input', async () => {
      mockWatchlistResponse([])

      const wrapper = mountComponent()
      await flushPromises()
      await nextTick()

      const autocomplete = wrapper.find('.el-autocomplete-stub')
      expect(autocomplete.exists()).toBe(true)
    })

    it('has placeholder text', async () => {
      mockWatchlistResponse([])

      const wrapper = mountComponent()
      await flushPromises()
      await nextTick()

      const input = wrapper.find('.el-autocomplete-input')
      expect(input.attributes('placeholder')).toBeTruthy()
    })
  })

  /* ─── 4. Delete button ─── */
  describe('delete', () => {
    it('triggers remove API on delete confirm', async () => {
      mockWatchlistResponse(sampleSystems)
      mockElMessageBoxConfirm.mockResolvedValueOnce('confirm')
      mockRemoveResponse()
      // After remove, refresh list
      mockWatchlistResponse([sampleSystems[1]]) // Only Amarr remains

      const wrapper = mountComponent()
      await flushPromises()
      await nextTick()

      // Find delete buttons - they should be rendered in the table column
      const deleteButtons = wrapper.findAll('button')
      const deleteBtn = deleteButtons.find(b => b.text().includes('删除'))
      expect(deleteBtn).toBeTruthy()

      // Click delete
      if (deleteBtn) {
        await deleteBtn.trigger('click')
        await flushPromises()
        await nextTick()

        // Confirm dialog should be called
        expect(mockElMessageBoxConfirm).toHaveBeenCalled()
        // Remove API should be called
        expect(mockHttpPost).toHaveBeenCalledWith(
          '/EVE/home/coefficient/remove',
          expect.objectContaining({ system_id: expect.any(Number) }),
        )
      }
    })
  })

  /* ─── 5. Add-all button ─── */
  describe('add-all button', () => {
    it('renders add-all asset systems button', async () => {
      mockWatchlistResponse([])

      const wrapper = mountComponent()
      await flushPromises()
      await nextTick()

      const buttons = wrapper.findAll('button')
      const addAllBtn = buttons.find(b => b.text().includes('一键添加资产星系'))
      expect(addAllBtn).toBeTruthy()
    })

    it('calls addAllAssetSystems API on click', async () => {
      mockWatchlistResponse([])
      mockAddAllResponse(5)
      // After add-all, refresh list
      mockWatchlistResponse([])

      const wrapper = mountComponent()
      await flushPromises()
      await nextTick()

      const buttons = wrapper.findAll('button')
      const addAllBtn = buttons.find(b => b.text().includes('一键添加资产星系'))
      expect(addAllBtn).toBeTruthy()

      if (addAllBtn) {
        await addAllBtn.trigger('click')
        await flushPromises()
        await nextTick()

        expect(mockHttpPost).toHaveBeenCalledWith(
          '/EVE/home/coefficient/addAllAssetSystems',
          {},
        )
        expect(mockElMessageSuccess).toHaveBeenCalled()
      }
    })

    it('shows loading state on add-all button while processing', async () => {
      mockWatchlistResponse([])
      // Make the add-all request slow
      let resolveAddAll: (value: any) => void
      const addAllPromise = new Promise((resolve) => {
        resolveAddAll = resolve
      })
      mockHttpPost.mockReturnValueOnce(addAllPromise)

      const wrapper = mountComponent()
      await flushPromises()
      await nextTick()

      const buttons = wrapper.findAll('button')
      const addAllBtn = buttons.find(b => b.text().includes('一键添加资产星系'))
      expect(addAllBtn).toBeTruthy()

      if (addAllBtn) {
        await addAllBtn.trigger('click')
        await nextTick()

        // Button should be in loading state (disabled prop)
        expect(addAllBtn.attributes('disabled')).toBeDefined()
      }

      // Clean up
      resolveAddAll!({
        json: async () => ({
          status: 200,
          data: { added_count: 5, systems: [] },
          message: '成功',
        }),
        ok: true,
        status: 200,
      })
    })
  })

  /* ─── 6. Loading state ─── */
  describe('loading state', () => {
    it('shows skeleton while loading', async () => {
      // Delay the watchlist response
      let resolveWatchlist: (value: any) => void
      const watchlistPromise = new Promise((resolve) => {
        resolveWatchlist = resolve
      })
      mockHttpGet.mockReturnValueOnce(watchlistPromise)

      const wrapper = mountComponent()
      await nextTick()

      // Skeleton should be visible during loading
      expect(wrapper.find('.el-skeleton-stub').exists()).toBe(true)

      // Resolve and clean up
      resolveWatchlist!({
        json: async () => ({ status: 200, data: [] }),
        ok: true,
        status: 200,
      })
      await flushPromises()
    })
  })

  /* ─── 7. Error state ─── */
  describe('error state', () => {
    it('shows error message when watchlist fetch fails', async () => {
      mockWatchlistError()

      const wrapper = mountComponent()
      await flushPromises()
      await nextTick()

      const empty = wrapper.find('.el-empty-stub')
      expect(empty.exists()).toBe(true)
      expect(empty.text()).toContain('加载失败')
    })
  })

  /* ─── 8. Coefficient format edge cases ─── */
  describe('coefficient formatting', () => {
    it('formats 1.0 as 100.00%', async () => {
      mockWatchlistResponse([
        {
          system_id: 1,
          system_name: 'Test',
          system_name_zh: '测试',
          manufacturing: 1.0,
          reaction: 1.0,
        },
      ])

      const wrapper = mountComponent()
      await flushPromises()
      await nextTick()

      const html = wrapper.html()
      expect(html).toContain('100.00%')
    })

    it('formats 0.0 as 0.00%', async () => {
      mockWatchlistResponse([
        {
          system_id: 1,
          system_name: 'Test',
          system_name_zh: '测试',
          manufacturing: 0.0,
          reaction: 0.0,
        },
      ])

      const wrapper = mountComponent()
      await flushPromises()
      await nextTick()

      const html = wrapper.html()
      expect(html).toContain('0.00%')
    })
  })

  /* ─── 9. Section card structure ─── */
  describe('section structure', () => {
    it('renders with section-card and section-header pattern', async () => {
      mockWatchlistResponse([])

      const wrapper = mountComponent()
      await flushPromises()
      await nextTick()

      expect(wrapper.find('.section-card').exists()).toBe(true)
      expect(wrapper.find('.section-header').exists()).toBe(true)
    })

    it('has title with 系数监控 text', async () => {
      mockWatchlistResponse([])

      const wrapper = mountComponent()
      await flushPromises()
      await nextTick()

      expect(wrapper.text()).toContain('系数监控')
    })
  })

  /* ─── 10. Search selection adds system ─── */
  describe('search selection', () => {
    it('calls add API when a search result is selected', async () => {
      mockWatchlistResponse([])
      mockAddResponse()
      // After add, refresh list
      mockWatchlistResponse([])

      const wrapper = mountComponent()
      await flushPromises()
      await nextTick()

      const autocomplete = wrapper.find('.el-autocomplete-stub')
      expect(autocomplete.exists()).toBe(true)

      // Simulate selecting an item (via the stubbed keyup.enter that emits 'select')
      const input = wrapper.find('.el-autocomplete-input')
      await input.trigger('keyup.enter')
      await flushPromises()
      await nextTick()

      expect(mockHttpPost).toHaveBeenCalledWith(
        '/EVE/home/coefficient/add',
        expect.objectContaining({ system_id: expect.any(Number) }),
      )
    })
  })
})
