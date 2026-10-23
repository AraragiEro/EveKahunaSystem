<script setup lang="ts">
import KCard from '@/components/k/KCard.vue'
import KEmpty from '@/components/k/KEmpty.vue'
import KStat from '@/components/k/KStat.vue'
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useTransition } from '@vueuse/core'
import {
  Plus,
  Search,
  FolderOpened,
  UserFilled,
  Cpu,
  TrendCharts,
  Tools,
  Bell,
  DataLine,
} from '@element-plus/icons-vue'
import { http } from '@/http'
import { handleApiResponse } from '@/utils/apiResponse'
import { calculateTotalAssets, getNumericValue } from '@/utils/totalAssets'
import { useAuthStore } from '@/stores/auth'
import { useAnnouncements } from '@/composables/useAnnouncements'
import CoefficientMonitor from '@/components/dashboard/CoefficientMonitor.vue'
import AssetComposition from '@/components/dashboard/AssetComposition.vue'
import GridShell from '@/components/layout/GridShell.vue'

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

/** 已完成任务默认折叠，避免首屏被「已完成 100%」占满 */
const finishedExpanded = ref(false)

// ──────────────────── 计算属性 ────────────────────

const hasCharacters = computed(() => characterSummaryList.value.length > 0)

const showWelcome = computed(
  () => !loadingJobs.value && !jobsError.value && !hasCharacters.value,
)

const totalValueSource = computed(() => {
  if (!overviewData.value) return 0
  // 5 项统一口径，见 utils/totalAssets
  return calculateTotalAssets(overviewData.value)
})

const historyTotalValue = computed(() => {
  const history =
    selectedTimeRange.value === '7d'
      ? lastNote7d.value
      : lastNote30d.value
  if (!history) return null
  return calculateTotalAssets(history)
})

const totalChange = computed(() =>
  calculateChange(totalValueSource.value, historyTotalValue.value),
)

const outputTotalValue = useTransition(totalValueSource, {
  duration: 2000,
  transition: (t: number) => t * (2 - t),
})

/** hero 右段：五段构成与总资产同源（calculateTotalAssets 的 5 项逐项展开） */
const compositionItems = computed<Array<{ key: string; label: string; value: number }>>(() => {
  const data = overviewData.value
  if (!data) return []
  return [
    { key: 'wallet', label: '钱包', value: getNumericValue(data.walletValue) },
    { key: 'order', label: '订单', value: getNumericValue(data.orderValue) },
    { key: 'running', label: '运行中', value: data.runningProcessValue ?? 0 },
    { key: 'marked', label: '标记资产', value: data.markedAssetValue ?? 0 },
    { key: 'unmarked', label: '非标记资产', value: data.unmarkedAssetValue ?? 0 },
  ]
})

const isJobDone = (job: RunningJobDetail): boolean =>
  (job.progress_percent ?? 0) >= 100 || new Date(job.end_date).getTime() <= Date.now()

// 按 end_date 升序排列，不做数量限制
const sortedRunningJobs = computed(() =>
  [...runningJobsList.value].sort(
    (a, b) => new Date(a.end_date).getTime() - new Date(b.end_date).getTime(),
  ),
)

/** 未完成（真正「进行中」）优先，已完成折叠在后 */
const unfinishedJobs = computed(() => sortedRunningJobs.value.filter((job) => !isJobDone(job)))

const finishedJobs = computed(() => sortedRunningJobs.value.filter(isJobDone))

const nextJob = computed(() => unfinishedJobs.value[0] ?? null)

const finishedValue = computed(() =>
  finishedJobs.value.reduce((sum, job) => sum + (job.value || 0), 0),
)

const finishedPreview = computed(() => (finishedExpanded.value ? finishedJobs.value : finishedJobs.value.slice(0, 3)))

const todoTitle = computed(() => {
  if (unfinishedJobs.value.length > 0) {
    return `${unfinishedJobs.value.length} 项任务进行中`
  }
  if (finishedJobs.value.length > 0) {
    return `${finishedJobs.value.length} 项已产出，等待收成`
  }
  return '暂无进行中的任务'
})

