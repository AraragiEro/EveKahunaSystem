<script setup lang="ts">
import { onMounted, onUnmounted, ref, computed, watch } from 'vue'
import { Setting, SuccessFilled, CircleCloseFilled, Plus, CloseBold, Delete, Refresh, VideoPlay } from '@element-plus/icons-vue'
import { http } from '@/http'
import { ElMessage } from 'element-plus';
import AssetViewIndustrypermision from './components/AssetViewIndustrypermision.vue'

const form = ref({
  allow_personal_asset: false,
  allow_corporation_asset: false,
  is_edit_corp_setting_allowed: false
})

type Mission = {
  id: string | number
  subject_type: 'character' | 'corp'
  subject_name: string
  subject_id: number
  is_active: boolean
  last_pull_time?: string | null
}

const missions = ref<Mission[]>([])
const missionsLoading = ref(false)

// 当前时间戳，用于实时更新倒计时
const currentTime = ref(Date.now())
let timeUpdateInterval: number | null = null

const createDialogVisible = ref(false)
const createForm = ref({
  subject_type: 'character' as 'character' | 'corp',
  subject_name: '' as string,
  subject_id: 0 as number,
  start_immediately: true as boolean,
})

type OwnerOption = {
  owner_name: string
  owner_id: number
  owner_type: 'character' | 'corp'
}

const ownerOptions = ref<OwnerOption[]>([])
const ownersLoading = ref(false)
const filteredOwnerOptions = computed(() => {
  const t = createForm.value.subject_type
  return ownerOptions.value.filter(o => {
    return o.owner_type === t
  })
})

const getIsEditCorpSettingAllowed = async () => {
  const response = await http.get('/EVE/asset/isEditCorpSettingAllowed')
  const data = await response.json()
  form.value.is_edit_corp_setting_allowed = data?.message || false
}

const handleAllowPullPersonalAsset = async () => {
  const response = await http.post('/EVE/asset/allowPullPersonalAsset', {
    allow_personal_asset: form.value.allow_personal_asset
  })
  const data = await response.json()
}

const handleAllowPullCorporationAsset = async () => {}
  
const fetchMissions = async () => {
  missionsLoading.value = true
  try {
    const res = await http.get('/EVE/asset/getAssetPullMissions')
    const data = await res.json()
    missions.value = Array.isArray(data?.data) ? data.data : []
  } catch (e) {
    ElMessage.error('获取拉取任务失败')
  } finally {
    missionsLoading.value = false
  }
}

const fetchOwnerOptions = async () => {
  ownersLoading.value = true
  try {
    const res = await http.get('/EVE/asset/pullAssetOwners')
    const data = await res.json()
    ownerOptions.value = Array.isArray(data?.data) ? data.data : []
  } catch (e) {
    ElMessage.error('获取主体列表失败')
  } finally {
    ownersLoading.value = false
  }
}

const openCreateDialog = async () => {
  await fetchOwnerOptions()
  // 如果没有公司权限，确保默认选择 user
  if (!form.value.is_edit_corp_setting_allowed && createForm.value.subject_type === 'corp') {
    createForm.value.subject_type = 'character'
    createForm.value.subject_name = ''
    createForm.value.subject_id = 0
  }
  createDialogVisible.value = true
}

watch(() => createForm.value.subject_type, () => {
  // reset selected name and id when type changes
  createForm.value.subject_name = ''
  createForm.value.subject_id = 0
})

const handleOwnerSelect = (ownerName: string) => {
  const selectedOwner = ownerOptions.value.find(
    o => {
      return o.owner_name === ownerName && o.owner_type === createForm.value.subject_type
    }
  )
  if (selectedOwner) {
    createForm.value.subject_name = selectedOwner.owner_name
    createForm.value.subject_id = selectedOwner.owner_id
  }
}

watch(() => form.value.is_edit_corp_setting_allowed, (newVal) => {
  // 如果权限变为 false 且当前选择的是 corp，自动切换回 user
  if (!newVal && createForm.value.subject_type === 'corp') {
    createForm.value.subject_type = 'character'
    createForm.value.subject_name = ''
    createForm.value.subject_id = 0
  }
})

const handleCloseMission = async (row: Mission) => {
  try {
    const res = await http.post(`/EVE/asset/closeAssetPullMission`, {
      asset_owner_type: row.subject_type,
      asset_owner_id: row.subject_id,
      active: false
    })
    await res.json()
    ElMessage.success('已关闭任务')
    fetchMissions()
  } catch (e) {
    ElMessage.error('关闭任务失败')
  }
}

const handleStartMission = async (row: Mission) => {
  try {
    const res = await http.post(`/EVE/asset/startAssetPullMission`, {
      asset_owner_type: row.subject_type,
      asset_owner_id: row.subject_id,
      active: true
    })
    await res.json()
    ElMessage.success('已启动任务')
    fetchMissions()
  } catch (e) {
    ElMessage.error('启动任务失败')
  }
}

