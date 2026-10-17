<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import type { Ref } from 'vue'
import { useRouter } from 'vue-router'
import { useTransition } from '@vueuse/core'
import {
  Plus,
  Search,
  FolderOpened,
  UserFilled,
  Cpu,
  TrendCharts,
} from '@element-plus/icons-vue'
import { http } from '@/http'
import { handleApiResponse } from '@/utils/apiResponse'
import { useAuthStore } from '@/stores/auth'
import { useAnnouncements, type Announcement } from '@/composables/useAnnouncements'
import CoefficientMonitor from '@/components/dashboard/CoefficientMonitor.vue'

// ──────────────────── 接口定义 ────────────────────

interface OverviewData {
  totalValue?: number
  walletValue: number | Record<string, number>
  orderValue: number | Record<string, number>
  runningProcessValue: number
  markedAssetValue: number
  unmarkedAssetValue: number
}

interface DashboardOverviewResponse {
  today: OverviewData
  last_note_7d: OverviewData | null
  last_note_30d: OverviewData | null
}

interface RunningJobDetail {
  job_type: string
  activity_type: string
  product_type_id: number
  product_name: string
  product_name_zh: string
  runs: number
  product_quantity_per_run: number
  total_quantity: number
  progress_percent: number
  cost: number
  installer_name: string
  installer_id?: number
  value: number
  start_date: string
  end_date: string
}

interface CharacterSummary {
  character_id: number
  character_name: string
  manufacturing_running_count: number
  manufacturing_completed_count: number
  reaction_running_count: number
  reaction_completed_count: number
}

interface OpsStats {
  total_users: number
  total_vips: number
  total_plans: number
  total_asset_value: number
  total_running_value: number
}

// ──────────────────── 工具函数 ────────────────────

const formatNumber = (value: number): string => {
  if (value === null || value === undefined || isNaN(value)) {
    return '0'
  }
  return value.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

const formatCompactNumber = (value: number): string => {
  if (value === null || value === undefined || isNaN(value)) return '0'
  if (value >= 1e12) return (value / 1e12).toFixed(2) + 'T'
  if (value >= 1e9) return (value / 1e9).toFixed(2) + 'B'
  if (value >= 1e6) return (value / 1e6).toFixed(2) + 'M'
  if (value >= 1e3) return (value / 1e3).toFixed(2) + 'K'
  return value.toLocaleString('zh-CN')
}

const getProgressColor = (percentage: number): string => {
  if (percentage >= 90) return '#67c23a'
  if (percentage >= 70) return '#e6a23c'
  if (percentage >= 50) return '#f56c6c'
  return '#909399'
}

const getNumericValue = (value: number | Record<string, number>): number => {
  if (typeof value === 'number') return value
  if (typeof value === 'object') {
    return Object.values(value).reduce(
      (sum, v) => sum + (typeof v === 'number' ? v : 0),
      0,
    )
  }
  return 0
}

const calculateChange = (
  current: number,
  last: number | null,
): { diff: number; percent: number | null; hasChange: boolean } => {
  if (last === null || last === undefined) {
    return { diff: 0, percent: null, hasChange: false }
  }
  const diff = current - last
  const percent =
    last !== 0
      ? (diff / last) * 100
      : diff > 0
        ? Infinity
        : diff < 0
          ? -Infinity
          : 0
  return { diff, percent, hasChange: true }
}

const formatChange = (change: {
  diff: number
  percent: number | null
  hasChange: boolean
}): string => {
  if (!change.hasChange || change.percent === null) return ''
  const sign = change.diff >= 0 ? '+' : ''
  const pct =
    change.percent === Infinity
      ? '+∞%'
      : change.percent === -Infinity
        ? '-∞%'
        : `${sign}${change.percent.toFixed(2)}%`
  return pct
}

const formatRemainingTime = (endDateStr: string): string => {
  const now = new Date()
  const end = new Date(endDateStr)
  const diffMs = end.getTime() - now.getTime()
  if (diffMs <= 0) return '已完成'

  const totalMinutes = Math.floor(diffMs / 60000)
  const days = Math.floor(totalMinutes / (24 * 60))
  const hours = Math.floor((totalMinutes % (24 * 60)) / 60)
  const minutes = totalMinutes % 60

  if (days > 0) {
    return `${days}天${hours}小时${minutes}分钟`
  } else if (hours > 0) {
    return `${hours}小时${minutes}分钟`
  } else {
    return `${minutes}分钟`
  }
}

const stripMarkdown = (md: string): string => {
  if (!md) return ''
  return md
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/__(.+?)__/g, '$1')
    .replace(/\*(.+?)\*/g, '$1')
    .replace(/_(.+?)_/g, '$1')
    .replace(/`(.+?)`/g, '$1')
    .replace(/\[(.+?)\]\(.+?\)/g, '$1')
    .replace(/!\[.*?\]\(.+?\)/g, '')
    .replace(/^[-*+]\s+/gm, '')
    .replace(/^\d+\.\s+/gm, '')
    .replace(/^>/gm, '')
    .replace(/---+/g, '')
    .replace(/\n+/g, ' ')
    .trim()
}