const todoMeta = computed(() => {
  const parts: string[] = []
  if (nextJob.value) {
    parts.push(`下一项：${nextJob.value.product_name_zh} · 剩余 ${formatRemainingTime(nextJob.value.end_date)}`)
  }
  if (finishedJobs.value.length > 0) {
    parts.push(`待收成 ${finishedJobs.value.length} 项 · ${formatCompactNumber(finishedValue.value)} ISK`)
  }
  if (parts.length === 0) {
    return '新建工业计划或启动生产后，这里会显示待办'
  }
  return parts.join(' · ')
})

const todoActionText = computed(() =>
  nextJob.value ? '查看生产计划' : finishedJobs.value.length > 0 ? '去收取' : '新建工业计划',
)

const goTodo = () => {
  router.push('/industry/industryPlan')
}

const opsItems = computed(() => {
  const stats = opsStats.value
  if (!stats) return []
  return [
    { key: 'users', label: '注册用户', value: stats.total_users.toLocaleString('zh-CN') },
    { key: 'vips', label: 'VIP 会员', value: stats.total_vips.toLocaleString('zh-CN') },
    { key: 'plans', label: '工业计划', value: stats.total_plans.toLocaleString('zh-CN') },
    { key: 'asset', label: '总资产价值', value: formatCompactNumber(stats.total_asset_value) },
    { key: 'running', label: '运行中价值', value: formatCompactNumber(stats.total_running_value) },
  ]
})

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
        <!-- 状态点只是配色提示，语义在紧邻的文字里；别让读屏重复播报一个没有含义的 span -->
        <span class="status-dot" aria-hidden="true" :class="{'status-online': serverStatus === 'online', 'status-offline': serverStatus === 'offline', 'status-unknown': serverStatus === 'unknown'}"></span>
        <span class="status-text">{{ serverStatus === 'online' ? 'TQ 在线' : serverStatus === 'offline' ? 'TQ 维护中' : 'TQ 状态未知' }}</span>
      </div>
      <div class="header-actions">
        <el-button @click="router.push('/industry/industryPlan')">
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
      <!-- ═══════════════ 首屏 hero：左「总资产 + 趋势」/ 右「资产构成」 ═══════════════ -->
      <section class="hero">
        <div class="hero__main">
          <!-- 骨架屏 -->
          <template v-if="loadingOverview && !overviewData">
            <el-skeleton animated>
              <template #template>
                <el-skeleton-item variant="text" style="width: 30%; margin-bottom: 12px" />
                <el-skeleton-item variant="text" style="width: 80%; height: 56px" />
              </template>
            </el-skeleton>
          </template>

          <!-- 错误状态 -->
          <template v-else-if="overviewError && !overviewData">
            <KEmpty why="概览数据加载失败，请刷新重试" size="sm" />
          </template>

          <!-- 真实内容 -->
          <template v-else>
            <div class="hero__label">总资产估值</div>
            <div class="hero__value" :title="`${formatNumber(totalValueSource)} ISK`">
              {{ formatNumber(outputTotalValue) }}<span class="hero__unit">ISK</span>
            </div>
            <!-- 趋势与 7天/30天 分段同一行，不做两端对齐 -->
            <div class="hero__trend">
              <template v-if="totalChange.hasChange">
                <span
                  class="hero__delta"
                  :class="totalChange.diff >= 0 ? 'is-up' : 'is-down'"
                >
                  {{ totalChange.diff >= 0 ? '↑' : '↓' }}
                  {{ formatChange(totalChange) }}
                </span>
                <span class="hero__period">
                  vs {{ selectedTimeRange === '7d' ? '7天前' : '30天前' }}
                </span>
              </template>
              <div class="hero__range" role="group" aria-label="趋势对比周期">
                <button
                  type="button"
                  class="hero__range-btn"
                  :class="{ 'is-active': selectedTimeRange === '7d' }"
                  :aria-pressed="selectedTimeRange === '7d'"
                  @click="selectedTimeRange = '7d'"
                >
                  7天
                </button>
                <button
                  type="button"
                  class="hero__range-btn"
                  :class="{ 'is-active': selectedTimeRange === '30d' }"
                  :aria-pressed="selectedTimeRange === '30d'"
                  @click="selectedTimeRange = '30d'"
                >
                  30天
                </button>
              </div>
            </div>
          </template>
        </div>

        <AssetComposition
          v-if="overviewData"
          class="hero__composition"
          :items="compositionItems"
          :total="totalValueSource"
        />
        <div v-else-if="loadingOverview" class="hero__composition hero__composition--loading">
          <el-skeleton animated :rows="3" />
        </div>
      </section>

      <!-- ═══════════════ 运营状态：一行紧凑小方块（数字统一 ink 色，量级 ≤28px） ═══════════════ -->
      <KCard class="ops-bar-card" padding="sm">
        <div class="ops-bar">
          <div class="ops-bar__title">
            <el-icon class="section-icon"><DataLine /></el-icon>
            <span>运营状态</span>
          </div>
          <div v-if="opsStats" class="ops-grid">
            <div v-for="item in opsItems" :key="item.key" class="ops-cell">
              <KStat :label="item.label" :value="item.value" size="md" />
            </div>
          </div>
          <div v-else-if="loadingOps" class="ops-loading">
            <el-skeleton animated :rows="1" />
          </div>
          <div v-else-if="opsError" class="ops-hint">加载失败</div>
          <div v-else class="ops-hint">暂无数据</div>
        </div>
      </KCard>

      <!-- ═══════════════ 三列仪表盘网格（任务 5 / 公告 4 / 系数 3） ═══════════════ -->
      <GridShell class="dashboard-grid" gap="16px">
        <!-- 列 1: 进行中的任务（待办条 + 未完成优先） -->
        <div class="dashboard-column k-col-5">
          <KCard class="task-card" padding="none">
            <template #header>
              <div class="task-card__title">
                <el-icon class="section-icon"><Tools /></el-icon>
                <span>进行中的任务</span>
                <span
                  class="count-badge"
                  :class="{ 'is-muted': unfinishedJobs.length === 0 }"
                  :title="`未完成 ${unfinishedJobs.length} 项`"
                >
                  {{ unfinishedJobs.length }}
                </span>
              </div>
            </template>

            <!-- 首行待办：真实状态 + 唯一主操作 -->
            <div class="todo-strip">
              <div class="todo-strip__text">
                <span class="todo-strip__kicker">下一步</span>
                <p class="todo-strip__title">{{ todoTitle }}</p>
                <p class="todo-strip__meta">{{ todoMeta }}</p>
              </div>
              <el-button type="primary" size="small" @click="goTodo">
                {{ todoActionText }}
              </el-button>
            </div>

            <div class="task-list">
              <!-- 未完成任务 -->
              <div
                v-for="job in unfinishedJobs"
                :key="`${job.product_type_id}-${job.start_date}`"
                class="task-row"
              >
                <div class="task-row__head">
                  <img
                    v-if="job.installer_id"
                    :src="`https://imageserver.eveonline.com/Character/${job.installer_id}_64.jpg`"
                    class="task-avatar"
                    width="20"
                    height="20"
                    alt=""
                    @error="(e: Event) => { (e.target as HTMLImageElement).style.display = 'none' }"
                  />
                  <span class="task-row__installer">{{ job.installer_name }}</span>
                  <span class="task-row__activity">{{ job.activity_type }}</span>
                  <span class="task-row__value">{{ formatCompactNumber(job.value) }} ISK</span>
                </div>
                <div class="task-row__body">
                  <img
                    :src="`https://imageserver.eveonline.com/types/${job.product_type_id}/icon`"
                    class="task-icon"
                    alt=""
                    @error="(e: Event) => { (e.target as HTMLImageElement).style.display = 'none' }"
                  />
                  <div class="task-row__info">
                    <div class="task-row__name">{{ job.product_name_zh }}</div>
                    <div class="task-progress">
                      <span
                        class="task-progress__fill"
                        :style="{ width: `${Math.max(2, Math.min(100, job.progress_percent))}%` }"
                      />
                    </div>
                    <div class="task-row__meta">
                      <span>{{ job.runs.toLocaleString('zh-CN') }}×{{ job.product_quantity_per_run.toLocaleString('zh-CN') }}</span>
                      <span>剩余 {{ formatRemainingTime(job.end_date) }}</span>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 已完成任务：默认折到 3 条，状态用 chip 而不是再画一遍 100% -->
              <template v-if="finishedPreview.length > 0">
                <div
                  v-for="job in finishedPreview"
                  :key="`done-${job.product_type_id}-${job.start_date}`"
                  class="task-row is-done"
                >
                  <div class="task-row__head">
                    <img
                      v-if="job.installer_id"
                      :src="`https://imageserver.eveonline.com/Character/${job.installer_id}_64.jpg`"
                      class="task-avatar"
                      width="20"
                      height="20"
                      alt=""
                      @error="(e: Event) => { (e.target as HTMLImageElement).style.display = 'none' }"
                    />
                    <span class="task-row__installer">{{ job.installer_name }}</span>
                    <span class="task-row__activity">{{ job.activity_type }}</span>
                    <span class="task-row__value">{{ formatCompactNumber(job.value) }} ISK</span>
                  </div>
                  <div class="task-row__body">
                    <img
                      :src="`https://imageserver.eveonline.com/types/${job.product_type_id}/icon`"
                      class="task-icon"
                      alt=""
                      @error="(e: Event) => { (e.target as HTMLImageElement).style.display = 'none' }"
                    />
                    <div class="task-row__info">
                      <div class="task-row__name">{{ job.product_name_zh }}</div>
                      <div class="task-row__meta">
                        <span>{{ job.runs.toLocaleString('zh-CN') }}×{{ job.product_quantity_per_run.toLocaleString('zh-CN') }}</span>
                        <span class="task-row__done-chip">已产出</span>
                      </div>
                    </div>
                  </div>
                </div>
                <button
                  v-if="finishedJobs.length > 3"
                  type="button"
                  class="task-fold"
                  @click="finishedExpanded = !finishedExpanded"
                >
                  {{ finishedExpanded ? '收起已完成' : `展开全部已完成（${finishedJobs.length} 项）` }}
                </button>
              </template>

              <!-- 骨架屏 -->
              <template v-if="loadingJobs && sortedRunningJobs.length === 0">
                <div v-for="i in 4" :key="i" class="task-row is-skeleton">
                  <el-skeleton animated :rows="2" />
                </div>
              </template>

              <!-- 错误状态 -->
              <div v-else-if="jobsError" class="section-empty">
                <KEmpty why="任务数据加载失败" size="sm" />
              </div>

              <!-- 空状态 -->
              <div v-else-if="!loadingJobs && sortedRunningJobs.length === 0" class="section-empty">
                <KEmpty why="暂无运行中任务" size="sm" />
              </div>
            </div>
          </KCard>
        </div>

        <!-- 列 2: 最新公告 -->
        <div class="dashboard-column k-col-4">
          <KCard class="announcement-card" padding="none">
            <template #header>
              <div class="task-card__title">
                <el-icon class="section-icon"><Bell /></el-icon>
                <span>最新公告</span>
              </div>
            </template>
            <template #actions>
              <el-button text size="small" @click="router.push('/announcements')">
                查看全部
              </el-button>
            </template>
            <div class="announcement-list" v-if="announcements.length > 0">
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
            <div v-else class="section-empty">
              <KEmpty why="暂无公告" size="sm" />
            </div>
          </KCard>
        </div>

        <!-- 列 3: 系数监控 -->
        <div class="dashboard-column k-col-3">
          <CoefficientMonitor />
        </div>
      </GridShell>
    </template>
  </div>
