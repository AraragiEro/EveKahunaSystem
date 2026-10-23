<script setup lang="ts">
import KCard from '@/components/k/KCard.vue'
import KEmpty from '@/components/k/KEmpty.vue'
import KStat from '@/components/k/KStat.vue'
import KTable from '@/components/k/KTable.vue'
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Timer } from '@element-plus/icons-vue'
import { getTqStatus, getCharacters, testCharacterToken, getBuckets, getQueueDepth, getUsageLog } from '@/api/esiAdmin'
import type { CharacterEsiStatus, TqStatus, BucketStats, QueueDepth, UsageLogEntry } from '@/types/esiAdmin'

// ── Tab state ──
const activeTab = ref('characters')

// ── TQ server status ──
const tqStatus = ref<TqStatus>({
  status: 'unknown',
})

const statusText = computed(() => {
  const map: Record<string, string> = { online: '在线', offline: '离线', unknown: '未知' }
  return map[tqStatus.value.status] ?? '未知'
})

const alertType = computed(() => {
  const map: Record<string, string> = { online: 'success', offline: 'error', unknown: 'info' }
  return map[tqStatus.value.status] ?? 'info'
})

let tqTimer: ReturnType<typeof setInterval> | null = null

async function fetchTqStatus() {
  try {
    const data = await getTqStatus()
    tqStatus.value = data
  } catch {
    // keep current state on error
  }
}

// ── Characters ──
const characters = ref<CharacterEsiStatus[]>([])
const loading = ref(false)
const searchUserName = ref('')
const statusFilter = ref('all')

const statusOptions = [
  { label: '全部', value: 'all' },
  { label: '有效', value: 'valid' },
  { label: '即将过期', value: 'about_to_expire' },
  { label: '已过期', value: 'expired' },
  { label: '未知', value: 'unknown' },
]

const filteredCharacters = computed(() => {
  let result = characters.value

  if (searchUserName.value.trim()) {
    const term = searchUserName.value.trim().toLowerCase()
    result = result.filter(
      (c) =>
        (c.owner_user_name ?? '').toLowerCase().includes(term) ||
        (c.character_name ?? '').toLowerCase().includes(term),
    )
  }

  if (statusFilter.value !== 'all') {
    result = result.filter((c) => c.token_status === statusFilter.value)
  }

  return result
})

async function fetchCharacters(silent = false) {
  if (!silent) loading.value = true
  try {
    const data = await getCharacters()
    characters.value = data.items
  } catch (e: any) {
    if (!silent) ElMessage.error(e?.message || '获取角色状态失败')
  } finally {
    if (!silent) loading.value = false
  }
}

// ── Cooldown management ──
const cooldowns = ref<Record<number, number>>({})
let cooldownTimer: ReturnType<typeof setInterval> | null = null

function ensureCooldownTimer() {
  if (cooldownTimer) return
  cooldownTimer = setInterval(() => {
    let hasActive = false
    const keys = Object.keys(cooldowns.value)
    for (const key of keys) {
      const id = Number(key)
      if (cooldowns.value[id] > 0) {
        cooldowns.value[id]--
        hasActive = true
      }
    }
    if (!hasActive && cooldownTimer) {
      clearInterval(cooldownTimer)
      cooldownTimer = null
    }
  }, 1000)
}

async function handleTestToken(characterId: number) {
  if ((cooldowns.value[characterId] ?? 0) > 0) return

  cooldowns.value[characterId] = 30
  ensureCooldownTimer()

  try {
    const result = await testCharacterToken(characterId)
    if (result.success) {
      const latencyPart = result.latency_ms != null ? `延迟 ${result.latency_ms} ms` : ''
      ElMessage.success(latencyPart || '测试成功')
    } else {
      ElMessage.error(result.error || '测试失败')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '测试失败')
  }
}

// ── Buckets & Queue Depth ──
const queueDepth = ref<QueueDepth>({ backlog: 0, in_flight: 0 })
const buckets = ref<BucketStats[]>([])
const bucketsLoading = ref(false)