// ──────────────────── 状态 ────────────────────

const router = useRouter()
const authStore = useAuthStore()
const username = computed(() => authStore.user?.username || '指挥官')

const { latest: announcements } = useAnnouncements()

const overviewData = ref<OverviewData | null>(null)
const lastNote7d = ref<OverviewData | null>(null)
const lastNote30d = ref<OverviewData | null>(null)
const selectedTimeRange = ref<'7d' | '30d'>('7d')

const runningJobsList = ref<RunningJobDetail[]>([])
const characterSummaryList = ref<CharacterSummary[]>([])
const loadingOverview = ref(false)
const loadingJobs = ref(false)

const overviewError = ref(false)
const jobsError = ref(false)

const serverStatus = ref<'online' | 'offline' | 'unknown' | null>(null)

const opsStats = ref<OpsStats | null>(null)
const loadingOps = ref(false)
const opsError = ref(false)

// ──────────────────── 计算属性 ────────────────────

const hasCharacters = computed(() => characterSummaryList.value.length > 0)

const showWelcome = computed(
  () => !loadingJobs.value && !jobsError.value && !hasCharacters.value,
)

const totalValueSource = computed(() => {
  if (!overviewData.value) return 0
  const data = overviewData.value
  return (
    getNumericValue(data.walletValue) +
    getNumericValue(data.orderValue) +
    data.runningProcessValue
  )
})

const historyTotalValue = computed(() => {
  const history =
    selectedTimeRange.value === '7d'
      ? lastNote7d.value
      : lastNote30d.value
  if (!history) return null
  return (
    getNumericValue(history.walletValue) +
    getNumericValue(history.orderValue) +
    history.runningProcessValue
  )
})

const totalChange = computed(() =>
  calculateChange(totalValueSource.value, historyTotalValue.value),
)

const outputTotalValue = useTransition(totalValueSource, {
  duration: 2000,
  transition: (t: number) => t * (2 - t),
})

// 按 end_date 升序排列，不做数量限制
const sortedRunningJobs = computed(() => {
  return [...runningJobsList.value].sort(
    (a, b) =>
      new Date(a.end_date).getTime() - new Date(b.end_date).getTime(),
  )
})

// 懒加载
const VISIBLE_STEP = 8
const visibleCount = ref(VISIBLE_STEP)
const jobListRef: Ref<HTMLElement | null> = ref(null)
const hasMoreJobs = computed(() => visibleCount.value < sortedRunningJobs.value.length)
const visibleJobs = computed(() => sortedRunningJobs.value.slice(0, visibleCount.value))

const onJobListScroll = (e: Event) => {
  const el = e.target as HTMLElement
  if (el.scrollTop + el.clientHeight >= el.scrollHeight - 20 && hasMoreJobs.value) {
    visibleCount.value = Math.min(visibleCount.value + VISIBLE_STEP, sortedRunningJobs.value.length)
  }
}

// ──────────────────── 新手指南步骤 ────────────────────

const guideSteps = [
  {
    icon: UserFilled,
    title: '① 认证角色',
    desc: '通过 ESI SSO 授权你的游戏角色',
    route: '/setting/characterSetting',
  },
  {
    icon: Cpu,
    title: '② 创建工业计划',
    desc: '选择产品，配置制造参数',
    route: '/industry/industryPlan',
  },
  {
    icon: TrendCharts,
    title: '③ 查看市场',
    desc: '实时价格查询与利润计算',
    route: '/utils/estimator',
  },
]

// ──────────────────── 数据获取 ────────────────────

