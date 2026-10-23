<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Box, Document, List, Coin } from '@element-plus/icons-vue'
import KTable from '@/components/k/KTable.vue'
import KStat from '@/components/k/KStat.vue'
import { http } from '@/http'

// ==================== 功能模块 ====================
type ModuleKey = 'market-cost' | 'orders-stats' | 'lp-snapshot' | string

interface ModuleItem {
  key: ModuleKey
  label: string
  icon: any
  description: string
}

const modules = ref<ModuleItem[]>([
  {
    key: 'market-cost',
    label: '市场成本缓存',
    icon: Box,
    description: '管理系统级市场成本计算缓存的全量/增量刷新',
  },
  {
    key: 'orders-stats',
    label: '订单统计刷新',
    icon: List,
    description: '管理用户订单统计数据刷新标记，支持手动触发刷新',
  },
  {
    key: 'lp-snapshot',
    label: 'LP 快照管理',
    icon: Coin,
    description: '管理 LP 价值快照执行标志，清除后将在下次启动或定时触发时重新计算',
  },
])

const activeModule = ref<ModuleKey>('market-cost')

// ==================== 状态数据 ====================
const loading = ref(false)
const priceRefreshLoading = ref(false)
const statusLoading = ref(false)
const statusData = ref<any>({})
const logsData = ref<any[]>([])

// 轮询定时器
let statusTimer: ReturnType<typeof setInterval> | null = null
const STATUS_POLL_INTERVAL = 3000 // 3秒轮询一次

// ==================== 状态格式化 ====================
const formatStatusLabel = (status: string) => {
  const map: Record<string, { label: string; type: string }> = {
    idle: { label: '空闲', type: 'info' },
    running: { label: '刷新中', type: 'warning' },
    completed: { label: '已完成', type: 'success' },
    failed: { label: '失败', type: 'danger' },
  }
  return map[status] || { label: status || '未知', type: 'info' }
}

/** 把状态语义映射到 KStat 的 tone（info 无对应档，回落 default） */
const statusTone = (status: string): 'default' | 'primary' | 'success' | 'warning' | 'danger' => {
  const type = formatStatusLabel(status).type
  if (type === 'success' || type === 'warning' || type === 'danger' || type === 'primary') {
    return type
  }
  return 'default'
}

