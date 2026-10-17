<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { http } from '@/http'
import { handleApiResponse } from '@/utils/apiResponse'
import type { WatchedSystem, SystemSearchResult } from '@/types/coefficient'

/* ── State ── */
const loading = ref(false)
const error = ref(false)
const watchlist = ref<WatchedSystem[]>([])
const searchQuery = ref('')
const addingAll = ref(false)

/* ── API: fetch watchlist ── */
const fetchWatchlist = async () => {
  loading.value = true
  error.value = false

  try {
    const res = await http.get('/EVE/home/coefficient/watchlist')
    const data = await handleApiResponse<{ status: number; data: WatchedSystem[] }>(res)
    if (data && data.data) {
      watchlist.value = data.data
    } else {
      watchlist.value = []
    }
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

/* ── API: search systems ── */
const searchSystems = async (
  query: string,
  callback: (results: SystemSearchResult[]) => void,
) => {
  if (!query || query.trim().length === 0) {
    callback([])
    return
  }

  try {
    const res = await http.get('/EVE/home/searchSystems', { q: query.trim() })
    const data = await handleApiResponse<{ status: number; data: SystemSearchResult[] }>(res)
    if (data && data.data) {
      callback(data.data)
    } else {
      callback([])
    }
  } catch {
    callback([])
  }
}

/* ── API: add system ── */
const addSystem = async (systemId: number) => {
  try {
    const res = await http.post('/EVE/home/coefficient/add', { system_id: systemId })
    const data = await handleApiResponse<{ status: number }>(res)
    if (data) {
      ElMessage.success('添加成功')
      await fetchWatchlist()
    }
  } catch {
    ElMessage.error('添加失败')
  }
}

/* ── Handler: search select ── */
const onSearchSelect = (item: SystemSearchResult) => {
  searchQuery.value = ''
  addSystem(item.system_id)
}

/* ── API: remove system ── */
const removeSystem = async (system: WatchedSystem) => {
  try {
    await ElMessageBox.confirm(
      `确定要移除星系 "${system.system_name_zh || system.system_name}" 的监控吗？`,
      '确认移除',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return // user cancelled
  }

  try {
    const res = await http.post('/EVE/home/coefficient/remove', { system_id: system.system_id })
    const data = await handleApiResponse<{ status: number }>(res)
    if (data) {
      ElMessage.success('移除成功')
      await fetchWatchlist()
    }
  } catch {
    ElMessage.error('移除失败')
  }
}

/* ── API: add all asset systems ── */
const addAllAssetSystems = async () => {
  addingAll.value = true

  try {
    const res = await http.post('/EVE/home/coefficient/addAllAssetSystems', {})
    const data = await handleApiResponse<{ status: number; data: { added_count: number }; message: string }>(res)
    if (data) {
      ElMessage.success(data.data?.added_count
        ? `成功添加 ${data.data.added_count} 个星系`
        : '操作完成')
      await fetchWatchlist()
    }
  } catch {
    ElMessage.error('批量添加失败')
  } finally {
    addingAll.value = false
  }
}

/* ── Format coefficient ── */
const formatCoefficient = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return '-'
  return (value * 100).toFixed(2) + '%'
}

/* ── Lifecycle ── */
onMounted(() => {
  fetchWatchlist()
})
</script>

<template>
  <div class="section-card">
    <!-- Header -->
    <div class="section-header">
      <span class="section-title-with-icon">📊 系数监控</span>
      <el-button
        type="primary"
        size="small"
        :loading="addingAll"
        @click="addAllAssetSystems"
      >
        一键添加资产星系
      </el-button>
    </div>

    <!-- Search -->
    <div class="search-row">
      <el-autocomplete
        v-model="searchQuery"
        :fetch-suggestions="searchSystems"
        placeholder="搜索星系名称（中/英文）"
        :trigger-on-focus="false"
        value-key="system_name_zh"
        class="search-input"
        @select="onSearchSelect"
      />
    </div>

    <!-- Content -->
    <div class="section-body">
      <!-- Loading -->
      <div v-if="loading" class="section-loading">
        <el-skeleton animated :rows="4" />
      </div>

      <!-- Error -->
      <div v-else-if="error" class="section-empty">
        <el-empty description="加载失败，请刷新重试" :image-size="80" />
      </div>

      <!-- Empty -->
      <div v-else-if="watchlist.length === 0" class="section-empty">
        <el-empty description="暂无监控星系，使用上方搜索添加" :image-size="80" />
      </div>

      <!-- Table -->
      <div v-else class="table-wrapper">
        <el-table :data="watchlist" stripe>
          <el-table-column label="星系名称" min-width="160">
            <template #default="{ row }">
              <div class="system-name-cell">
                <span class="system-zh">{{ row.system_name_zh || row.system_name }}</span>
                <span class="system-region" v-if="row.region_name">{{ row.region_name }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="制造系数" width="110" align="center">
            <template #default="{ row }">
              <span class="coeff-value">{{ formatCoefficient(row.manufacturing) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="反应系数" width="110" align="center">
            <template #default="{ row }">
              <span class="coeff-value">{{ formatCoefficient(row.reaction) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="90" align="center" fixed="right">
            <template #default="{ row }">
              <el-button type="danger" size="small" @click="removeSystem(row)">
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── Section card (following dashboard pattern) ── */
.section-card {
  background: var(--k-color-surface);
  border-radius: var(--k-radius-lg);
  border: 1px solid var(--k-color-border);
  box-shadow: var(--k-shadow-sm);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--k-color-border);
}

.section-title-with-icon {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--k-color-text);
}

/* ── Search row ── */
.search-row {
  padding: 12px 20px;
  border-bottom: 1px solid var(--k-color-border);
}

.search-input {
  width: 100%;
}

/* ── Section body ── */
.section-body {
  flex: 1;
  min-height: 0;
}

.section-loading {
  padding: 16px 20px;
}

.section-empty {
  padding: 48px 20px;
  display: flex;
  justify-content: center;
}

/* ── Table wrapper ── */
.table-wrapper {
  padding: 0;
}

/* ── System name cell ── */
.system-name-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.system-zh {
  font-size: 14px;
  font-weight: 600;
  color: var(--k-color-text);
}

.system-region {
  font-size: 12px;
  color: var(--k-color-text-secondary);
}

/* ── Coefficient value ── */
.coeff-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--k-color-primary);
  font-variant-numeric: tabular-nums;
}
</style>