const fetchOverview = async () => {
  loadingOverview.value = true
  overviewError.value = false

  try {
    const res = await http.post('/EVE/home/dashboardOverview', {})
    const data = await handleApiResponse<{
      status: number
      data: DashboardOverviewResponse
    }>(res)
    if (data && data.data) {
      overviewData.value = data.data.today
      lastNote7d.value = data.data.last_note_7d
      lastNote30d.value = data.data.last_note_30d
    }
  } catch {
    overviewError.value = true
  } finally {
    loadingOverview.value = false
  }
}

const fetchJobs = async () => {
  loadingJobs.value = true
  jobsError.value = false

  try {
    const res = await http.post('/EVE/home/runningJobsDetails', {
      skip_container_filter: true,
    })
    const data = await handleApiResponse<{
      status: number
      data: {
        detail_list: RunningJobDetail[]
        character_summary_list: CharacterSummary[]
      }
    }>(res)
    if (data && data.data) {
      runningJobsList.value = data.data.detail_list || []
      characterSummaryList.value = data.data.character_summary_list || []
    }
  } catch {
    jobsError.value = true
  } finally {
    loadingJobs.value = false
  }
}

const fetchServerStatus = async () => {
  try {
    const res = await http.get('/EVE/home/serverStatus')
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const data = (await res.json()) as any
    if (data && data.status === 200 && data.data) {
      serverStatus.value = data.data.status as 'online' | 'offline' | 'unknown'
    } else {
      serverStatus.value = 'unknown'
    }
  } catch {
    serverStatus.value = 'unknown'
  }
}

const fetchOpsStats = async () => {
  loadingOps.value = true
  opsError.value = false

  try {
    const res = await http.get('/EVE/home/dashboardStats')
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const data = (await res.json()) as any
    if (data && data.status === 200 && data.data) {
      opsStats.value = {
        total_users: data.data.total_users ?? 0,
        total_vips: data.data.total_vips ?? 0,
        total_plans: data.data.total_plans ?? 0,
        total_asset_value: data.data.total_asset_value ?? 0,
        total_running_value: data.data.total_running_value ?? 0,
      }
    }
  } catch {
    opsError.value = true
  } finally {
    loadingOps.value = false
  }
}

onMounted(() => {
  fetchOverview()
  fetchJobs()
  fetchServerStatus()
  fetchOpsStats()
})
</script>

