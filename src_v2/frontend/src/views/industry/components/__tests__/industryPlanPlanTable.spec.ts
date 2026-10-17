import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import IndustryPlanPlanTable from '../industryPlanPlanTable.vue'

// ---------------------------------------------------------------------------
// Types matching the component's PlanRow interface
// ---------------------------------------------------------------------------
interface PlanRow {
  row_id: number
  type: 'group' | 'product'
  group_id?: string | null
  order: number
  type_id?: number
  quantity?: number
  type_name?: string
  type_name_zh?: string
  active?: boolean
  note?: string
  name?: string
}

// ---------------------------------------------------------------------------
// Factories
// ---------------------------------------------------------------------------
const makeProduct = (overrides: Partial<PlanRow> = {}): PlanRow => ({
  row_id: 1,
  type: 'product',
  type_id: 12345,
  quantity: 10,
  type_name: 'Test Item',
  type_name_zh: '测试物品',
  active: true,
  order: 0,
  group_id: null,
  ...overrides,
})

const makeGroup = (overrides: Partial<PlanRow> = {}): PlanRow => ({
  row_id: 2,
  type: 'group',
  name: 'Test Group',
  order: 1,
  ...overrides,
})

// ---------------------------------------------------------------------------
// Global stubs for Element Plus + VueDraggable
// We need basic stubs so the component mounts in jsdom without errors.
// el-switch and el-input-number stubs emit change events to trigger
// emitFlattened where needed.
// ---------------------------------------------------------------------------
const globalStubs = {
  VueDraggable: false,
  'el-scrollbar': {
    template: '<div class="el-scrollbar-stub"><slot /></div>',
  },
  'el-input-number': {
    template:
      '<div class="el-input-number-stub"><button class="increase-btn" @click="inc">+</button></div>',
    props: ['modelValue'],
    emits: ['update:modelValue', 'change'],
    methods: {
      inc() {
        const v = (this.modelValue ?? 0) + 1
        this.$emit('update:modelValue', v)
        this.$emit('change', v)
      },
    },
  },
  'el-switch': {
    template: '<div class="el-switch-stub" @click="toggle"></div>',
    props: ['modelValue'],
    emits: ['update:modelValue', 'change'],
    methods: {
      toggle() {
        this.$emit('update:modelValue', !this.modelValue)
        this.$emit('change', !this.modelValue)
      },
    },
  },
  'el-button': {
    template: '<button class="el-button-stub"><slot /></button>',
  },
  'el-icon': {
    template: '<i class="el-icon-stub"><slot /></i>',
  },
  'el-dialog': {
    template:
      '<div v-if="modelValue" class="el-dialog-stub"><slot /></div>',
    props: ['modelValue'],
    emits: ['update:modelValue'],
  },
  'el-input': {
    template:
      '<input class="note-input-stub" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
    props: ['modelValue'],
    emits: ['update:modelValue'],
  },
  'el-tooltip': {
    template: '<span class="el-tooltip-stub" :content="content"><slot /></span>',
    props: ['content'],
  },
}

// ---------------------------------------------------------------------------
// Helper to mount the component
// ---------------------------------------------------------------------------
const createWrapper = (list: PlanRow[], cardStyleMode: 'normal' | 'compact' = 'normal') => {
  return mount(IndustryPlanPlanTable, {
    props: { list, cardStyleMode },
    global: { stubs: globalStubs },
    attachTo: document.body,
  })
}

