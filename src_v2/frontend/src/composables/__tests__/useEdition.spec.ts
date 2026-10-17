import { describe, it, expect, beforeEach } from 'vitest'

/**
 * useEdition 测试
 *
 * import.meta.env 在 Vite 中为编译时替换，无法在运行时通过 vi.stubEnv 修改。
 * 本测试直接使用当前环境的实际设置值，验证核心逻辑一致性。
 */
describe('useEdition', () => {
  let mod: typeof import('@/composables/useEdition')

  beforeEach(async () => {
    // Use dynamic import to get fresh module for each test
    // Note: import.meta.env is transformed at build time, so resetModules
    // won't change VITE_APP_EDITION
    mod = await import('@/composables/useEdition')
  })

  it('should export isEnterprise and isCommunity', () => {
    expect(typeof mod.isEnterprise).toBe('object') // computed ref
    expect(typeof mod.isCommunity).toBe('object')
    expect(typeof mod.isEnterprise.value).toBe('boolean')
    expect(typeof mod.isCommunity.value).toBe('boolean')
  })

  it('isEnterprise and isCommunity must be mutually exclusive', () => {
    expect(mod.isEnterprise.value).toBe(!mod.isCommunity.value)
  })

  it('useEdition() returns edition string', () => {
    const result = mod.useEdition()
    expect(['community', 'enterprise']).toContain(result.edition)
    expect(typeof result.isEnterprise).toBe('boolean')
    expect(typeof result.isCommunity).toBe('boolean')
  })

  it('useEdition() flags match global flags', () => {
    const result = mod.useEdition()
    expect(result.isEnterprise).toBe(mod.isEnterprise.value)
    expect(result.isCommunity).toBe(mod.isCommunity.value)
  })

  it('edition is consistent with boolean flags', () => {
    const { edition, isEnterprise, isCommunity } = mod.useEdition()
    expect(edition === 'enterprise').toBe(isEnterprise)
    expect(edition === 'community').toBe(isCommunity)
  })

  it('only one edition flag is true at a time', () => {
    const { isEnterprise, isCommunity } = mod.useEdition()
    expect(isEnterprise !== isCommunity).toBe(true) // XOR
  })
})