</template>

<style scoped>
/* ═══════════════ 根容器 ═══════════════ */
.dashboard-root {
  display: flex;
  flex-direction: column;
  /* 外层 .main-scroll 已给确定高度；100vh 会多出顶栏/页脚的高度，
     既导致页面纵向滚动，也让底部卡片被切。 */
  height: 100%;
  box-sizing: border-box;
  padding: var(--k-space-5, 24px);
  background: var(--k-color-surface-soft);
}

/* ═══════════════ 页面标题 ═══════════════ */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--k-space-4);
  flex-wrap: wrap;
  gap: var(--k-space-3);
}

.page-header-left {
  display: flex;
  flex-direction: column;
  gap: var(--k-space-1);
}

.page-header-center {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: var(--k-radius-pill);
  background: var(--k-color-surface);
  border: 1px solid var(--k-color-border-subtle);
  font-size: var(--k-font-xs);
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
  font-size: var(--k-font-md);
  color: var(--k-color-text-secondary);
}

/* ═══════════════ 首屏 hero：横向两段 ═══════════════ */
.hero {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 0.9fr);
  align-items: center;
  gap: var(--k-space-5);
  border-radius: var(--k-radius-lg);
  padding: var(--k-space-5);
  margin-bottom: var(--k-space-4);
  background:
    radial-gradient(
      circle at 18% 10%,
      color-mix(in srgb, var(--k-color-primary) 12%, transparent),
      transparent 42%
    ),
    radial-gradient(
      circle at 88% 18%,
      color-mix(in srgb, var(--k-color-primary) 6%, transparent),
      transparent 46%
    ),
    var(--k-color-surface);
  border: 1px solid var(--k-color-border);
  min-width: 0;
}