const handlePullMission = async (row: Mission) => {
  try {
    const res = await http.post(`/EVE/asset/pullAssetNow`, {
      asset_owner_type: row.subject_type,
      asset_owner_id: row.subject_id
    })
    await res.json()
    ElMessage.success('已拉取任务')
    fetchMissions()
  } catch (e) {
    ElMessage.error('拉取任务失败')
  }
}

const handleDeleteMission = async (row: Mission) => {
  try {
    const res = await http.delete(`/EVE/asset/deleteAssetPullMission`, {
      asset_owner_type: row.subject_type,
      asset_owner_id: row.subject_id
    })
    await res.json()
    ElMessage.success('已删除任务')
    fetchMissions()
  } catch (e) {
    ElMessage.error('删除任务失败')
  }
}

const handleCreateMission = async () => {
  // 验证权限
  if (createForm.value.subject_type === 'corp' && !form.value.is_edit_corp_setting_allowed) {
    ElMessage.error('您没有权限创建公司资产拉取任务')
    return
  }
  if (!createForm.value.subject_name || !createForm.value.subject_id) {
    ElMessage.warning('请选择主体名称')
    return
  }
  try {
    const payload = {
      asset_owner_id: createForm.value.subject_id,
      asset_owner_type: createForm.value.subject_type,
      active: createForm.value.start_immediately
    }
    const res = await http.post('/EVE/asset/createAssetPullMission', payload)
    await res.json()
    ElMessage.success('创建任务成功')
    createDialogVisible.value = false
    // reset simple fields
    createForm.value.subject_name = ''
    createForm.value.subject_id = 0
    createForm.value.subject_type = 'character'
    createForm.value.start_immediately = true
    fetchMissions()
  } catch (e) {
    ElMessage.error('创建任务失败')
  }
}

// 检查是否可以立刻拉取（距离上次拉取超过5分钟，或者从未拉取过）
const canPullNow = (lastPullTime: string | null | undefined): boolean => {
  if (!lastPullTime) {
    return true // 从未拉取过，可以立刻拉取
  }
  try {
    const lastPull = new Date(lastPullTime).getTime()
    const now = currentTime.value // 使用响应式的时间戳
    
    // 如果解析失败或时间无效，允许拉取
    if (isNaN(lastPull)) {
      return true
    }
    
    // 如果 lastPull 是未来时间（可能是时区问题），允许拉取
    if (lastPull > now) {
      return true
    }
    
    const fiveMinutes = 1 * 60 * 1000
    const elapsed = now - lastPull
    return elapsed >= fiveMinutes
  } catch (e) {
    // 解析失败，允许拉取
    return true
  }
}

// 计算距离可以拉取还有多少时间（秒）
const getRemainingSeconds = (lastPullTime: string | null | undefined): number => {
  if (!lastPullTime) {
    return 0 // 从未拉取过，可以立刻拉取
  }
  try {
    const lastPull = new Date(lastPullTime).getTime()
    const now = currentTime.value // 使用响应式的时间戳
    
    // 如果解析失败或时间无效，返回0（可以拉取）
    if (isNaN(lastPull)) {
      return 0
    }
    
    // 如果 lastPull 是未来时间（可能是时区问题），返回0（可以拉取）
    if (lastPull > now) {
      return 0
    }
    
    const fiveMinutes = 5 * 60 * 1000
    const elapsed = now - lastPull
    const remaining = fiveMinutes - elapsed
    
    // 如果已经超过5分钟，返回0
    if (remaining <= 0) {
      return 0
    }
    
    return Math.ceil(remaining / 1000)
  } catch (e) {
    // 解析失败，返回0（可以拉取）
    return 0
  }
}

// 格式化剩余时间为可读字符串
const formatRemainingTime = (seconds: number): string => {
  if (seconds <= 0) {
    return '可以立刻拉取'
  }
  const minutes = Math.floor(seconds / 60)
  const secs = seconds % 60
  if (minutes > 0) {
    return `还需等待 ${minutes}分${secs}秒`
  }
  return `还需等待 ${secs}秒`
}

onMounted(async () => {
  getIsEditCorpSettingAllowed()
  fetchMissions()
  
  // 每秒更新一次当前时间，用于实时刷新倒计时
  timeUpdateInterval = window.setInterval(() => {
    currentTime.value = Date.now()
  }, 1000)
})

onUnmounted(() => {
  // 清理定时器
  if (timeUpdateInterval !== null) {
    clearInterval(timeUpdateInterval)
    timeUpdateInterval = null
  }
})

</script>

