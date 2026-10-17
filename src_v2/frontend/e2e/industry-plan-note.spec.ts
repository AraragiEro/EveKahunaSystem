import { test, expect } from '@playwright/test'

/**
 * E2E 测试：工业计划产品备注 (Product Note)
 *
 * 验证 /industry/industryPlan 页面中产品备注功能的完整流程：
 * 1. 登录 (若未认证)
 * 2. 导航到工业计划页面并选择计划
 * 3. 悬停产品卡片 → 显示编辑图标
 * 4. 点击编辑图标 → 输入备注
 * 5. Enter 保存 → 备注显示在卡片上
 * 6. 点击"保存计划" → 刷新页面 → 备注仍然存在
 *
 * 前置条件：
 * - 需要运行中的服务器 (baseURL: http://localhost:9527)
 * - 需要有效的测试账号
 *
 * 运行方式：
 *   cd src_v2/frontend && npx playwright test e2e/industry-plan-note.spec.ts
 */

/** 从环境变量读取测试凭证，未设置时使用默认值 */
const TEST_USERNAME = process.env.E2E_TEST_USERNAME || 'kahuna'
const TEST_PASSWORD = process.env.E2E_TEST_PASSWORD || 'kahuna'

test.describe('工业计划产品备注', () => {
  test('完整的备注流程：编辑 → 保存 → 刷新 → 持久化', async ({ page }) => {
    // ===== Phase 1: 导航到工业计划页面 =====
    await page.goto('/industry/industryPlan', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(500)

    // ===== Phase 2: 登录 (若被重定向到登录页) =====
    if (page.url().includes('/login')) {
      // 填写用户名
      const usernameInput = page.locator('input[placeholder="用户名"]')
      await expect(usernameInput).toBeVisible({ timeout: 5000 })
      await usernameInput.fill(TEST_USERNAME)

      // 填写密码
      const passwordInput = page.locator('input[placeholder="密码"]')
      await passwordInput.fill(TEST_PASSWORD)

      // 点击登录
      const loginButton = page.locator('button:has-text("登录")')
      await loginButton.click()

      // 等待登录成功并重定向回工业计划页面
      await page.waitForURL('**/industry/industryPlan', { timeout: 15000 })
      await page.waitForTimeout(500)
    }

    // 确认已到达工业计划页面
    await expect(page.locator('body')).not.toBeEmpty()
    expect(page.url()).toContain('/industry/industryPlan')

    // ===== Phase 3: 选择计划 =====
    // 打开计划选择下拉框
    const planSelect = page.locator('.plan-select')
    await expect(planSelect).toBeVisible({ timeout: 10000 })
    await planSelect.click()
    await page.waitForTimeout(300)

    // 选中第一个可用的计划选项
    const firstOption = page.locator('.el-select-dropdown__item').first()
    await expect(firstOption).toBeVisible({ timeout: 5000 })
    const planName = await firstOption.textContent() || ''
    await firstOption.click()
    await page.waitForTimeout(800) // 等待产品列表加载

    // ===== Phase 4: 找到第一个 active 的产品卡片并对备注进行编辑 =====
    // 定位产品卡片（优先 top-level-product，其次 grouped）
    const productCard = page.locator('.product-card').first()
    await expect(productCard).toBeVisible({ timeout: 10000 })

    // 悬停产品卡片以显示备注编辑图标
    await productCard.hover()
    await page.waitForTimeout(200)

    // 定位备注编辑图标（hover 后 opacity 变为 1）
    const editIcon = productCard.locator('.note-edit-icon')
    await expect(editIcon).toBeVisible({ timeout: 3000 })

    // 点击编辑图标
    await editIcon.click()
    await page.waitForTimeout(300)

    // 验证备注输入框出现
    const noteInput = page.locator('.note-input input').first()
    await expect(noteInput).toBeVisible({ timeout: 3000 })

    // 输入备注内容
    const testNote = `E2E测试备注 ${Date.now()}`
    await noteInput.fill(testNote)

    // 按 Enter 保存备注
    await noteInput.press('Enter')
    await page.waitForTimeout(300)

    // 验证备注文本显示在卡片上
    const noteText = productCard.locator('.product-note .note-text')
    await expect(noteText).toBeVisible({ timeout: 3000 })
    expect(await noteText.textContent()).toBe(testNote)

    // ===== Phase 5: 保存计划到后端 =====
    const saveButton = page.locator('button:has-text("保存计划")')
    await expect(saveButton).toBeVisible()
    await saveButton.click()
    // 等待保存完成（成功消息或网络请求完成）
    await page.waitForTimeout(1000)

    // ===== Phase 6: 刷新页面验证持久化 =====
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(500)

    // 重新选择同一个计划
    await planSelect.click()
    await page.waitForTimeout(300)
    // 选择之前记录的计划名
    const planOption = page.locator(`.el-select-dropdown__item:has-text("${planName.trim()}")`)
    if (await planOption.count() > 0) {
      await planOption.click()
    } else {
      // 如果精确匹配失败，选第一个
      const anyOption = page.locator('.el-select-dropdown__item').first()
      await anyOption.click()
    }
    await page.waitForTimeout(800)

    // 等待产品卡片重新加载
    const reloadedCard = page.locator('.product-card').first()
    await expect(reloadedCard).toBeVisible({ timeout: 10000 })

    // 验证备注文本仍然存在
    const persistedNote = reloadedCard.locator('.product-note .note-text')
    await expect(persistedNote).toBeVisible({ timeout: 5000 })
    expect(await persistedNote.textContent()).toBe(testNote)

    // ===== 截图存档 =====
    await page.screenshot({
      path: `e2e/screenshots/industry-plan-note-${Date.now()}.png`,
      fullPage: true,
    })
  })
})