<template>
  <div class="dashboard-root">
    <!-- ═══════════════ 页面标题 ═══════════════ -->
    <div class="page-header">
      <div class="page-header-left">
        <h1 class="page-title">仪表盘</h1>
        <p class="page-subtitle">欢迎回来，{{ username }}</p>
      </div>
      <div class="page-header-center" v-if="serverStatus">
        <span class="status-dot" :class="{'status-online': serverStatus === 'online', 'status-offline': serverStatus === 'offline', 'status-unknown': serverStatus === 'unknown'}"></span>
        <span class="status-text">{{ serverStatus === 'online' ? 'TQ 在线' : serverStatus === 'offline' ? 'TQ 维护中' : 'TQ 状态未知' }}</span>
      </div>
      <div class="header-actions">
        <el-button type="primary" @click="router.push('/industry/industryPlan')">
          <el-icon><Plus /></el-icon>新建工业计划
        </el-button>
        <el-button @click="router.push('/utils/estimator')">
          <el-icon><Search /></el-icon>市场查询
        </el-button>
        <el-button @click="router.push('/industry/assetView')">
          <el-icon><FolderOpened /></el-icon>资产管理
        </el-button>
      </div>
    </div>

    <!-- ═══════════════ 未认证用户：欢迎引导 ═══════════════ -->
    <div v-if="showWelcome" class="welcome-section">
      <div class="welcome-card">
        <h2>🚀 欢迎来到 Kahuna</h2>
        <p>认证 ESI 角色，解锁工业规划与资产管理</p>
        <el-button
          type="primary"
          size="large"
          @click="router.push('/setting/characterSetting')"
        >
          前往角色设置 →
        </el-button>
      </div>
      <div class="guide-cards">
        <div
          v-for="step in guideSteps"
          :key="step.title"
          class="guide-card"
        >
          <el-icon :size="32"><component :is="step.icon" /></el-icon>
          <h3>{{ step.title }}</h3>
          <p>{{ step.desc }}</p>
          <el-button text type="primary" @click="router.push(step.route)">
            前往 →
          </el-button>
        </div>
      </div>
    </div>

    <!-- ═══════════════ 已认证用户：仪表盘内容 ═══════════════ -->
    <template v-if="!showWelcome">
      <!-- ═══════════════ ISK 英雄横幅 ═══════════════ -->
      <div class="hero-banner">
        <!-- 骨架屏 -->
        <template v-if="loadingOverview && !overviewData">
          <div class="data-card-total">
            <el-skeleton animated>
              <template #template>
                <el-skeleton-item
                  variant="text"
                  style="width: 30%; margin: 0 auto 8px"
                />
                <el-skeleton-item
                  variant="text"
                  style="width: 60%; margin: 0 auto; height: 48px"
                />
              </template>
            </el-skeleton>
          </div>
        </template>

        <!-- 错误状态 -->
        <template v-else-if="overviewError && !overviewData">
          <div class="section-empty">
            <el-empty
              description="概览数据加载失败，请刷新重试"
              :image-size="80"
            />
          </div>
        </template>

        <!-- 真实内容 -->
        <template v-else>
          <div class="data-card-total">
            <div class="total-label">总资产估值</div>
            <div class="total-value">
              {{ formatNumber(outputTotalValue) }} ISK
            </div>
            <div class="total-change" v-if="totalChange.hasChange">
              <span
                :class="
                  totalChange.diff >= 0 ? 'change-positive' : 'change-negative'
                "
              >
                {{ totalChange.diff >= 0 ? '↑' : '↓' }}
                {{ formatChange(totalChange) }}
              </span>
              <span class="period-label">
                vs
                {{
                  selectedTimeRange === '7d' ? '7天前' : '30天前'
                }}
              </span>
            </div>
            <div class="time-toggle">
              <el-button
                :type="selectedTimeRange === '7d' ? 'primary' : 'default'"
                size="small"
                @click="selectedTimeRange = '7d'"
              >
                7天
              </el-button>
              <el-button
                :type="selectedTimeRange === '30d' ? 'primary' : 'default'"
                size="small"
                @click="selectedTimeRange = '30d'"
              >
                30天
              </el-button>
            </div>
          </div>
        </template>
      </div>

    </template>

    <!-- ═══════════════ 始终可见：四列仪表盘网格 ═══════════════ -->
    <div class="dashboard-grid">
      <!-- 列 1: 正在运行的任务 -->
      <div class="dashboard-column">
        <div class="section-card">
          <div class="section-header">
            <span class="section-title-with-icon">🔧 正在运行的任务</span>
            <span
              v-if="sortedRunningJobs.length > 0"
              class="count-badge"
            >
              {{ sortedRunningJobs.length }}
            </span>
          </div>
          <div
            class="scrollable-job-list"
            ref="jobListRef"
            @scroll="onJobListScroll"
          >
            <!-- 任务卡片 -->
            <div
              v-if="visibleJobs.length > 0"
              class="job-card-list"
            >
              <div
                v-for="job in visibleJobs"
                :key="`${job.product_type_id}-${job.start_date}`"
                class="job-card compact"
              >
                <div class="job-card-header">
                  <img
                    v-if="job.installer_id"
                    :src="`https://imageserver.eveonline.com/Character/${job.installer_id}_64.jpg`"
                    class="installer-avatar-sm"
                    width="24"
                    height="24"
                    @error="
                      (e: Event) => {
                        ;(e.target as HTMLImageElement).style.display = 'none'
                      }
                    "
                  />
                  <span class="installer-name">{{ job.installer_name }}</span>
                  <el-tag
                    :type="
                      job.activity_type === '制造' ? 'primary' : 'warning'
                    "
                    size="small"
                  >
                    {{ job.activity_type }}
                  </el-tag>
                </div>
                <div class="job-card-body">
                  <img
                    :src="`https://imageserver.eveonline.com/types/${job.product_type_id}/icon`"
                    class="item-icon-sm"
                    @error="
                      (e: Event) => {
                        ;(e.target as HTMLImageElement).style.display = 'none'
                      }
                    "
                  />
                  <div class="job-info">
                    <div class="product-name">
                      {{ job.product_name_zh }}
                    </div>
                    <div class="job-progress">
                      <el-progress
                        :percentage="job.progress_percent"
                        :color="getProgressColor(job.progress_percent)"
                        :stroke-width="6"
                      />
                    </div>
                    <div class="job-meta">
                      <span>
                        {{ job.runs.toLocaleString('zh-CN') }}×{{
                          job.product_quantity_per_run.toLocaleString(
                            'zh-CN',
                          )
                        }}
                      </span>
                      <span class="job-value">
                        {{ formatNumber(job.value) }} ISK
                      </span>
                      <span class="job-time">
                        {{ formatRemainingTime(job.end_date) }}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
              <div v-if="hasMoreJobs" class="load-more-hint">滚动加载更多...</div>
            </div>

            <!-- 骨架屏 -->
            <div v-else-if="loadingJobs" class="job-card-list">
              <div v-for="i in 4" :key="i" class="job-card compact skeleton-card">
                <el-skeleton animated :rows="3" />
              </div>
            </div>

            <!-- 错误状态 -->
            <div v-else-if="jobsError" class="section-empty">
              <el-empty
                description="任务数据加载失败"
                :image-size="60"
              />
            </div>

            <!-- 空状态 -->
            <div v-else-if="!loadingJobs" class="section-empty">
              <el-empty description="暂无运行中任务" :image-size="60" />
            </div>
          </div>
        </div>
      </div>

      <!-- 列 2: 最新公告 -->
      <div class="dashboard-column">
        <div class="section-card" v-if="announcements.length > 0">
          <div class="section-header">
            <span class="section-title-with-icon">📢 最新公告</span>
          </div>
          <div class="announcement-list">
            <div
              v-for="item in announcements"
              :key="item.filename"
              class="announcement-item"
              @click="router.push('/announcements')"
              role="link"
              tabindex="0"
            >
              <div class="announcement-title">{{ item.title }}</div>
              <div class="announcement-date">{{ item.published_at }}</div>
              <div class="announcement-summary">
                {{ (item.summary || stripMarkdown(item.content).slice(0, 100) || '').slice(0, 100) }}
              </div>
            </div>
          </div>
        </div>
        <div v-else class="section-card">
          <div class="section-header">
            <span class="section-title-with-icon">📢 最新公告</span>
          </div>
          <el-empty description="暂无公告" :image-size="60" />
        </div>
      </div>

      <!-- 列 3: 运营状态 -->
      <div class="dashboard-column">
        <div class="section-card">
          <div class="section-header">
            <span class="section-title-with-icon">📊 运营状态</span>
          </div>

          <div v-if="opsStats" class="ops-grid">
            <div class="ops-item">
              <span class="ops-value">{{ opsStats.total_users }}</span>
              <span class="ops-label">注册用户</span>
            </div>
            <div class="ops-item">
              <span class="ops-value">{{ opsStats.total_vips }}</span>
              <span class="ops-label">VIP 会员</span>
            </div>
            <div class="ops-item">
              <span class="ops-value">{{ opsStats.total_plans }}</span>
              <span class="ops-label">工业计划</span>
            </div>
            <div class="ops-item">
              <span class="ops-value">{{
                formatCompactNumber(opsStats.total_asset_value)
              }}</span>
              <span class="ops-label">总资产估值</span>
            </div>
            <div class="ops-item">
              <span class="ops-value">{{
                formatCompactNumber(opsStats.total_running_value)
              }}</span>
              <span class="ops-label">运行中价值</span>
            </div>
          </div>

          <div v-else-if="loadingOps" class="ops-loading">
            <el-skeleton animated :rows="3" />
          </div>

          <div v-else-if="opsError" class="section-empty">
            <el-empty description="加载失败" :image-size="60" />
          </div>

          <div v-else class="section-empty">
            <el-empty description="暂无数据" :image-size="60" />
          </div>
        </div>
      </div>

      <!-- 列 4: 系数监控 -->
      <div class="dashboard-column">
        <CoefficientMonitor />
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ═══════════════ 根容器 ═══════════════ */
.dashboard-root {
  display: flex;
  flex-direction: column;
  height: 100vh;
  box-sizing: border-box;
  padding: 24px;
  background: var(--k-color-surface-soft);
}