async function fetchQueueDepth() {
  try {
    const data = await getQueueDepth()
    queueDepth.value = data
  } catch {
    // keep current state on error
  }
}

async function fetchBuckets(silent = false) {
  if (!silent) bucketsLoading.value = true
  try {
    const data = await getBuckets()
    buckets.value = data
  } catch (e: any) {
    if (!silent) ElMessage.error(e?.message || '获取桶统计失败')
  } finally {
    if (!silent) bucketsLoading.value = false
  }
}

function progressColor(percentage: number): string {
  if (percentage > 50) return 'var(--el-color-success)'
  if (percentage >= 20) return 'var(--el-color-warning)'
  return 'var(--el-color-danger)'
}

function progressClass(percentage: number): string {
  if (percentage > 50) return 'progress-high'
  if (percentage >= 20) return 'progress-mid'
  return 'progress-low'
}

function tokenPercentage(row: BucketStats): number {
  if (!row.max || row.max <= 0) return 0
  return Math.round((row.remaining / row.max) * 100)
}

let charactersTimer: ReturnType<typeof setInterval> | null = null
let bucketsTimer: ReturnType<typeof setInterval> | null = null

// ── Usage Logs ──
const logItems = ref<UsageLogEntry[]>([])
const logTotal = ref(0)
const logOffset = ref(0)
const logHasMore = ref(true)
const logLoading = ref(false)
let logTimer: ReturnType<typeof setInterval> | null = null

// ── Helpers ──
function statusTagType(status: string) {
  const map: Record<string, string> = {
    valid: 'success',
    about_to_expire: 'warning',
    expired: 'danger',
    unknown: 'info',
  }
  return map[status] ?? 'info'
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    valid: '有效',
    about_to_expire: '即将过期',
    expired: '已过期',
    unknown: '未知',
  }
  return map[status] ?? status
}

function formatDateTime(dateStr: string | null) {
  if (!dateStr) return '-'
  try {
    return new Date(dateStr).toLocaleString('zh-CN')
  } catch {
    return dateStr
  }
}

// ── Log helpers ──
function logStatusTagType(code: number | null) {
  if (code == null) return 'info'
  if (code >= 200 && code < 300) return 'success'
  if (code >= 400 && code < 500) return 'warning'
  if (code >= 500) return 'danger'
  return 'info'
}

function logLatencyClass(ms: number | null) {
  if (ms == null) return ''
  if (ms < 100) return 'latency-fast'
  if (ms <= 500) return 'latency-mid'
  return 'latency-slow'
}

// ── Log data ──
const LOG_PAGE_SIZE = 50

async function loadLogs(offset: number) {
  if (logLoading.value) return
  logLoading.value = true
  try {
    const data = await getUsageLog({ limit: LOG_PAGE_SIZE, offset })
    if (offset === 0) {
      logItems.value = data.items
    } else {
      logItems.value = [...logItems.value, ...data.items]
    }
    logTotal.value = data.total
    logHasMore.value = data.has_more
    logOffset.value = offset + data.items.length
  } catch (e: any) {
    ElMessage.error(e?.message || '获取使用日志失败')
  } finally {
    logLoading.value = false
  }
}

async function loadMore() {
  await loadLogs(logOffset.value)
}

async function refreshLogs() {
  logOffset.value = 0
  logItems.value = []
  logHasMore.value = true
  await loadLogs(0)
}

async function pollLogs() {
  // Polling is always silent — no loading state to avoid flicker
  try {
    const data = await getUsageLog({ limit: LOG_PAGE_SIZE, offset: 0 })
    // Replace first page items, keep the rest
    const tail = logItems.value.slice(LOG_PAGE_SIZE)
    logItems.value = [...data.items, ...tail]
    logTotal.value = data.total
    logHasMore.value = data.has_more
  } catch {
    // keep current state on error
  }
}