<template>
<el-tabs>
  <el-tab-pane label="资产浏览">

  </el-tab-pane>
  <el-tab-pane label="工业访问许可">
    <AssetViewIndustrypermision />
  </el-tab-pane>
  <el-tab-pane label="资产拉取状态">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
      <div style="font-weight: 600;">当前用户可见任务</div>
      <el-button type="primary" size="small" @click="openCreateDialog">
        <el-icon style="margin-right:4px"><Plus /></el-icon>
        新增拉取任务
      </el-button>
    </div>
    <el-table :data="missions" v-loading="missionsLoading" size="small" border>
      <el-table-column label="主体类型" prop="subject_type" width="100">
        <template #default="{ row }">
          <el-tag type="info" v-if="row.subject_type === 'character'">character</el-tag>
          <el-tag type="warning" v-else>corp</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="主体名称" prop="subject_name" min-width="auto" />
      <el-table-column label="是否启动" prop="is_active" width="110">
        <template #default="{ row }">
          <el-tag type="success" v-if="row.is_active">已启动</el-tag>
          <el-tag type="default" v-else>未启动</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="上次拉取时间" prop="last_pull_time" min-width="100px">
        <template #default="{ row }">
          <span>{{ row.last_pull_time || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="拉取状态" prop="pull_status" width="200px">

      </el-table-column>
      <el-table-column label="操作" width="300px" fixed="right">
        <template #default="{ row }">
          <!-- 立刻拉取 -->
          <!-- 如果上次拉取时间超过5分钟，或者从未拉取过，则可点击 -->
          <el-tooltip :content="canPullNow(row.last_pull_time) ? '可以立刻拉取' : formatRemainingTime(getRemainingSeconds(row.last_pull_time))" placement="top">
            <el-button 
              v-if="canPullNow(row.last_pull_time)" 
              size="small" 
              type="primary" 
              plain 
              @click="handlePullMission(row)"
            >
              <el-icon style="margin-right:4px"><Refresh /></el-icon>
              立刻拉取
            </el-button>
            <el-button 
              v-else 
              size="small" 
              type="primary" 
              plain 
              disabled
            >
              <el-icon style="margin-right:4px"><Refresh /></el-icon>
              立刻拉取
            </el-button>
          </el-tooltip>
          <el-button v-if="row.is_active" size="small" type="warning" plain :disabled="!row.is_active" @click="handleCloseMission(row)">
            <el-icon style="margin-right:4px"><CloseBold /></el-icon>
            关闭
          </el-button>
          <el-button v-else size="small" type="primary" plain @click="handleStartMission(row)">
            <el-icon style="margin-right:4px"><VideoPlay /></el-icon>
            启动
          </el-button>
          <el-button size="small" type="danger" plain @click="handleDeleteMission(row)">
            <el-icon style="margin-right:4px"><Delete /></el-icon>
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="createDialogVisible" title="新增拉取任务" width="420px">
      <el-form :model="createForm" label-width="96px">
        <el-form-item label="主体类型">
          <el-segmented 
            v-model="createForm.subject_type" 
            :options="form.is_edit_corp_setting_allowed ? ['character','corp'] : ['character']" 
          />
        </el-form-item>
        <el-form-item :label="createForm.subject_type === 'character' ? '角色名' : '公司名'">
          <el-select 
            v-model="createForm.subject_name" 
            placeholder="请选择" 
            filterable 
            :loading="ownersLoading" 
            :disabled="createForm.subject_type === 'corp' && !form.is_edit_corp_setting_allowed"
            @change="handleOwnerSelect"
            style="width:100%"
          >
            <el-option
              v-for="item in filteredOwnerOptions"
              :key="item.owner_type + ':' + item.owner_name"
              :label="item.owner_name"
              :value="item.owner_name"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="创建即启动">
          <el-switch v-model="createForm.start_immediately" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div style="display:flex; justify-content:flex-end; gap:8px;">
          <el-button @click="createDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleCreateMission">创建</el-button>
        </div>
      </template>
    </el-dialog>
  </el-tab-pane>
  <el-tab-pane label="配置">
    <el-form :model="form" label-width="auto">
        <el-form-item label="允许拉取公司资产" v-if="form.is_edit_corp_setting_allowed">
          <el-switch
            v-model="form.allow_corporation_asset"
            @change="handleAllowPullCorporationAsset"
          />
        </el-form-item>
        <el-form-item label="公司资产拉取许可" v-if="!form.is_edit_corp_setting_allowed">
          <el-icon color="green" size="18" v-if="form.allow_corporation_asset"><SuccessFilled /></el-icon>
          <el-icon color="red" size="18" v-if="!form.allow_corporation_asset"><CircleCloseFilled /></el-icon>
        </el-form-item>
    </el-form>
  </el-tab-pane>
</el-tabs>

</template>

<style scoped>
</style>