import { test, expect } from '@playwright/test'

/**
 * E2E 冒烟测试
 *
 * 验证核心页面可正常访问，无崩溃或空白。
 * 完整用户旅程测试需要运行中的服务器 + 数据库服务。
 */

test.describe('Landing Page', () => {
  test('should load landing page', async ({ page }) => {
    await page.goto('/')
    // 页面标题或内容存在
    await expect(page.locator('body')).not.toBeEmpty()
  })

  test('should have page title', async ({ page }) => {
    await page.goto('/')
    const title = await page.title()
    expect(title).toBeTruthy()
  })
})

test.describe('Login Page', () => {
  test('should navigate to login page', async ({ page }) => {
    await page.goto('/login')
    await expect(page.locator('body')).not.toBeEmpty()
  })

  test('should show login form elements', async ({ page }) => {
    await page.goto('/login')
    // 检查表单元素存在（Element Plus 组件）
    const inputs = page.locator('input')
    const count = await inputs.count()
    expect(count).toBeGreaterThan(0)
  })
})

test.describe('API Docs', () => {
  test('should load API documentation', async ({ page }) => {
    await page.goto('/api/docs')
    await expect(page.locator('body')).not.toBeEmpty()
  })
})