// ── Polling intervals (ms) ──
const TQ_POLL_INTERVAL = 3000
const CHARACTERS_POLL_INTERVAL = 30000
const BUCKETS_POLL_INTERVAL = 3000
const LOGS_POLL_INTERVAL = 3000

// ── Tab-aware polling ──
function startTabPolling(tab: string) {
  switch (tab) {
    case 'characters':
      if (!charactersTimer) {
        charactersTimer = setInterval(() => fetchCharacters(true), CHARACTERS_POLL_INTERVAL)
      }
      break
    case 'buckets':
      if (!bucketsTimer) {
        fetchQueueDepth()
        fetchBuckets()
        bucketsTimer = setInterval(() => {
          fetchQueueDepth()
          fetchBuckets(true)
        }, BUCKETS_POLL_INTERVAL)
      }
      break
    case 'logs':
      if (!logTimer) {
        if (logItems.value.length === 0) refreshLogs()
        logTimer = setInterval(pollLogs, LOGS_POLL_INTERVAL)
      }
      break
  }
}

function stopTabPolling(tab: string) {
  switch (tab) {
    case 'characters':
      if (charactersTimer) {
        clearInterval(charactersTimer)
        charactersTimer = null
      }
      break
    case 'buckets':
      if (bucketsTimer) {
        clearInterval(bucketsTimer)
        bucketsTimer = null
      }
      break
    case 'logs':
      if (logTimer) {
        clearInterval(logTimer)
        logTimer = null
      }
      break
  }
}

function clearAllTimers() {
  if (tqTimer) { clearInterval(tqTimer); tqTimer = null }
  if (cooldownTimer) { clearInterval(cooldownTimer); cooldownTimer = null }
  if (charactersTimer) { clearInterval(charactersTimer); charactersTimer = null }
  if (bucketsTimer) { clearInterval(bucketsTimer); bucketsTimer = null }
  if (logTimer) { clearInterval(logTimer); logTimer = null }
}

// ── Tab watcher ──
watch(activeTab, (newTab, oldTab) => {
  stopTabPolling(oldTab)
  startTabPolling(newTab)
})

// ── Lifecycle ──
onMounted(() => {
  // Initial fetches for all data
  fetchTqStatus()
  fetchCharacters()
  fetchQueueDepth()
  fetchBuckets()

  // TQ always polls regardless of active tab
  tqTimer = setInterval(fetchTqStatus, TQ_POLL_INTERVAL)

  // Start polling for default active tab
  startTabPolling(activeTab.value)
})

onUnmounted(() => {
  clearAllTimers()
})
</script>