.hero__main {
  display: flex;
  flex-direction: column;
  gap: var(--k-space-2);
  min-width: 0;
}

.hero__label {
  font-size: var(--k-font-sm);
  color: var(--k-color-text-secondary);
}

.hero__value {
  /* 全页唯一的 40px+ 量级（--k-font-hero = 40→68） */
  font-size: var(--k-font-hero);
  font-weight: 800;
  line-height: 1.08;
  letter-spacing: -0.01em;
  color: var(--k-color-text);
  font-variant-numeric: tabular-nums;
  display: flex;
  align-items: baseline;
  gap: var(--k-space-2);
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.hero__unit {
  font-size: var(--k-font-sm);
  font-weight: 600;
  color: var(--k-color-text-secondary);
  letter-spacing: 0.04em;
}

.hero__trend {
  display: flex;
  align-items: center;
  gap: var(--k-space-3);
  flex-wrap: wrap;
  min-width: 0;
}

.hero__delta {
  font-size: var(--k-font-md);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.hero__delta.is-up {
  color: var(--k-color-success);
}

.hero__delta.is-down {
  color: var(--k-color-danger);
}

.hero__period {
  font-size: var(--k-font-xs);
  color: var(--k-color-text-secondary);
}

/* 分段控件：选中态用主色浅底 + 主色描边，不再是实心按钮（页内只留 1 个实心主按钮） */
.hero__range {
  display: inline-flex;
  align-items: center;
  padding: 2px;
  gap: 2px;
  border-radius: var(--k-radius-pill);
  background: var(--k-color-surface-soft);
  border: 1px solid var(--k-color-border-subtle);
}

.hero__range-btn {
  appearance: none;
  border: 0;
  cursor: pointer;
  padding: 2px 12px;
  border-radius: var(--k-radius-pill);
  background: transparent;
  color: var(--k-color-text-secondary);
  font-size: var(--k-font-xs);
  font-weight: 600;
  line-height: 1.6;
  transition:
    background var(--k-dur-1) var(--k-ease),
    color var(--k-dur-1) var(--k-ease);
}

.hero__range-btn:hover {
  color: var(--k-color-text);
}

.hero__range-btn.is-active {
  background: var(--k-color-primary-soft);
  color: var(--k-color-primary);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--k-color-primary) 40%, transparent);
}