/* ═══════════════ 页面标题 ═══════════════ */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
  flex-wrap: wrap;
  gap: 12px;
}

.page-header-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.page-header-center {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: var(--k-radius-md);
  background: var(--k-color-surface-soft);
  font-size: 13px;
}

.page-title {
  margin: 0;
  font-size: 28px;
  font-weight: 700;
  color: var(--k-color-text);
  letter-spacing: 0.02em;
}

.page-subtitle {
  margin: 0;
  font-size: 14px;
  color: var(--k-color-text-secondary);
}

/* ═══════════════ 英雄横幅 ═══════════════ */
.hero-banner {
  border-radius: var(--k-radius-lg);
  padding: 28px 24px 20px;
  margin-bottom: 0;
  background:
    radial-gradient(
      circle at 20% 10%,
      color-mix(in srgb, var(--k-color-primary) 12%, transparent),
      transparent 40%
    ),
    radial-gradient(
      circle at 85% 20%,
      color-mix(in srgb, var(--k-color-primary) 6%, transparent),
      transparent 44%
    ),
    var(--k-color-surface);
  border: 1px solid var(--k-color-border);
  position: relative;
}

:root[data-theme='dark'] .hero-banner,
[data-theme='dark'] .hero-banner {
  /* dark-mode styles now handled by --k-color-* variables automatically */
}

