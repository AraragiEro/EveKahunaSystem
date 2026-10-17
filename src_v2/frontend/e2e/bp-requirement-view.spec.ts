import { test, expect } from '@playwright/test'

/**
 * E2E 测试：蓝图需求视图 (Blueprint Requirements View)
 *
 * 验证 /industry/flowDecomposition 页面中 "蓝图需求视图" Tab 的功能：
 * 1. Tab 可见性与标签文本
 * 2. 数据表格渲染（7 列）
 * 3. 空状态展示（无数据时显示 "无缺失蓝图"）
 * 4. 浏览器控制台无错误
 *
 * 前置条件：
 * - 需要运行中的服务器 (baseURL: http://localhost:9527)
 * - Tab 需要 vip_alpha 角色才能交互（未授权时 Tab 为 disabled 状态）
 *
 * 运行方式：
 *   cd src_v2/frontend && npx playwright test e2e/bp-requirement-view.spec.ts
 */

/** 期望的 8 个列标签（与 BlueprintRequirementsView.vue 中 el-table-column 的 label 一致） */
const EXPECTED_COLUMNS = [
  'icon',
  '物品名称(zh)',
  '物品名称(en)',
  '类型',
  '缺少BPC数量',
  '每张BPC运行次数',
  '总运行次数',
  'T2发明源蓝图',
]

/** 蓝图需求视图 Tab 的标签文本 */
const TAB_LABEL = '蓝图需求视图'

/** 获取 Tab 定位器 */
const getTab = (page: any) =>
  page.locator(`.el-tabs__item:has-text("${TAB_LABEL}")`).first()

/** 检查 Tab 是否被禁用 */
const isTabDisabled = async (tab: any): Promise<boolean> =>
  tab.evaluate((el: HTMLElement) => el.classList.contains('is-disabled'))