.hero__composition {
  min-width: 0;
}

.hero__composition--loading {
  padding: var(--k-space-3);
}

/* ═══════════════ 仪表盘网格 ═══════════════ */
.dashboard-grid {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.dashboard-column {
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

/* 运营条：宽屏一行 5 格，≤1199 收成 3 列，≤767 收成 2 列 */
@media (max-width: 1199px) {
  .ops-bar {
    flex-direction: column;
    align-items: stretch;
    gap: var(--k-space-2);
  }

  .ops-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 767px) {
  .ops-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

/* ═══════════════ 卡片标题（KCard header 插槽） ═══════════════ */
.task-card,
.announcement-card {
  min-height: 0;
  flex: 1 1 auto;
}

/* KCard 的 body 不是 flex 容器；这里补上，任务/公告列表的 flex:1 + overflow:auto 才会生效 */
.task-card :deep(.k-card__body),
.announcement-card :deep(.k-card__body) {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.task-card__title {
  display: flex;
  align-items: center;
  gap: var(--k-space-2);
  min-width: 0;
  font-size: var(--k-font-md);
  font-weight: 600;
  color: var(--k-color-text);
}

.section-icon {
  font-size: 16px;
  color: var(--k-color-primary);
  flex: none;
}

.count-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 20px;
  padding: 0 6px;
  border-radius: var(--k-radius-pill);
  font-size: var(--k-font-xs);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  background: var(--k-color-primary-soft);
  color: var(--k-color-primary);
}

.count-badge.is-muted {
  background: var(--k-color-surface-soft);
  color: var(--k-color-text-tertiary);
}

/* ═══════════════ 待办条（首行） ═══════════════ */
.todo-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--k-space-3);
  padding: var(--k-space-3) var(--k-space-4);
  margin: var(--k-space-3) var(--k-space-3) 0;
  border-radius: var(--k-radius-md);
  background: var(--k-color-surface-soft);
  border: 1px solid var(--k-color-border-subtle);
  border-left: 3px solid var(--k-color-primary);
}

.todo-strip__text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.todo-strip__kicker {
  font-size: var(--k-font-xs);
  color: var(--k-color-text-tertiary);
  letter-spacing: 0.08em;
}

.todo-strip__title {
  margin: 0;
  font-size: var(--k-font-md);
  font-weight: 700;
  color: var(--k-color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.todo-strip__meta {
  margin: 0;
  font-size: var(--k-font-xs);
  color: var(--k-color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ═══════════════ 任务列表 ═══════════════ */
.task-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: var(--k-space-3);
  display: flex;
  flex-direction: column;
  gap: var(--k-space-2);
}

.task-list::-webkit-scrollbar {
  width: 4px;
}

.task-list::-webkit-scrollbar-thumb {
  background: var(--k-color-border);
  border-radius: 2px;
}

.task-row {
  padding: var(--k-space-2) var(--k-space-3);
  border-radius: var(--k-radius-md);
  border: 1px solid var(--k-color-border-subtle);
  background: var(--k-color-surface);
  transition: border-color var(--k-dur-1) var(--k-ease);
}

.task-row:hover {
  border-color: var(--k-color-border);
}

.task-row.is-done {
  opacity: 0.72;
  background: var(--k-color-surface-soft);
}

.task-row.is-skeleton {
  opacity: 0.8;
}

.task-row__head {
  display: flex;
  align-items: center;
  gap: var(--k-space-2);
  min-width: 0;
  margin-bottom: 6px;
}

.task-avatar {
  width: 20px;
  height: 20px;
  border-radius: var(--k-radius-pill);
  object-fit: cover;
  flex: none;
  border: 1px solid var(--k-color-border-subtle);
}

.task-row__installer {
  font-size: var(--k-font-xs);
  font-weight: 600;
  color: var(--k-color-text-secondary);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-row__activity {
  flex: none;
  font-size: 11px;
  padding: 0 6px;
  border-radius: var(--k-radius-pill);
  background: var(--k-color-primary-soft);
  color: var(--k-color-primary);
  line-height: 1.6;
}

.task-row__value {
  margin-left: auto;
  flex: none;
  font-size: var(--k-font-xs);
  font-weight: 600;
  color: var(--k-color-text);
  font-variant-numeric: tabular-nums;
}

.task-row__body {
  display: flex;
  align-items: flex-start;
  gap: var(--k-space-2);
  min-width: 0;
}

.task-icon {
  width: 28px;
  height: 28px;
  border-radius: var(--k-radius-xs);
  flex: none;
}

.task-row__info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.task-row__name {
  font-size: var(--k-font-sm);
  font-weight: 600;
  color: var(--k-color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-progress {
  height: 5px;
  border-radius: var(--k-radius-pill);
  background: var(--k-color-surface-strong);
  overflow: hidden;
}

.task-progress__fill {
  display: block;
  height: 100%;
  border-radius: var(--k-radius-pill);
  background: var(--k-color-primary);
  transition: width var(--k-dur-2) var(--k-ease);
}

.task-row__meta {
  display: flex;
  align-items: center;
  gap: var(--k-space-3);
  font-size: 11px;
  color: var(--k-color-text-secondary);
  font-variant-numeric: tabular-nums;
}

.task-row__done-chip {
  margin-left: auto;
  padding: 0 6px;
  border-radius: var(--k-radius-pill);
  background: var(--k-color-success-soft);
  color: var(--k-color-success);
  font-size: 11px;
  font-weight: 600;
}

.task-fold {
  appearance: none;
  border: 0;
  cursor: pointer;
  margin-top: var(--k-space-1);
  padding: var(--k-space-2);
  border-radius: var(--k-radius-sm);
  background: transparent;
  color: var(--k-color-text-secondary);
  font-size: var(--k-font-xs);
  transition: background var(--k-dur-1) var(--k-ease);
}

.task-fold:hover {
  background: var(--k-color-surface-soft);
  color: var(--k-color-text);
}

.section-empty {
  padding: var(--k-space-6) var(--k-space-4);
  display: flex;
  justify-content: center;
}

/* ═══════════════ 公告预览 ═══════════════ */
.announcement-list {
  padding: var(--k-space-2) 0;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.announcement-item {
  padding: var(--k-space-3) var(--k-space-4);
  border-bottom: 1px solid var(--k-color-border-subtle);
  transition: background var(--k-dur-1) var(--k-ease);
}

.announcement-item:last-child {
  border-bottom: none;
}

.announcement-item:hover {
  background: var(--k-color-surface-soft);
  cursor: pointer;
}

.announcement-title {
  font-size: var(--k-font-md);
  font-weight: 600;
  color: var(--k-color-text);
  margin-bottom: var(--k-space-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.announcement-date {
  font-size: var(--k-font-xs);
  color: var(--k-color-text-secondary);
  margin-bottom: var(--k-space-1);
}

.announcement-summary {
  font-size: var(--k-font-xs);
  color: var(--k-color-text-secondary);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ═══════════════ 运营状态：一行紧凑小方块 ═══════════════ */
.ops-bar-card {
  flex: none;
  margin-bottom: var(--k-space-4);
}

.ops-bar {
  display: flex;
  align-items: center;
  gap: var(--k-space-4);
  min-width: 0;
}

.ops-bar__title {
  display: flex;
  align-items: center;
  gap: var(--k-space-2);
  flex: none;
  font-size: var(--k-font-md);
  font-weight: 600;
  color: var(--k-color-text);
}

.ops-grid {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: var(--k-space-2);
  min-width: 0;
}

.ops-cell {
  padding: var(--k-space-2) var(--k-space-3);
  border-radius: var(--k-radius-md);
  background: var(--k-color-surface-soft);
  border: 1px solid var(--k-color-border-subtle);
  min-width: 0;
}

/* 数字统一 ink 色，量级 24px（≤28；全页 40px+ 只留给 hero） */
.ops-grid :deep(.k-stat__value) {
  font-size: 24px;
  color: var(--k-color-text);
}

.ops-hint {
  flex: 1;
  font-size: var(--k-font-xs);
  color: var(--k-color-text-secondary);
}

.ops-loading {
  flex: 1;
  min-width: 0;
}

/* ═══════════════ 快捷操作按钮 ═══════════════ */
.header-actions {
  display: flex;
  gap: var(--k-space-2);
  flex-wrap: wrap;
}

/* ═══════════════ 未认证欢迎页 ═══════════════ */
.welcome-section {
  min-height: 60vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--k-space-6);
}

.welcome-card {
  text-align: center;
  padding: var(--k-space-7) var(--k-space-6);
  background: var(--k-color-surface);
  border-radius: var(--k-radius-lg);
  border: 1px solid var(--k-color-border);
  box-shadow: var(--k-shadow-md);
  max-width: 520px;
  width: 100%;
}

.welcome-card h2 {
  margin: 0 0 var(--k-space-3);
  font-size: 24px;
  font-weight: 700;
  color: var(--k-color-text);
}

.welcome-card p {
  margin: 0 0 var(--k-space-5);
  font-size: 15px;
  color: var(--k-color-text-secondary);
  line-height: 1.6;
}

.guide-cards {
  display: flex;
  gap: var(--k-space-5);
  max-width: 760px;
  width: 100%;
}

.guide-card {
  flex: 1;
  text-align: center;
  padding: var(--k-space-5) var(--k-space-4);
  background: var(--k-color-surface);
  border-radius: var(--k-radius-lg);
  border: 1px solid var(--k-color-border);
  box-shadow: var(--k-shadow-sm);
  transition:
    transform var(--k-dur-2) var(--k-ease),
    box-shadow var(--k-dur-2) var(--k-ease);
}

.guide-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--k-shadow-md);
}

.guide-card .el-icon {
  color: var(--k-color-primary);
  margin-bottom: var(--k-space-3);
}

.guide-card h3 {
  margin: 0 0 var(--k-space-2);
  font-size: 15px;
  font-weight: 600;
  color: var(--k-color-text);
}

.guide-card p {
  margin: 0 0 var(--k-space-3);
  font-size: var(--k-font-sm);
  color: var(--k-color-text-secondary);
  line-height: 1.5;
}

/* ═══════════════ 响应式 ═══════════════ */
@media (max-width: 991px) {
  .hero {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 768px) {
  .dashboard-root {
    padding: var(--k-space-3);
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

  .hero {
    padding: var(--k-space-4);
  }

  .hero__value {
    font-size: clamp(32px, 9vw, 44px);
  }

  .dashboard-grid {
    grid-template-columns: 1fr;
  }

  .guide-cards {
    flex-direction: column;
  }

  .welcome-card {
    padding: var(--k-space-5) var(--k-space-4);
  }

  .header-actions {
    flex-direction: row;
    flex-wrap: wrap;
  }

  .header-actions .el-button {
    flex: 1;
  }
}

/* ── P2-C ≤640：375 级窄屏的两处内容裁切 ─────────────────────────────
   1. .hero__value 在 768 档是 clamp(32px, 9vw, 44px)，375 下 33.75px，
      「154,722,402,002.17」实测被容器裁掉右侧 3 位数字（真的读不到数）。
      这里只再降一档字号，1280+ 仍走 token 原值。
   2. .header-actions 在 768 档给按钮 flex:1，三个按钮平分 295px 后
      「新建工业计划」被压成「新建工业计…」。改成按内容宽度、放不下就换行。 */
@media (max-width: 640px) {
  .hero__value {
    font-size: clamp(17px, 6vw, 26px);
  }

  .header-actions {
    width: 100%;
  }

  .header-actions .el-button {
    flex: 0 1 auto;
  }
}
</style>