.data-card-total {
  text-align: center;
  padding: 16px 0 24px;
}

.total-label {
  font-size: 14px;
  color: var(--k-color-text-secondary);
  margin-bottom: 8px;
}

.total-value {
  font-size: 48px;
  font-weight: 800;
  color: var(--k-color-text);
  line-height: 1.2;
  letter-spacing: 0.02em;
  font-variant-numeric: tabular-nums;
}

.total-change {
  margin-top: 8px;
  font-size: 16px;
  font-weight: 600;
}

.change-positive {
  color: #22c55e;
}

.change-negative {
  color: #f87171;
}

.period-label {
  font-size: 13px;
  font-weight: 400;
  color: var(--k-color-text-secondary);
  margin-left: 4px;
}

.time-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 16px;
}

/* TQ 服务器状态 */
.server-status {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0 0 4px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-online {
  background: #22c55e;
  box-shadow: 0 0 6px rgba(34, 197, 94, 0.5);
}

.status-offline {
  background: #f87171;
  box-shadow: 0 0 6px rgba(248, 113, 113, 0.5);
}

.status-unknown {
  background: #909399;
  box-shadow: 0 0 6px rgba(144, 147, 153, 0.5);
}

.status-text {
  font-size: 12px;
  color: var(--k-color-text-secondary);
}

/* ═══════════════ 四列仪表盘网格 ═══════════════ */
.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  margin-top: 16px;
}

.dashboard-column {
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.scrollable-job-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
}

.scrollable-job-list::-webkit-scrollbar {
  width: 4px;
}

.scrollable-job-list::-webkit-scrollbar-thumb {
  background: var(--k-color-border);
  border-radius: 2px;
}

.load-more-hint {
  text-align: center;
  padding: 12px;
  color: var(--k-color-text-secondary);
  font-size: 13px;
}

/* ═══════════════ 区块卡片 ═══════════════ */
.section-card {
  background: var(--k-color-surface);
  border-radius: var(--k-radius-lg);
  border: 1px solid var(--k-color-border);
  box-shadow: var(--k-shadow-sm);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--k-color-border);
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--k-color-text);
}

.section-icon {
  font-size: 18px;
}

.section-title-with-icon {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--k-color-text);
}

.count-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 22px;
  padding: 0 6px;
  border-radius: 11px;
  font-size: 12px;
  font-weight: 600;
  background: var(--k-color-primary);
  color: #fff;
}

.section-empty {
  padding: 48px 20px;
  display: flex;
  justify-content: center;
}

/* ═══════════════ 运行中任务卡片 (紧凑版) ═══════════════ */
.job-card-list {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.job-card.compact {
  background: var(--k-color-surface-soft);
  border-radius: var(--k-radius-md);
  padding: 10px 12px;
  border: 1px solid var(--k-color-border);
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease;
}

.job-card.compact:hover {
  transform: translateY(-2px);
  box-shadow: var(--k-shadow-md);
}

.job-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.installer-avatar-sm {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: 2px solid var(--k-color-primary);
  object-fit: cover;
  flex-shrink: 0;
}

.installer-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--k-color-text);
  flex: 1;
  margin-left: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.job-card-body {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.item-icon-sm {
  width: 32px;
  height: 32px;
  border-radius: 4px;
  flex-shrink: 0;
}

.job-info {
  flex: 1;
  min-width: 0;
}

.product-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--k-color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-bottom: 6px;
}

