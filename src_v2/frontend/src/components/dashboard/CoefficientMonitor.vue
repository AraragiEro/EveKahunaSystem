<script setup lang="ts">
import KCard from '@/components/k/KCard.vue'
import KTable from '@/components/k/KTable.vue'
import KEmpty from '@/components/k/KEmpty.vue'
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { DataAnalysis, Delete } from '@element-plus/icons-vue'
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
  <KCard class="coeff-card" padding="none">
    <template #header>
      <div class="coeff-title">
        <el-icon class="coeff-icon"><DataAnalysis /></el-icon>
        <span>系数监控</span>
      </div>
    </template>
    <template #actions>
      <!-- 页内只留 1 个实心主按钮（进行中任务的「下一步」），这里降为描边按钮 -->
      <el-button size="small" :loading="addingAll" @click="addAllAssetSystems">
        一键添加资产星系
      </el-button>
    </template>

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
    <div class="coeff-body">
      <div v-if="loading" class="coeff-loading">
        <el-skeleton animated :rows="4" />
      </div>

      <div v-else-if="error" class="coeff-empty">
        <KEmpty why="加载失败，请刷新重试" size="sm" />
      </div>

      <div v-else-if="watchlist.length === 0" class="coeff-empty">
        <KEmpty why="暂无监控星系，使用上方搜索添加" size="sm" />
      </div>

      <!-- 列宽按权重分配：星系 40 / 制造 25 / 反应 25 / 操作 10（百分比 + fixed 布局，宽屏也不会被内容拉散） -->
      <KTable
        v-else
        :data="watchlist"
        density="compact"
        class="coeff-table"
        stripe
      >
        <el-table-column label="星系名称">
          <template #default="{ row }">
            <div class="system-name-cell">
              <span class="system-zh">{{ row.system_name_zh || row.system_name }}</span>
              <span class="system-region" v-if="row.region_name">{{ row.region_name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="制造系数" align="center">
          <template #default="{ row }">
            <span class="coeff-value">{{ formatCoefficient(row.manufacturing) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="反应系数" align="center">
          <template #default="{ row }">
            <span class="coeff-value">{{ formatCoefficient(row.reaction) }}</span>
          </template>
        </el-table-column>
        <!-- 每行一个实心红按钮噪声太大，改成弱化的图标按钮 + tooltip -->
        <el-table-column label="操作" align="center">
          <template #default="{ row }">
            <el-tooltip content="移除监控" placement="top">
              <el-button
                type="danger"
                text
                size="small"
                :icon="Delete"
                aria-label="移除监控"
                class="coeff-remove"
                @click="removeSystem(row)"
              />
            </el-tooltip>
          </template>
        </el-table-column>
      </KTable>
    </div>
  </KCard>
</template>

<style scoped>
.coeff-card {
  flex: 1 1 auto;
  min-height: 0;
  /* 网格项默认 min-width:auto 时会被内容顶宽，卡片右缘就会盖住表格最后一列 */
  min-width: 0;
}

/* KCard 的 body 补成 flex，表格区才能在卡片内滚动而不是撑高卡片被网格裁掉 */
.coeff-card :deep(.k-card__body) {
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
}

.coeff-title {
  display: flex;
  align-items: center;
  gap: var(--k-space-2);
  font-size: var(--k-font-md);
  font-weight: 600;
  color: var(--k-color-text);
}

.coeff-icon {
  font-size: 16px;
  color: var(--k-color-primary);
}

/* ── Search row ── */
.search-row {
  padding: var(--k-space-3) var(--k-space-4);
  border-bottom: 1px solid var(--k-color-border-subtle);
}

.search-input {
  width: 100%;
}

/* ── Section body ── */
.coeff-body {
  flex: 1;
  min-height: 0;
  /* 横向也允许滚动：极窄卡片下宁可出滚动条，也不要把最后一列裁掉 */
  min-width: 0;
  overflow: auto;
}

.coeff-loading {
  padding: var(--k-space-3) var(--k-space-4);
}

.coeff-empty {
  padding: var(--k-space-6) var(--k-space-4);
  display: flex;
  justify-content: center;
}

/* ── 列宽权重：34 / 25 / 25 / 16 ──
   el-table 的列 width 只接受数字（百分比字符串会被当成 px），所以权重写在 colgroup 上，
   配 table-layout: fixed 才能保证宽屏下也按比例分，而不是被最长的星系名拉散。
   注意 EP 2.11 的表格节点自己就带 .el-table__header / .el-table__body 类
   （不是「wrapper > table」），选择器必须直接命中 table 本身，否则 fixed 布局不生效、
   列宽按内容撑到容器之外，最后一列就会被卡片边缘裁掉。
   操作列原来只占 10%（1440 下 ≈31px），比「操作」两个字 + 单元格内距还窄，
   表头被裁成「操」；这里提到 16% 并保留容器横向滚动兜底。 */
.coeff-table :deep(table.el-table__header),
.coeff-table :deep(table.el-table__body) {
  table-layout: fixed;
  width: 100% !important;
}

.coeff-table :deep(colgroup col:nth-child(1)) {
  width: 34% !important;
}

.coeff-table :deep(colgroup col:nth-child(2)) {
  width: 25% !important;
}

.coeff-table :deep(colgroup col:nth-child(3)) {
  width: 25% !important;
}

.coeff-table :deep(colgroup col:nth-child(4)) {
  width: 16% !important;
}

/* 星系名允许省略，不把 40% 的列撑开 */
.coeff-table :deep(.cell) {
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 操作列只有 10%（1920 下 ≈41px），收紧内距并禁止表头换行，否则「操作」会竖排 */
.coeff-table :deep(th:last-child .cell),
.coeff-table :deep(td:last-child .cell) {
  padding-left: var(--k-space-1);
  padding-right: var(--k-space-1);
  text-align: center;
}

.coeff-table :deep(th:last-child .cell) {
  white-space: nowrap;
  overflow: visible;
}

/* ── System name cell ── */
.system-name-cell {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.system-zh {
  font-size: var(--k-font-sm);
  font-weight: 600;
  color: var(--k-color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.system-region {
  font-size: 11px;
  color: var(--k-color-text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Coefficient value ── */
.coeff-value {
  font-size: var(--k-font-sm);
  font-weight: 600;
  color: var(--k-color-text);
  font-variant-numeric: tabular-nums;
}

.coeff-remove {
  height: 24px;
  width: 24px;
  padding: 0;
}
</style>
