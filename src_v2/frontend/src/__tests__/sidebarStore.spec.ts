import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useSidebarStore } from '@/stores/sidebar'

/**
 * 侧栏「钉住」偏好（P2-b）
 * 只测可持久化的那一半：写 localStorage、刷新后读回、缺省值。
 * 展开/收起的临时态（hover、点折叠按钮）在组件里，不在 store。
 */
const KEY = 'kahuna_sidebar_pinned'

describe('sidebar store · 钉住偏好', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('初始未钉住', () => {
    const store = useSidebarStore()
    expect(store.pinned).toBe(false)
  })

  it('钉住后写入 localStorage', () => {
    const store = useSidebarStore()
    store.setPinned(true)
    expect(store.pinned).toBe(true)
    expect(localStorage.getItem(KEY)).toBe('1')
  })

  it('取消钉住写 0，不会留旧值', () => {
    const store = useSidebarStore()
    store.setPinned(true)
    store.setPinned(false)
    expect(store.pinned).toBe(false)
    expect(localStorage.getItem(KEY)).toBe('0')
  })

  it('togglePinned 来回切换', () => {
    const store = useSidebarStore()
    store.togglePinned()
    expect(store.pinned).toBe(true)
    store.togglePinned()
    expect(store.pinned).toBe(false)
  })

  it('刷新（重建 store）后仍读回钉住状态', () => {
    localStorage.setItem(KEY, '1')
    setActivePinia(createPinia())
    const store = useSidebarStore()
    expect(store.pinned).toBe(true)
  })

  it('脏值只当没钉住', () => {
    localStorage.setItem(KEY, 'yes')
    setActivePinia(createPinia())
    const store = useSidebarStore()
    expect(store.pinned).toBe(false)
  })
})