.job-progress {
  margin-bottom: 6px;
}

.job-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 12px;
  color: var(--k-color-text-secondary);
}

.job-meta .job-value {
  color: #67c23a;
  font-weight: 600;
}

.job-meta .job-time {
  color: var(--k-color-text-secondary);
}

/* ═══════════════ 公告预览 ═══════════════ */
.announcement-list {
  padding: 8px 0;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.announcement-item {
  padding: 12px 20px;
  border-bottom: 1px solid var(--k-color-border-subtle);
  transition: background 0.15s ease;
}

.announcement-item:last-child {
  border-bottom: none;
}

.announcement-item:hover {
  background: var(--k-color-surface-soft);
  cursor: pointer;
}

.announcement-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--k-color-text);
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.announcement-date {
  font-size: 12px;
  color: var(--k-color-text-secondary);
  margin-bottom: 4px;
}

.announcement-summary {
  font-size: 12px;
  color: var(--k-color-text-secondary);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ═══════════════ 运营统计 ═══════════════ */
.ops-grid {
  padding: 16px 20px;
  display: grid;
  grid-template-columns: 1fr;
  gap: 14px;
}

.ops-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: var(--k-color-surface-soft);
  border-radius: var(--k-radius-md);
  border-left: 3px solid var(--k-color-primary);
}

.ops-item:nth-child(2) {
  border-left-color: #e6a23c;
}

.ops-item:nth-child(3) {
  border-left-color: #67c23a;
}

.ops-item:nth-child(4) {
  border-left-color: #409eff;
}

.ops-item:nth-child(5) {
  border-left-color: #f56c6c;
}

.ops-value {
  font-size: 18px;
  font-weight: 700;
  color: var(--k-color-text);
  font-variant-numeric: tabular-nums;
}

.ops-label {
  font-size: 12px;
  color: var(--k-color-text-secondary);
}

.ops-loading {
  padding: 16px 20px;
}

/* ═══════════════ 快捷操作按钮 ═══════════════ */
.header-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

/* ═══════════════ 未认证欢迎页 ═══════════════ */
.welcome-section {
  min-height: 60vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 32px;
}

.welcome-card {
  text-align: center;
  padding: 48px 40px;
  background: var(--k-color-surface);
  border-radius: var(--k-radius-lg);
  border: 1px solid var(--k-color-border);
  box-shadow: var(--k-shadow-md);
  max-width: 520px;
  width: 100%;
}

.welcome-card h2 {
  margin: 0 0 12px;
  font-size: 24px;
  font-weight: 700;
  color: var(--k-color-text);
}

.welcome-card p {
  margin: 0 0 24px;
  font-size: 15px;
  color: var(--k-color-text-secondary);
  line-height: 1.6;
}

.guide-cards {
  display: flex;
  gap: 20px;
  max-width: 760px;
  width: 100%;
}

.guide-card {
  flex: 1;
  text-align: center;
  padding: 28px 20px;
  background: var(--k-color-surface);
  border-radius: var(--k-radius-lg);
  border: 1px solid var(--k-color-border);
  box-shadow: var(--k-shadow-sm);
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease;
}

.guide-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--k-shadow-md);
}

.guide-card .el-icon {
  color: var(--k-color-primary);
  margin-bottom: 12px;
}

.guide-card h3 {
  margin: 0 0 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--k-color-text);
}

.guide-card p {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--k-color-text-secondary);
  line-height: 1.5;
}

/* ═══════════════ 骨架屏 ═══════════════ */
.skeleton-card {
  min-height: 100px;
}

/* ═══════════════ 响应式 ═══════════════ */
@media (max-width: 768px) {
  .dashboard-root {
    padding: 12px;
    height: auto;
    min-height: 100vh;
  }

  .page-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .page-title {
    font-size: 22px;
  }

  .total-value {
    font-size: 32px;
  }

  .hero-banner {
    padding: 16px 12px;
  }

  .dashboard-grid {
    grid-template-columns: 1fr;
  }

  .guide-cards {
    flex-direction: column;
  }

  .welcome-card {
    padding: 32px 24px;
  }

  .header-actions {
    flex-direction: row;
    flex-wrap: wrap;
  }

  .header-actions .el-button {
    flex: 1;
  }
}

@media (max-width: 1024px) {
  .dashboard-grid {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