const formatDateTime = (isoStr: string): string => {
  if (!isoStr) return '-'
  const date = new Date(isoStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

// ==================== API 调用 ====================
const fetchStatus = async () => {
  try {
    const res = await http.get('/admin/system/market-cost/status')
    const data = await res.json()
    if (data.status === 200) {
      statusData.value = data.data || {}
    }
  } catch (error) {
    console.error('获取状态失败:', error)
  }
}

const fetchLogs = async () => {
  try {
    const res = await http.get('/admin/system/market-cost/refresh-logs?limit=10')
    const data = await res.json()
    if (data.status === 200) {
      logsData.value = data.data || []
    }
  } catch (error) {
    console.error('获取历史记录失败:', error)
  }
}

// ==================== 手动刷新 ====================
const handleTriggerRefresh = async () => {
  try {
    await ElMessageBox.confirm(
      '此操作将清除现有缓存并重新计算所有有蓝图的物品成本，耗时较长，期间成本数据可能不完整。是否确认执行？',
      '确认执行全量刷新',
      {
        confirmButtonText: '确认执行',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
  } catch {
    return
  }

  loading.value = true
  try {
    const res = await http.post('/admin/system/market-cost/trigger-full-refresh', {})
    const data = await res.json()
    if (data.status === 200) {
      ElMessage.success(data.message || '刷新任务已启动')
      await fetchStatus()
      await fetchLogs()
    } else if (res.status === 409) {
      ElMessage.warning(data.message || '已有任务在运行')
    } else {
      ElMessage.error(data.message || '启动失败')
    }
  } catch (error: any) {
    ElMessage.error('请求失败')
    console.error(error)
  } finally {
    loading.value = false
  }
}

// ==================== 手动刷新价格 ====================
const handleTriggerPriceRefresh = async () => {
  try {
    await ElMessageBox.confirm(
      '此操作将基于已保存的材料骨架，查询最新市场价格并刷新成本结果。不重新计算材料，耗时较短。是否确认执行？',
      '确认执行价格刷新',
      {
        confirmButtonText: '确认执行',
        cancelButtonText: '取消',
        type: 'info',
      }
    )
  } catch {
    return
  }

  priceRefreshLoading.value = true
  try {
    const res = await http.post('/admin/system/market-cost/trigger-price-refresh', {
      market_zone: 'jita',
      price_base: 'buy',
    })
    const data = await res.json()
    if (data.status === 200) {
      ElMessage.success(data.message || '价格刷新完成')
      await fetchStatus()
    } else {
      ElMessage.error(data.message || '刷新失败')
    }
  } catch (error: any) {
    ElMessage.error('请求失败')
    console.error(error)
  } finally {
    priceRefreshLoading.value = false
  }
}

// ==================== 轮询控制 ====================
const startPolling = () => {
  stopPolling()
  statusTimer = setInterval(() => {
    fetchStatus()
  }, STATUS_POLL_INTERVAL)
}

const stopPolling = () => {
  if (statusTimer) {
    clearInterval(statusTimer)
    statusTimer = null
  }
}

// ==================== 订单统计刷新状态 ====================
const ordersStatsUsers = ref<any[]>([])
const ordersStatsLoading = ref(false)
const ordersStatsDeleting = ref('')

const fetchOrdersStatsStatus = async () => {
  try {
    const res = await http.get('/admin/system/orders-stats/status')
    const data = await res.json()
    if (data.status === 200) {
      ordersStatsUsers.value = data.data || []
    }
  } catch (error) {
    console.error('获取订单统计刷新状态失败:', error)
  }
}

const handleDeleteOrdersStatsFlag = async (userName: string) => {
  try {
    await ElMessageBox.confirm(
      `确认删除用户 ${userName} 的刷新标记吗？删除后系统将在下次轮询时重新刷新该用户的订单统计数据。`,
      '确认删除',
      { confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning' }
    )
    ordersStatsDeleting.value = userName
    const res = await http.delete(`/admin/system/orders-stats/flag?user_name=${encodeURIComponent(userName)}`)
    const data = await res.json()
    if (data.status === 200) {
      ElMessage.success(data.message as string)
      await fetchOrdersStatsStatus()
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除刷新标记失败:', error)
      ElMessage.error('删除刷新标记失败')
    }
  } finally {
    ordersStatsDeleting.value = ''
  }
}

const formatTtl = (seconds: number) => {
  if (seconds <= 0) return '-'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 0) return `${h}小时${m}分钟`
  return `${m}分钟`
}

// ==================== LP 快照管理 ====================
const lpSnapshotLoading = ref(false)
const lpSnapshotFlagExists = ref(false)
const lpSnapshotTtl = ref(-1)

const fetchLpSnapshotStatus = async () => {
  try {
    const res = await http.get('/admin/system/lp-snapshot/flag')
    const data = await res.json()
    if (data.status === 200) {
      lpSnapshotFlagExists.value = data.data.flag_exists
      lpSnapshotTtl.value = data.data.ttl_seconds
    }
  } catch (error) {
    console.error('获取 LP 快照状态失败:', error)
  }
}

const handleClearLpSnapshotFlag = async () => {
  try {
    await ElMessageBox.confirm(
      '清除执行标志后，系统将在下次定时触发（每日 UTC 12:00）或服务器重启时重新计算所有军团的 LP 价值。是否确认清除？',
      '确认清除 LP 快照标志',
      { confirmButtonText: '确认清除', cancelButtonText: '取消', type: 'warning' }
    )
    lpSnapshotLoading.value = true
    const res = await http.delete('/admin/system/lp-snapshot/flag')
    const data = await res.json()
    if (data.status === 200) {
      ElMessage.success(data.message as string)
      await fetchLpSnapshotStatus()
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('清除 LP 快照标志失败:', error)
      ElMessage.error('操作失败')
    }
  } finally {
    lpSnapshotLoading.value = false
  }
}

// ==================== 生命周期 ====================
onMounted(() => {
  fetchStatus()
  fetchLogs()
  fetchOrdersStatsStatus()
  fetchLpSnapshotStatus()
  startPolling()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<template>
  <div class="website-management">
    <h2 class="page-title">网站管理</h2>

    <!-- ==================== 功能模块概览 ==================== -->
    <div class="module-overview">
      <div
        v-for="mod in modules"
        :key="mod.key"
        class="module-card"
        :class="{ active: activeModule === mod.key }"
        @click="activeModule = mod.key"
      >
        <div class="module-icon-wrapper">
          <el-icon :size="28"><component :is="mod.icon" /></el-icon>
        </div>
        <div class="module-info">
          <div class="module-label">{{ mod.label }}</div>
          <div class="module-desc">{{ mod.description }}</div>
        </div>
      </div>

      <!-- 预留扩展位置 -->
      <div class="module-card placeholder">
        <div class="module-icon-wrapper">
          <el-icon :size="28"><Document /></el-icon>
        </div>
        <div class="module-info">
          <div class="module-label">待扩展</div>
          <div class="module-desc">更多管理功能即将上线</div>
        </div>
      </div>
    </div>

    <!-- ==================== 功能模块详情 ==================== -->
    <div v-if="activeModule === 'market-cost'" class="module-detail">
      <!-- 缓存状态概览 -->
      <div class="card">
        <div class="card-header">
          <span class="card-title">
            <el-icon class="card-title-icon"><Box /></el-icon>
            市场成本缓存状态
          </span>
          <el-button size="small" :loading="statusLoading" @click="fetchStatus">
            <el-icon><Refresh /></el-icon>
            刷新状态
          </el-button>
        </div>

        <div class="status-grid">
          <KStat class="status-item" label="当前状态" :value="formatStatusLabel(statusData.overall_status).label"
            :tone="statusTone(statusData.overall_status)" align="center" />
          <KStat class="status-item" label="缓存 type_id 数量" :value="statusData.cached_type_id_count ?? 0"
            align="center" />
          <div class="status-item">
            <div class="status-label">Flag 状态</div>
            <div class="status-value">
              <el-tag :type="statusData.flag_exists ? 'success' : 'info'" size="small">
                {{ statusData.flag_exists ? '已设置' : '未设置' }}
              </el-tag>
            </div>
          </div>
          <div class="status-item">
            <div class="status-label">分布式锁</div>
            <div class="status-value">
              <el-tag :type="statusData.lock_exists ? 'danger' : 'success'" size="small">
                {{ statusData.lock_exists ? '已占用' : '空闲' }}
              </el-tag>
            </div>
          </div>
        </div>

        <!-- 实时进度（仅运行中时显示） -->
        <div v-if="statusData.overall_status === 'running' && statusData.progress" class="progress-section">
          <div class="progress-header">
            <span class="progress-title">实时计算进度</span>
            <span class="progress-step">{{ statusData.progress.current_step }}</span>
          </div>
          <el-progress
            :percentage="
              statusData.progress.total > 0
                ? Math.round((statusData.progress.completed / statusData.progress.total) * 100)
                : 0
            "
            :stroke-width="18"
            status="exception"
          />
          <div class="progress-detail">
            已完成 {{ statusData.progress.completed }} / {{ statusData.progress.total }}
          </div>
        </div>

        <!-- 最近一次刷新详情 -->
        <div v-if="statusData.detail && Object.keys(statusData.detail).length > 0" class="detail-section">
          <div class="detail-title">最近一次刷新详情</div>
          <div class="detail-grid">
            <div class="detail-item">
              <span class="detail-label">触发方式</span>
              <span class="detail-value">
                <el-tag :type="statusData.detail.triggered_by === 'admin' ? 'primary' : 'info'" size="small">
                  {{ statusData.detail.triggered_by === 'admin' ? '手动' : '自动' }}
                </el-tag>
              </span>
            </div>
            <div class="detail-item">
              <span class="detail-label">计算数量</span>
              <span class="detail-value">{{ statusData.detail.type_id_count ?? '-' }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">当前步骤</span>
              <span class="detail-value">{{ statusData.detail.current_step ?? '-' }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">更新时间</span>
              <span class="detail-value">{{ formatDateTime(statusData.detail.updated_at) }}</span>
            </div>
            <div v-if="statusData.detail.error" class="detail-item error-item">
              <span class="detail-label">错误信息</span>
              <span class="detail-value error-text">{{ statusData.detail.error }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 手动操作 -->
      <div class="card">
        <div class="card-header">
          <span class="card-title">
            <el-icon class="card-title-icon"><Refresh /></el-icon>
            手动操作
          </span>
        </div>
        <div class="action-content">
          <div class="action-row">
            <el-button
              type="primary"
              size="large"
              :loading="loading"
              :disabled="statusData.lock_exists || statusData.overall_status === 'running'"
              @click="handleTriggerRefresh"
            >
              <el-icon class="btn-icon"><Refresh /></el-icon>
              立即执行全量刷新
            </el-button>
            <el-button
              type="warning"
              size="large"
              :loading="priceRefreshLoading"
              @click="handleTriggerPriceRefresh"
            >
              <el-icon class="btn-icon"><Refresh /></el-icon>
              仅刷新价格
            </el-button>
          </div>
          <div class="action-desc">
            <p><strong>全量刷新：</strong>将清除现有缓存并重新计算所有有蓝图的物品成本。耗时较长，请谨慎操作。</p>
            <p><strong>仅刷新价格：</strong>基于已保存的材料骨架，查询最新市场价格并刷新成本结果。不重新计算材料，耗时较短。</p>
            <span v-if="statusData.lock_exists || statusData.overall_status === 'running'" class="action-warn">
              （当前有全量刷新任务正在运行中，请等待完成）
            </span>
          </div>
        </div>
      </div>

      <!-- 刷新历史 -->
      <div class="card">
        <div class="card-header">
          <span class="card-title">刷新历史（最近10条）</span>
          <el-button size="small" @click="fetchLogs">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
        <KTable
          :data="logsData"
          style="width: 100%"
          size="small"
          density="compact"
          empty-why="还没有刷新记录"
          empty-hint="手动或定时刷新一次后就会出现在这里"
        >
          <el-table-column label="时间" min-width="160">
            <template #default="{ row }">
              {{ formatDateTime(row.time) }}
            </template>
          </el-table-column>
          <el-table-column label="触发方式" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="row.triggered_by === 'admin' ? 'primary' : 'info'" size="small">
                {{ row.triggered_by === 'admin' ? '手动' : '自动' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="type_id_count" label="计算数量" width="100" align="center" />
          <el-table-column label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="row.status === 'completed' ? 'success' : 'danger'" size="small">
                {{ row.status === 'completed' ? '成功' : '失败' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="错误信息" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.error" class="error-text">{{ row.error }}</span>
              <span v-else>-</span>
            </template>
          </el-table-column>
        </KTable>
      </div>
    </div>

    <!-- ==================== 订单统计刷新模块 ==================== -->
    <div v-if="activeModule === 'orders-stats'" class="module-detail">
      <div class="card">
        <div class="card-header">
          <span class="card-title">
            <el-icon class="card-title-icon"><List /></el-icon>
            订单统计刷新状态
          </span>
          <el-button size="small" :loading="ordersStatsLoading" @click="fetchOrdersStatsStatus">
            <el-icon><Refresh /></el-icon>
            刷新状态
          </el-button>
        </div>

        <div class="action-desc" style="margin-bottom: 16px;">
          <p>系统每5分钟轮询检查各VIP用户的刷新标记。标记存在（24h TTL）则跳过；标记不存在或已过期则自动刷新。</p>
          <p class="action-warn">删除标记后，系统将在下次轮询时（最多5分钟）重新拉取该角色的订单历史数据。</p>
        </div>

        <KTable
          :data="ordersStatsUsers"
          style="width: 100%"
          size="small"
          density="compact"
          empty-why="没有需要刷新订单统计的 VIP 用户"
          empty-hint="VIP 用户产生订单历史后会自动出现在这里"
        >
          <el-table-column prop="user_name" label="用户名" min-width="160" />
          <el-table-column label="标记状态" width="120" align="center">
            <template #default="{ row }">
              <el-tag :type="row.flag_exists ? 'success' : 'info'" size="small">
                {{ row.flag_exists ? '已刷新' : '待刷新' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="剩余时间" width="140" align="center">
            <template #default="{ row }">
              {{ row.flag_exists ? formatTtl(row.ttl_seconds) : '-' }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" align="center">
            <template #default="{ row }">
              <el-button
                type="danger"
                size="small"
                :loading="ordersStatsDeleting === row.user_name"
                @click="handleDeleteOrdersStatsFlag(row.user_name)"
              >
                删除标记
              </el-button>
            </template>
          </el-table-column>
        </KTable>
      </div>
    </div>

    <!-- LP 快照管理 -->
    <div v-if="activeModule === 'lp-snapshot'" class="module-detail">
      <div class="card">
        <div class="card-header">
          <span class="card-title">
            <el-icon class="card-title-icon"><Coin /></el-icon>
            快照执行标志
          </span>
          <el-tag :type="lpSnapshotFlagExists ? 'success' : 'info'" size="small">
            {{ lpSnapshotFlagExists ? '已执行' : '待执行' }}
          </el-tag>
        </div>
        <div class="action-desc" style="margin-bottom: 16px;">
          <p v-if="lpSnapshotFlagExists">
            当前标志存在，剩余有效时间 <strong>{{ formatTtl(lpSnapshotTtl) }}</strong>。
            标志有效期间，定时器和服务器重启不会重复执行快照。
          </p>
          <p v-else>
            当前无执行标志。下次定时触发（UTC 12:00）或服务器重启时将自动执行 LP 价值快照。
          </p>
          <p class="action-warn">
            清除标志不会删除已有的快照数据，仅允许系统重新执行一次快照计算。
          </p>
        </div>
        <div class="action-row">
          <el-button size="small" :loading="lpSnapshotLoading" @click="fetchLpSnapshotStatus">
            <el-icon><Refresh /></el-icon>
            刷新状态
          </el-button>
          <el-button
            size="small"
            type="danger"
            :loading="lpSnapshotLoading"
            :disabled="!lpSnapshotFlagExists"
            @click="handleClearLpSnapshotFlag"
          >
            清除标志
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.website-management {
  padding: 20px;
}

.page-title {
  margin: 0 0 20px 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--k-color-text);
}

/* ==================== 功能模块概览 ==================== */
.module-overview {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.module-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
  background: var(--k-color-surface);
  border-radius: 8px;
  box-shadow: var(--k-shadow-md);
  border: 2px solid transparent;
  cursor: pointer;
  transition: all 0.2s ease;
}

.module-card:hover {
  border-color: color-mix(in srgb, var(--k-color-primary) 50%, var(--k-color-border));
  transform: translateY(-2px);
}

.module-card.active {
  border-color: var(--k-color-primary);
  background: var(--k-color-surface-soft);
}

.module-card.placeholder {
  opacity: 0.6;
  cursor: default;
}

.module-card.placeholder:hover {
  transform: none;
  border-color: transparent;
}

.module-icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  border-radius: var(--k-radius-sm);
  background: var(--k-color-primary-soft);
  color: var(--k-color-primary);
  flex-shrink: 0;
}

.module-card.placeholder .module-icon-wrapper {
  background: var(--k-color-border);
  color: var(--k-color-text-secondary);
}

.module-info {
  flex: 1;
  min-width: 0;
}

.module-label {
  font-size: 16px;
  font-weight: 600;
  color: var(--k-color-text);
  margin-bottom: 4px;
}

.module-desc {
  font-size: 13px;
  color: var(--k-color-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ==================== 功能模块详情 ==================== */
.module-detail {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.card {
  background: var(--k-color-surface);
  border-radius: 8px;
  box-shadow: var(--k-shadow-md);
  border: 1px solid var(--k-color-border);
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--k-color-border);
}

.card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--k-color-text);
}

.card-title-icon {
  color: var(--el-color-primary);
}

/* 状态网格 */
.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
}

.status-item {
  background: var(--k-color-surface-soft);
  border-radius: var(--k-radius-sm);
  padding: 16px;
  text-align: center;
}

.status-label {
  font-size: 13px;
  color: var(--k-color-text-secondary);
  margin-bottom: 8px;
}

.status-value {
  font-size: 14px;
  color: var(--k-color-text);
}

.highlight-number {
  font-size: 24px;
  font-weight: 700;
  color: var(--el-color-primary);
}

/* 进度区域 */
.progress-section {
  margin-top: 20px;
  padding: 16px;
  background: var(--k-color-surface-soft);
  border-radius: var(--k-radius-sm);
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.progress-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--k-color-text);
}

.progress-step {
  font-size: 13px;
  color: var(--k-color-text-secondary);
}

.progress-detail {
  margin-top: 8px;
  font-size: 13px;
  color: var(--k-color-text-secondary);
  text-align: right;
}

/* 详情区域 */
.detail-section {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--k-color-border);
}

.detail-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--k-color-text);
  margin-bottom: 12px;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
}

.detail-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.detail-label {
  color: var(--k-color-text-secondary);
  min-width: 70px;
}

.detail-value {
  color: var(--k-color-text);
  font-weight: 500;
}

.error-item {
  grid-column: 1 / -1;
}

.error-text {
  color: var(--el-color-danger);
}

/* 操作区域 */
.action-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.btn-icon {
  margin-right: 6px;
}

.action-desc {
  font-size: 13px;
  color: var(--k-color-text-secondary);
  line-height: 1.6;
}

.action-desc p {
  margin: 4px 0;
}

.action-warn {
  color: var(--el-color-warning);
  font-weight: 500;
}
</style>
