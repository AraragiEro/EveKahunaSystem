import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

// ── Mock setup (hoisted by vitest) ──
const { mockHttpPost, mockHttpGet } = vi.hoisted(() => ({
  mockHttpPost: vi.fn(),
  mockHttpGet: vi.fn(),
}))

vi.mock('@/http', () => ({
  http: {
    post: mockHttpPost,
    get: mockHttpGet,
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({
    push: vi.fn(),
    replace: vi.fn(),
  })),
}))

// ── Dynamic import after mocks are set ──
const { useAuthStore } = await import('@/stores/auth')

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  // ─── Initial state ───
  describe('initial state', () => {
    it('should not be authenticated initially', () => {
      const store = useAuthStore()
      expect(store.isAuthenticated).toBe(false)
    })

    it('should have null token initially (managed by httpOnly cookie)', () => {
      const store = useAuthStore()
      expect(store.token).toBeNull()
    })

    it('should have null user initially', () => {
      const store = useAuthStore()
      expect(store.user).toBeNull()
    })

    it('should have null error initially', () => {
      const store = useAuthStore()
      expect(store.error).toBeNull()
    })

    it('should not be loading initially', () => {
      const store = useAuthStore()
      expect(store.isLoading).toBe(false)
    })

    it('userRoles should be empty array when not authenticated', () => {
      const store = useAuthStore()
      expect(store.userRoles).toEqual([])
    })
  })

  // ─── Login ───
  describe('login', () => {
    it('should set token and user on successful login', async () => {
      const store = useAuthStore()

      mockHttpPost.mockResolvedValueOnce({
        json: async () => ({
          status: 200,
          token: 'login-token-123',
          user: { id: 'u1', username: 'kahuna', roles: ['user'] },
        }),
      })

      const result = await store.login({ username: 'kahuna', password: 'secret' })

      expect(result.success).toBe(true)
      expect(store.user).toEqual({ id: 'u1', username: 'kahuna', roles: ['user'] })
      expect(store.isAuthenticated).toBe(true)
    })

    it('should set user after successful login', async () => {
      const store = useAuthStore()
      mockHttpPost.mockResolvedValueOnce({
        json: async () => ({
          status: 200,
          token: 'persisted-token',
          user: { id: 'u1', username: 'user1', roles: ['user'] },
        }),
      })
      await store.login({ username: 'user1', password: 'pass' })
      expect(store.user).toBeTruthy()
      expect(store.user?.username).toBe('user1')
    })

    it('should set isLoading to true during login and false after', async () => {
      const store = useAuthStore()

      mockHttpPost.mockResolvedValueOnce({
        json: async () => ({
          status: 200,
          token: 'tk',
          user: { id: '1', username: 'u', roles: [] },
        }),
      })

      const loginPromise = store.login({ username: 'u', password: 'p' })
      expect(store.isLoading).toBe(true)

      await loginPromise
      expect(store.isLoading).toBe(false)
    })

    it('should return error on failed login (status !== 200)', async () => {
      const store = useAuthStore()

      mockHttpPost.mockResolvedValueOnce({
        json: async () => ({
          status: 401,
          message: 'Invalid credentials',
        }),
      })

      const result = await store.login({ username: 'bad', password: 'wrong' })

      expect(result.success).toBe(false)
      expect(result.error).toBe('Invalid credentials')
      expect(store.token).toBeNull()
      expect(store.isAuthenticated).toBe(false)
    })

    it('should return error on network failure', async () => {
      const store = useAuthStore()

      mockHttpPost.mockRejectedValueOnce(new Error('Network Error'))

      const result = await store.login({ username: 'u', password: 'p' })

      expect(result.success).toBe(false)
      expect(result.error).toBe('Network Error')
      expect(store.isLoading).toBe(false)
    })

    it('should clear previous error before attempting login', async () => {
      const store = useAuthStore()
      // Manually set error
      store.error = 'previous error'

      mockHttpPost.mockResolvedValueOnce({
        json: async () => ({
          status: 200,
          token: 'tk',
          user: { id: '1', username: 'u', roles: [] },
        }),
      })

      await store.login({ username: 'u', password: 'p' })
      expect(store.error).toBeNull()
    })
  })

  // ─── Logout ───
  describe('logout', () => {
    it('should clear user on logout', () => {
      const store = useAuthStore()
      store.user = { id: 'u1', username: 'test', email: '', roles: ['user'] } as any
      store.logout()
      expect(store.isAuthenticated).toBe(false)
    })

    it('should set isAuthenticated to false after logout', () => {
      const store = useAuthStore()
      store.token = 'tk'
      store.user = { id: '1', username: 'u', email: '', roles: [] }

      store.logout()

      expect(store.isAuthenticated).toBe(false)
    })
  })

  // ─── CheckAuth ───
  describe('checkAuth', () => {
    it('should return false when no token exists', async () => {
      const store = useAuthStore()
      const result = await store.checkAuth()
      expect(result).toBe(false)
    })

    it('should return true when /auth/me returns status 200', async () => {
      const store = useAuthStore()
      store.token = 'valid-token'

      mockHttpGet.mockResolvedValueOnce({
        json: async () => ({
          status: 200,
          id: 'u1',
          username: 'kahuna',
          roles: ['user'],
          vipEndDate: '2025-12-31',
        }),
      })

      const result = await store.checkAuth()

      expect(result).toBe(true)
      expect(store.user).toEqual({
        id: 'u1',
        username: 'kahuna',
        email: '',
        roles: ['user'],
        vipEndDate: '2025-12-31',
      })
    })

    it('should logout and return false when /auth/me returns non-200 status', async () => {
      const store = useAuthStore()
      store.token = 'expired-token'

      mockHttpGet.mockResolvedValueOnce({
        json: async () => ({
          status: 401,
          message: 'Token expired',
        }),
      })

      const result = await store.checkAuth()

      expect(result).toBe(false)
    })

    it('should logout and return false when /auth/me returns invalid data shape', async () => {
      const store = useAuthStore()
      store.token = 'bad-token'

      mockHttpGet.mockResolvedValueOnce({
        json: async () => 'not an object',
      })

      const result = await store.checkAuth()

      expect(result).toBe(false)
    })

    it('should logout and return false when /auth/me throws', async () => {
      const store = useAuthStore()
      store.token = 'network-token'

      mockHttpGet.mockRejectedValueOnce(new Error('Timeout'))

      const result = await store.checkAuth()

      expect(result).toBe(false)
    })

    it('should logout on JSON parse failure', async () => {
      const store = useAuthStore()
      store.token = 'bad-json-token'

      mockHttpGet.mockResolvedValueOnce({
        json: async () => {
          throw new Error('Unexpected token')
        },
        text: async () => 'not json',
      })

      const result = await store.checkAuth()

      expect(result).toBe(false)
    })

    it('should cache successful auth check for subsequent calls', async () => {
      const store = useAuthStore()
      store.token = 'cache-token'

      mockHttpGet.mockResolvedValueOnce({
        json: async () => ({
          status: 200,
          id: 'u2',
          username: 'cached-user',
          roles: ['user'],
        }),
      })

      // First call - hits the API
      const result1 = await store.checkAuth()
      expect(result1).toBe(true)
      expect(mockHttpGet).toHaveBeenCalledTimes(1)
      expect(store.user?.username).toBe('cached-user')

      // Second call - should use cache, not hit API again
      const result2 = await store.checkAuth()
      expect(result2).toBe(true)
      // Still only called once (cached)
      expect(mockHttpGet).toHaveBeenCalledTimes(1)
    })
  })

  // ─── ClearError ───
  describe('clearError', () => {
    it('should clear the error state', () => {
      const store = useAuthStore()
      store.error = 'Something went wrong'

      store.clearError()

      expect(store.error).toBeNull()
    })
  })

  // ─── ClearAuthCache ───
  describe('clearAuthCache', () => {
    it('should force next checkAuth to call the API even when cache is valid', async () => {
      const store = useAuthStore()
      store.token = 'refresh-token'

      mockHttpGet.mockResolvedValue({
        json: async () => ({
          status: 200,
          id: 'u3',
          username: 'refresh-user',
          roles: ['user'],
        }),
      })

      // First checkAuth (fills cache)
      await store.checkAuth()
      expect(mockHttpGet).toHaveBeenCalledTimes(1)

      // Cache still valid, but clear it
      store.clearAuthCache()
      await store.checkAuth()
      // Should have made a second call since cache was cleared
      expect(mockHttpGet).toHaveBeenCalledTimes(2)
    })
  })
})
