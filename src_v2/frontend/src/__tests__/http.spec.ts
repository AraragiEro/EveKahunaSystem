import { describe, it, expect } from 'vitest'

describe('HttpService module', () => {
  it('should export http named instance', async () => {
    const { http } = await import('@/http')
    expect(http).toBeDefined()
    expect(typeof http.request).toBe('function')
  })

  it('should have convenience methods', async () => {
    const { http } = await import('@/http')
    expect(typeof http.get).toBe('function')
    expect(typeof http.post).toBe('function')
    expect(typeof http.put).toBe('function')
    expect(typeof http.delete).toBe('function')
  })

  it('request should accept full config', async () => {
    const { http } = await import('@/http')
    expect(http.request.length).toBeGreaterThanOrEqual(1)
  })

  it('should have timeout configured on axios instance', async () => {
    const { http } = await import('@/http')
    expect((http as any).client?.defaults?.timeout).toBe(120000)
  })
})