<template>
  <div class="esi-module-status">
    <!-- TQ 服务器状态横幅 -->
    <div class="tq-banner">
      <el-alert :type="alertType" :closable="false" show-icon>
        <template #title>
          <div class="alert-content">
            <span class="tq-label">TQ 服务器状态</span>
            <span class="tq-separator">|</span>
            <span class="tq-detail">EVE 服务器状态：{{ statusText }}</span>
          </div>
        </template>
      </el-alert>
    </div>

    <!-- 标签页 -->
    <el-tabs v-model="activeTab">
      <!-- 角色状态 -->
      <el-tab-pane label="角色状态" name="characters">
        <template v-if="loading || characters.length > 0">
          <!-- 筛选栏 -->
          <div class="filter-section">
          <el-input
            v-model="searchUserName"
            placeholder="搜索用户名或角色名"
            clearable
            style="width: 280px"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
          <el-select
            v-model="statusFilter"
            placeholder="状态筛选"
            style="width: 180px"
          >
            <el-option
              v-for="opt in statusOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </div>

        <!-- 角色表格 -->
        <KTable
          :data="filteredCharacters"
          v-loading="loading"
          stripe
          style="width: 100%"
          class="character-table"
          empty-why="还没有已授权的 EVE 角色"
          empty-hint="在角色管理里完成 SSO 授权后会出现在这里"
        >
          <el-table-column prop="character_id" label="角色ID" width="120" />
          <el-table-column prop="character_name" label="角色名" min-width="150" />
          <el-table-column prop="user_name" label="所属用户" width="130">
            <template #default="{ row }">
              <span>{{ row.owner_user_name || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="corporation_id" label="公司ID" width="120">
            <template #default="{ row }">
              <span>{{ row.corporation_id ?? '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="Director" width="90" align="center">
            <template #default="{ row }">
              <el-tag
                :type="row.director ? 'success' : 'info'"
                size="small"
              >
                {{ row.director ? '是' : '否' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.token_status)" size="small">
                {{ statusLabel(row.token_status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="过期时间" width="180">
            <template #default="{ row }">
              <span>{{ formatDateTime(row.expires_time) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <el-button
                size="small"
                type="primary"
                :disabled="(cooldowns[row.character_id] ?? 0) > 0"
                @click="handleTestToken(row.character_id)"
              >
                <el-icon v-if="(cooldowns[row.character_id] ?? 0) > 0">
                  <Timer />
                </el-icon>
                <template v-if="(cooldowns[row.character_id] ?? 0) > 0">
                  {{ cooldowns[row.character_id] }}s
                </template>
                <template v-else>
                  测试令牌
                </template>
              </el-button>
            </template>
          </el-table-column>
        </KTable>
        </template>

        <!-- 空状态 -->
        <KEmpty v-if="!loading && characters.length === 0" why="还没有已授权的 EVE 角色" />
      </el-tab-pane>

      <!-- 桶监控 -->
      <el-tab-pane label="桶监控" name="buckets">
        <template v-if="bucketsLoading || buckets.length > 0">
          <!-- 队列深度监控 -->
          <div class="queue-depth-cards">
          <KCard class="metric-card" padding="sm">
            <KStat
              label="请求积压"
              :value="queueDepth.backlog"
              :tone="queueDepth.backlog > 10 ? 'warning' : 'default'"
            />
          </KCard>
          <KCard class="metric-card" padding="sm">
            <KStat label="处理中" :value="queueDepth.in_flight" />
          </KCard>
        </div>

        <!-- 桶列表表格 -->
        <KTable
          :data="buckets"
          v-loading="bucketsLoading"
          stripe
          style="width: 100%"
          class="bucket-table"
          empty-why="当前没有正在使用的 ESI 令牌桶"
        >
          <el-table-column prop="pool_name" label="桶名称" min-width="180" />
          <el-table-column label="令牌水位" width="200">
            <template #default="{ row }">
              <div :class="progressClass(tokenPercentage(row))">
                <el-progress
                  :percentage="tokenPercentage(row)"
                  :color="progressColor(tokenPercentage(row))"
                  :stroke-width="18"
                />
              </div>
            </template>
          </el-table-column>
          <el-table-column label="速率(tokens/s)" width="120">
            <template #default="{ row }">
              {{ (Math.round(row.rate * 10) / 10).toFixed(1) }}/s
            </template>
          </el-table-column>
          <el-table-column prop="max" label="最大令牌" width="100" />
          <el-table-column label="当前令牌" width="100">
            <template #default="{ row }">
              {{ Math.round(row.remaining) }}
            </template>
          </el-table-column>
          <el-table-column label="错误计数" width="100">
            <template #default="{ row }">
              <el-tag v-if="row.error_count > 0" type="danger">
                {{ row.error_count }}
              </el-tag>
              <span v-else>0</span>
            </template>
          </el-table-column>
          <el-table-column label="关联端点" min-width="200">
            <template #default="{ row }">
              <el-tag
                v-for="ep in row.endpoints"
                :key="ep"
                size="small"
                class="endpoint-tag"
              >
                {{ ep }}
              </el-tag>
            </template>
          </el-table-column>
        </KTable>
        </template>

        <!-- 空状态 -->
        <KEmpty v-if="!bucketsLoading && buckets.length === 0" why="还没有注册的 ESI 令牌桶" />
      </el-tab-pane>

      <!-- 使用日志 -->
      <el-tab-pane label="使用日志" name="logs">
        <template v-if="logLoading || logItems.length > 0">
          <!-- 日志表格 -->
          <KTable
          :data="logItems"
          v-loading="logLoading"
          stripe
          style="width: 100%"
          class="log-table"
          empty-why="还没有 ESI 调用记录"
          empty-hint="有请求进来后这里会按时间倒序累积"
        >
          <el-table-column label="时间" width="180">
            <template #default="{ row }">
              <span>{{ formatDateTime(row.timestamp) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="endpoint" label="端点" min-width="200" show-overflow-tooltip />
          <el-table-column prop="pool_name" label="桶名称" min-width="140" show-overflow-tooltip />
          <el-table-column label="角色ID" width="120">
            <template #default="{ row }">
              <span>{{ row.character_id ?? '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态码" width="90" align="center">
            <template #default="{ row }">
              <el-tag
                v-if="row.status_code != null"
                :type="logStatusTagType(row.status_code)"
                size="small"
              >
                {{ row.status_code }}
              </el-tag>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column label="延迟(ms)" width="110" align="center">
            <template #default="{ row }">
              <span
                v-if="row.latency_ms != null"
                :class="['latency-value', logLatencyClass(row.latency_ms)]"
              >
                {{ row.latency_ms }}
              </span>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column label="错误信息" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="error-text">{{ row.error_message || '-' }}</span>
            </template>
          </el-table-column>
        </KTable>

        <!-- 加载更多 -->
        <div class="load-more-section">
          <div class="load-more-info">
            已加载 {{ logItems.length }} / 共 {{ logTotal }} 条
          </div>
          <el-button
            type="primary"
            :disabled="!logHasMore"
            :loading="logLoading"
            @click="loadMore"
          >
            加载更多
          </el-button>
        </div>
        </template>

        <!-- 空状态 -->
        <KEmpty v-if="!logLoading && logItems.length === 0" why="暂无 ESI 使用日志" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.esi-module-status {
  padding: 20px;
}

/* TQ 横幅 */
.tq-banner {
  margin-bottom: 16px;
}

.alert-content {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.tq-label {
  font-weight: 600;
  margin-right: 2px;
}

.tq-separator {
  color: var(--el-text-color-placeholder);
  user-select: none;
}

.tq-detail {
  font-weight: 400;
}

/* 筛选栏 */
.filter-section {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

/* 桶表格 */
.bucket-table {
  margin-top: 0;
}

/* 队列深度卡片 */
.queue-depth-cards {
  display: flex;
  gap: 16px;
  margin-bottom: 20px;
}

.metric-card {
  flex: 1;
  text-align: center;
}

.metric-label {
  font-size: 14px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}

.metric-value {
  font-size: 32px;
  font-weight: 700;
  color: var(--el-text-color-primary);
}

.metric-value.metric-warn {
  color: var(--el-color-danger);
}

/* 端点标签间距 */
.endpoint-tag {
  margin: 2px;
}

/* 日志表格 */
.log-table {
  margin-top: 0;
}

.latency-value {
  font-weight: 500;
}

.latency-fast {
  color: var(--el-color-success);
}

.latency-mid {
  color: var(--el-color-warning);
}

.latency-slow {
  color: var(--el-color-danger);
}

/* 进度条颜色（深色模式适配） */
.progress-high :deep(.el-progress-bar__inner) {
  background-color: var(--el-color-success);
}

.progress-mid :deep(.el-progress-bar__inner) {
  background-color: var(--el-color-warning);
}

.progress-low :deep(.el-progress-bar__inner) {
  background-color: var(--el-color-danger);
}

.error-text {
  color: var(--el-text-color-secondary);
}

.load-more-section {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  margin-top: 16px;
  padding: 12px 0;
}

.load-more-info {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
</style>