// ========================================================================
// Tests — product note feature (all tests pass now that the feature is implemented)
// ========================================================================
describe('industryPlanPlanTable — product note feature', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // -----------------------------------------------------------------------
  // Test 1  – Note text displayed next to product name on same row
  // -----------------------------------------------------------------------
  it('should display note text next to product name on the same row', async () => {
    const product = makeProduct({ note: '需要10个' })
    const wrapper = createWrapper([product])
    await nextTick()

    const noteEl = wrapper.find('.product-note')
    expect(noteEl.exists()).toBe(true)
    expect(noteEl.text()).toContain('需要10个')
  })

  // -----------------------------------------------------------------------
  // Test 2  – Edit icon appears on product card hover
  // -----------------------------------------------------------------------
  it('should show a note edit icon when hovering over a product card', async () => {
    const product = makeProduct({ note: '测试备注' })
    const wrapper = createWrapper([product])
    await nextTick()

    await wrapper.find('.product-card').trigger('mouseenter')
    await nextTick()

    const editIcon = wrapper.find('.note-edit-icon')
    expect(editIcon.exists()).toBe(true)
  })

  // -----------------------------------------------------------------------
  // Test 3  – Clicking edit icon shows inline input
  // -----------------------------------------------------------------------
  it('should display an inline input when clicking the note edit icon', async () => {
    const product = makeProduct({ note: '测试备注' })
    const wrapper = createWrapper([product])
    await nextTick()

    await wrapper.find('.product-card').trigger('mouseenter')
    await nextTick()

    const editIcon = wrapper.find('.note-edit-icon')
    expect(editIcon.exists()).toBe(true)
    await editIcon.trigger('click')
    await nextTick()

    const input = wrapper.find('.note-input')
    expect(input.exists()).toBe(true)
  })

  // -----------------------------------------------------------------------
  // Test 4  – Enter key saves note
  // -----------------------------------------------------------------------
  it('should save note when Enter key is pressed in the inline input', async () => {
    const product = makeProduct({ note: '旧备注' })
    const wrapper = createWrapper([product])
    await nextTick()

    // Navigate to inline input
    await wrapper.find('.product-card').trigger('mouseenter')
    await nextTick()
    await wrapper.find('.note-edit-icon').trigger('click')
    await nextTick()

    const input = wrapper.find('.note-input')
    expect(input.exists()).toBe(true)

    // Type new note and press Enter
    await input.setValue('新备注内容')
    await input.trigger('keyup.enter')
    await nextTick()

    // Verify the emitted data contains the updated note
    const emitted = wrapper.emitted('update:list')
    expect(emitted).toBeTruthy()
    if (emitted) {
      const payload = emitted[emitted.length - 1][0] as PlanRow[]
      const updatedProduct = payload.find((p) => p.row_id === product.row_id)
      expect(updatedProduct).toBeDefined()
      expect(updatedProduct!.note).toBe('新备注内容')
    }
  })

  // -----------------------------------------------------------------------
  // Test 5  – Blur (click away) saves note
  // -----------------------------------------------------------------------
  it('should save note when the inline input loses focus (blur)', async () => {
    const product = makeProduct({ note: '旧备注' })
    const wrapper = createWrapper([product])
    await nextTick()

    // Navigate to inline input
    await wrapper.find('.product-card').trigger('mouseenter')
    await nextTick()
    await wrapper.find('.note-edit-icon').trigger('click')
    await nextTick()

    const input = wrapper.find('.note-input')
    expect(input.exists()).toBe(true)

    // Type new note and blur
    await input.setValue('通过blur保存')
    await input.trigger('blur')
    await nextTick()

    const emitted = wrapper.emitted('update:list')
    expect(emitted).toBeTruthy()
    if (emitted) {
      const payload = emitted[emitted.length - 1][0] as PlanRow[]
      const updatedProduct = payload.find((p) => p.row_id === product.row_id)
      expect(updatedProduct).toBeDefined()
      expect(updatedProduct!.note).toBe('通过blur保存')
    }
  })

  // -----------------------------------------------------------------------
  // Test 6  – Long note truncated with ellipsis
  // -----------------------------------------------------------------------
  it('should truncate long notes with ellipsis', async () => {
    const longNote = '这是一条非常长的备注用来测试文本截断效果，它应该超过显示宽度并被CSS截断显示为省略号，以确保界面整洁。'.repeat(
      3,
    )
    const product = makeProduct({ note: longNote })
    const wrapper = createWrapper([product])
    await nextTick()

    const noteEl = wrapper.find('.product-note')
    expect(noteEl.exists()).toBe(true)

    // Verify CSS truncation properties are applied
    const style = getComputedStyle(noteEl.element)
    // Note: jsdom does not support text-overflow:ellipsis in getComputedStyle (always returns 'clip')
    // The CSS rule is correctly set in the component's scoped styles
    expect(style.overflow).toBe('hidden')
    expect(style.whiteSpace).toBe('nowrap')
  })

  // -----------------------------------------------------------------------
  // Test 7  – Hover over truncated note shows tooltip with full text
  // -----------------------------------------------------------------------
  it('should show a tooltip with the full note text when hovering a truncated note', async () => {
    const longNote = 'A'.repeat(300)
    const product = makeProduct({ note: longNote })
    const wrapper = createWrapper([product])
    await nextTick()

    const noteEl = wrapper.find('.product-note')
    expect(noteEl.exists()).toBe(true)

    // Assert an el-tooltip is present on the note element
    const tooltip = wrapper.find('.product-note-tooltip')
    expect(tooltip.exists()).toBe(true)
    expect(tooltip.attributes('content')).toBe(longNote)
  })

  // -----------------------------------------------------------------------
  // Test 8  – Note survives flatten → nest round-trip (data integrity)
  // -----------------------------------------------------------------------
  it('should preserve the note field through a flatten → nest round-trip', async () => {
    // Mount with a group containing a product that has a note
    const product = makeProduct({
      row_id: 10,
      note: 'round-trip备注',
      group_id: 'Test Group',
    })
    const group = makeGroup({ row_id: 20, name: 'Test Group' })
    const wrapper = createWrapper([group, product])
    await nextTick()

    // Trigger any action that calls emitFlattened (e.g. toggling a switch)
    const switchStub = wrapper.find('.el-switch-stub')
    if (switchStub.exists()) {
      await switchStub.trigger('click')
      await nextTick()
    }

    // Also directly simulate via setProps to verify nested data
    await wrapper.setProps({
      list: [
        { ...group },
        { ...product, group_id: 'Test Group', order: 0 },
      ],
    })
    await nextTick()

    // After rebuild, trigger a new emit and verify note persisted
    const switchStub2 = wrapper.find('.el-switch-stub')
    if (switchStub2.exists()) {
      await switchStub2.trigger('click')
      await nextTick()
    }

    const emitted = wrapper.emitted('update:list')
    expect(emitted).toBeTruthy()
    if (emitted) {
      const lastPayload = emitted[emitted.length - 1][0] as PlanRow[]
      // The product's note should still be present in the emitted flat list
      const productInPayload = lastPayload.find(
        (p) => p.type === 'product' && p.row_id === 10,
      )
      expect(productInPayload).toBeDefined()
      expect(productInPayload!.note).toBe('round-trip备注')
    }
  })

  // -----------------------------------------------------------------------
  // Test 9  – Input limited to 200 characters (maxlength)
  // -----------------------------------------------------------------------
  it('should limit the note input to 200 characters via maxlength', async () => {
    const product = makeProduct({ note: '测试' })
    const wrapper = createWrapper([product])
    await nextTick()

    // Navigate to inline input
    await wrapper.find('.product-card').trigger('mouseenter')
    await nextTick()
    await wrapper.find('.note-edit-icon').trigger('click')
    await nextTick()

    const input = wrapper.find('.note-input')
    expect(input.exists()).toBe(true)
    expect(input.attributes('maxlength')).toBe('200')
  })

  // -----------------------------------------------------------------------
  // Test 10 – Empty string input clears the note
  // -----------------------------------------------------------------------
  it('should clear the note when the input value is set to an empty string', async () => {
    const product = makeProduct({ note: '待清除的备注' })
    const wrapper = createWrapper([product])
    await nextTick()

    // Navigate to inline input
    await wrapper.find('.product-card').trigger('mouseenter')
    await nextTick()
    await wrapper.find('.note-edit-icon').trigger('click')
    await nextTick()

    const input = wrapper.find('.note-input')
    expect(input.exists()).toBe(true)

    // Clear input (set to empty string)
    await input.setValue('')
    await input.trigger('keyup.enter')
    await nextTick()

    const emitted = wrapper.emitted('update:list')
    expect(emitted).toBeTruthy()
    if (emitted) {
      const payload = emitted[emitted.length - 1][0] as PlanRow[]
      const updatedProduct = payload.find((p) => p.row_id === product.row_id)
      expect(updatedProduct).toBeDefined()
      // Note should be cleared (undefined or empty string)
      expect(updatedProduct!.note).toBeUndefined()
    }
  })

  // -----------------------------------------------------------------------
  // Test 11 – Group cards do NOT show edit icon (while product cards do)
  // -----------------------------------------------------------------------
  it('should NOT show a note edit icon on group cards, while product cards do show it on hover', async () => {
    const product = makeProduct({ note: '产品备注', row_id: 1, group_id: 'My Group' })
    const group = makeGroup({ row_id: 2, name: 'My Group' })
    const wrapper = createWrapper([group, product])
    await nextTick()

    // Groups should never have a note edit icon
    const groupIcons = wrapper.find('.group-header .note-edit-icon')
    expect(groupIcons.exists()).toBe(false)

    // Product cards SHOULD show the note edit icon on hover
    await wrapper.find('.product-card').trigger('mouseenter')
    await nextTick()

    const productIcon = wrapper.find('.product-card .note-edit-icon')
    expect(productIcon.exists()).toBe(true)
  })

  // -----------------------------------------------------------------------
  // Test 12 – Compact mode displays notes correctly
  // -----------------------------------------------------------------------
  it('should display notes correctly in compact mode', async () => {
    const product = makeProduct({ note: '紧凑模式备注' })
    const wrapper = createWrapper([product], 'compact')
    await nextTick()

    // Verify the container has the compact class
    expect(wrapper.find('.compact').exists()).toBe(true)

    // Note should still be visible in compact mode
    const noteEl = wrapper.find('.compact .product-note')
    expect(noteEl.exists()).toBe(true)
    expect(noteEl.text()).toContain('紧凑模式备注')
  })
})