test.describe('蓝图需求视图 Tab', () => {
  test.beforeEach(async ({ page }) => {
    // 导航到页面；未认证时将重定向到 /login
    await page.goto('/industry/flowDecomposition', { waitUntil: 'domcontentloaded' })
  })

  test('1. 页面应正常加载（非空白）', async ({ page }) => {
    await expect(page.locator('body')).not.toBeEmpty()
  })

  test('2. "蓝图需求视图" Tab 应存在于 DOM 中', async ({ page }) => {
    const tab = getTab(page)
    await expect(tab).toBeAttached({ timeout: 10000 })

    const tabText = await tab.textContent()
    expect(tabText).toContain(TAB_LABEL)
  })

  test('3. Tab 状态检查与点击（处理 VIP 权限守卫）', async ({ page }) => {
    const tab = getTab(page)
    await expect(tab).toBeAttached({ timeout: 10000 })

    const disabled = await isTabDisabled(tab)

    if (disabled) {
      console.log(`[INFO] "${TAB_LABEL}" Tab 已禁用 — 需要 vip_alpha 角色才能访问`)
      const ariaDisabled = await tab.getAttribute('aria-disabled')
      expect(ariaDisabled).toBe('true')
    } else {
      await tab.click()
      await page.waitForTimeout(500)

      const isActive = await tab.evaluate((el: HTMLElement) =>
        el.classList.contains('is-active')
      )
      expect(isActive).toBe(true)
    }
  })

  test('4. 表格列完整性 — 验证 7 列渲染', async ({ page }) => {
    const tab = getTab(page)
    await expect(tab).toBeAttached({ timeout: 10000 })

    const disabled = await isTabDisabled(tab)
    if (disabled) {
      test.skip(true, 'Tab 已禁用，跳过列验证')
      return
    }

    await tab.click()
    await page.waitForTimeout(500)

    // 等待表格或空状态元素出现
    const tableOrEmpty = page.locator('.blueprint-req-table, .el-empty').first()
    await expect(tableOrEmpty).toBeAttached({ timeout: 5000 })

    const tableCount = await page.locator('.blueprint-req-table').count()
    if (tableCount > 0) {
      // 有数据：验证 7 个列头
      const headerCells = page.locator(
        '.blueprint-req-table .el-table__header-wrapper th .cell'
      )
      const headerCount = await headerCells.count()
      const headerTexts: string[] = []

      for (let i = 0; i < headerCount; i++) {
        const text = (await headerCells.nth(i).textContent())?.trim() || ''
        headerTexts.push(text)
      }

      console.log(`[INFO] 实际渲染列 (${headerCount}): ${JSON.stringify(headerTexts)}`)
      expect(headerCount).toBe(EXPECTED_COLUMNS.length)

      for (const expectedCol of EXPECTED_COLUMNS) {
        expect(headerTexts).toContain(expectedCol)
      }
    } else {
      // 无数据时验证空状态
      const emptyElement = page.locator('.el-empty')
      await expect(emptyElement).toBeAttached()

      const emptyDesc = await emptyElement.locator('.el-empty__description').textContent()
      expect(emptyDesc).toContain('无缺失蓝图')
    }
  })

  test('5. 空状态文案验证 — 无数据时显示 "无缺失蓝图"', async ({ page }) => {
    const tab = getTab(page)
    await expect(tab).toBeAttached({ timeout: 10000 })

    const disabled = await isTabDisabled(tab)
    if (disabled) {
      test.skip(true, 'Tab 已禁用，跳过空状态验证')
      return
    }

    await tab.click()
    await page.waitForTimeout(500)

    await page.locator('.blueprint-req-table, .el-empty').first().waitFor({ timeout: 5000 })

    const emptyCount = await page.locator('.el-empty').count()
    if (emptyCount > 0) {
      const emptyDesc = page.locator('.el-empty .el-empty__description')
      await expect(emptyDesc).toBeVisible()
      expect(await emptyDesc.textContent()).toBe('无缺失蓝图')
    }
  })

  test('6. 截图存档', async ({ page }) => {
    const tab = getTab(page)
    await expect(tab).toBeAttached({ timeout: 10000 })

    const disabled = await isTabDisabled(tab)
    if (!disabled) {
      await tab.click()
      await page.waitForTimeout(500)
      await page.locator('.blueprint-req-table, .el-empty').first().waitFor({ timeout: 5000 })
    }

    await page.screenshot({
      path: `e2e/screenshots/bp-requirement-view-${disabled ? 'disabled' : 'active'}.png`,
      fullPage: true,
    })
  })

  test('7. 浏览器控制台应无错误', async ({ page }) => {
    const consoleErrors: string[] = []

    // 在导航前注册监听器
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text())
      }
    })

    // 重新导航以捕获完整的加载错误
    await page.goto('/industry/flowDecomposition', { waitUntil: 'networkidle' })
    await page.waitForTimeout(2000)

    // 尝试点击 Tab（如果未禁用）以触发组件渲染
    const tab = getTab(page)
    if (await tab.isVisible()) {
      const disabled = await isTabDisabled(tab)
      if (!disabled) {
        await tab.click()
        await page.waitForTimeout(1000)
      }
    }

    const criticalErrors = consoleErrors.filter(
      (err) =>
        !err.includes('favicon') &&
        !err.includes('404') &&
        !err.includes('Not Found')
    )

    if (criticalErrors.length > 0) {
      console.error(`[ERROR] 控制台错误 (${criticalErrors.length}): ${JSON.stringify(criticalErrors)}`)
    }
    expect(criticalErrors.length).toBe(0)
  })

  test('8. 组件内容快照（文本提取）', async ({ page }) => {
    const tab = getTab(page)
    await expect(tab).toBeAttached({ timeout: 10000 })

    const disabled = await isTabDisabled(tab)
    if (disabled) {
      test.skip(true, 'Tab 已禁用，跳过快照')
      return
    }

    await tab.click()
    await page.waitForTimeout(500)

    const content = page.locator('.blueprint-req-table, .el-empty').first()
    await expect(content).toBeAttached({ timeout: 5000 })

    const text = await content.textContent()
    console.log(`[INFO] 蓝图需求视图内容预览: ${text?.substring(0, 300)}...`)
    expect(text).toBeTruthy()
  })
})
