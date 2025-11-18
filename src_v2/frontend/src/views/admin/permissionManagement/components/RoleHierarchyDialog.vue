<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { http } from '@/http'
import type { Role } from '../types'

interface Props {
  modelValue: boolean
  role: Role | null
}

interface Emits {
  (e: 'update:modelValue', value: boolean): void
  (e: 'refresh'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const dialogVisible = ref(false)
const parentRoles = ref<string[]>([])
const childRoles = ref<string[]>([])
const hierarchyForm = ref({
  selectedParentRoles: [] as string[],
  selectedChildRoles: [] as string[]
})
const roles = ref<Role[]>([])

watch(() => props.modelValue, (val) => {
  dialogVisible.value = val
  if (val && props.role) {
    loadHierarchy()
    loadRoles()
  }
})

watch(dialogVisible, (val) => {
  emit('update:modelValue', val)
})

const loadHierarchy = async () => {
  if (!props.role) return
  
  try {
    const response = await http.get(`/permission/roles/${props.role.roleName}/hierarchy`)
    if (response.ok) {
      const data = await response.json()
      parentRoles.value = data.data.parentRoles || []
      childRoles.value = data.data.childRoles || []
      hierarchyForm.value = {
        selectedParentRoles: [],
        selectedChildRoles: []
      }
    } else {
      const error = await response.json()
      ElMessage.error(error.message || '加载角色层级关系失败')
    }
  } catch (error: any) {
    ElMessage.error(error?.message || '加载角色层级关系失败')
  }
}

const loadRoles = async () => {
  try {
    const response = await http.get('/permission/roles')
    if (response.ok) {
      const data = await response.json()
      roles.value = data.data || []
    }
  } catch (error: any) {
    // 静默失败
  }
}

const handleAddParentRoles = async () => {
  if (!props.role || hierarchyForm.value.selectedParentRoles.length === 0) return
  
  try {
    const promises = hierarchyForm.value.selectedParentRoles.map(parentRoleName =>
      http.post('/permission/roles/hierarchy', {
        parentRoleName: parentRoleName,
        childRoleName: props.role!.roleName
      })
    )
    
    await Promise.all(promises)
    ElMessage.success('父角色添加成功')
    hierarchyForm.value.selectedParentRoles = []
    loadHierarchy()
    emit('refresh')
  } catch (error: any) {
    ElMessage.error(error?.message || '添加父角色失败')
  }
}

const handleAddChildRoles = async () => {
  if (!props.role || hierarchyForm.value.selectedChildRoles.length === 0) return
  
  try {
    const promises = hierarchyForm.value.selectedChildRoles.map(childRoleName =>
      http.post('/permission/roles/hierarchy', {
        parentRoleName: props.role!.roleName,
        childRoleName: childRoleName
      })
    )
    
    await Promise.all(promises)
    ElMessage.success('子角色添加成功')
    hierarchyForm.value.selectedChildRoles = []
    loadHierarchy()
    emit('refresh')
  } catch (error: any) {
    ElMessage.error(error?.message || '添加子角色失败')
  }
}

const handleDeleteHierarchy = async (parentRole: string, childRole: string) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除角色层级关系 "${parentRole}" -> "${childRole}" 吗？`,
      '删除层级关系',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    const response = await http.delete('/permission/roles/hierarchy', {
      hierarchyPairs: [[parentRole, childRole]]
    })
    
    if (response.ok) {
      ElMessage.success('角色层级关系删除成功')
      loadHierarchy()
      emit('refresh')
    } else {
      const error = await response.json()
      ElMessage.error(error.message || '删除角色层级关系失败')
    }
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error?.message || '删除角色层级关系失败')
    }
  }
}
</script>

<template>
  <el-dialog v-model="dialogVisible" :title="`管理角色层级关系 - ${role?.roleName}`" width="900px">
    <div class="hierarchy-content">
      <!-- 当前角色信息 -->
      <div class="current-role-info">
        <el-card shadow="never" class="role-card">
          <template #header>
            <div class="card-header">
              <span class="role-name">{{ role?.roleName }}</span>
              <el-tag type="info" size="small">当前角色</el-tag>
            </div>
          </template>
          <div class="role-description">
            {{ role?.roleDescription || '暂无描述' }}
          </div>
        </el-card>
      </div>

      <!-- 父角色区域 -->
      <el-card shadow="never" class="hierarchy-card">
        <template #header>
          <div class="card-header">
            <span>父角色 ({{ parentRoles.length }})</span>
          </div>
        </template>
        <div class="hierarchy-tags">
          <el-tag
            v-for="parentRole in parentRoles"
            :key="parentRole"
            closable
            @close="handleDeleteHierarchy(parentRole, role!.roleName)"
            type="success"
            size="large"
            class="hierarchy-tag"
          >
            {{ parentRole }}
          </el-tag>
          <div v-if="parentRoles.length === 0" class="empty-text">暂无父角色</div>
        </div>
        <el-divider />
        <div class="add-hierarchy-section">
          <el-select
            v-model="hierarchyForm.selectedParentRoles"
            placeholder="选择多个父角色（支持多选）"
            filterable
            multiple
            style="width: 100%"
          >
            <el-option
              v-for="r in roles.filter(r => r.roleName !== role?.roleName && !parentRoles.includes(r.roleName))"
              :key="r.roleName"
              :label="r.roleName"
              :value="r.roleName"
            />
          </el-select>
          <el-button
            type="primary"
            :disabled="hierarchyForm.selectedParentRoles.length === 0"
            @click="handleAddParentRoles"
            style="margin-top: 10px"
          >
            批量添加父角色
          </el-button>
        </div>
      </el-card>

      <!-- 子角色区域 -->
      <el-card shadow="never" class="hierarchy-card">
        <template #header>
          <div class="card-header">
            <span>子角色 ({{ childRoles.length }})</span>
          </div>
        </template>
        <div class="hierarchy-tags">
          <el-tag
            v-for="childRole in childRoles"
            :key="childRole"
            closable
            @close="handleDeleteHierarchy(role!.roleName, childRole)"
            type="warning"
            size="large"
            class="hierarchy-tag"
          >
            {{ childRole }}
          </el-tag>
          <div v-if="childRoles.length === 0" class="empty-text">暂无子角色</div>
        </div>
        <el-divider />
        <div class="add-hierarchy-section">
          <el-select
            v-model="hierarchyForm.selectedChildRoles"
            placeholder="选择多个子角色（支持多选）"
            filterable
            multiple
            style="width: 100%"
          >
            <el-option
              v-for="r in roles.filter(r => r.roleName !== role?.roleName && !childRoles.includes(r.roleName))"
              :key="r.roleName"
              :label="r.roleName"
              :value="r.roleName"
            />
          </el-select>
          <el-button
            type="primary"
            :disabled="hierarchyForm.selectedChildRoles.length === 0"
            @click="handleAddChildRoles"
            style="margin-top: 10px"
          >
            批量添加子角色
          </el-button>
        </div>
      </el-card>
    </div>
    <template #footer>
      <el-button @click="dialogVisible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.hierarchy-content {
  max-height: 600px;
  overflow-y: auto;
}

.current-role-info {
  margin-bottom: 20px;
}

.role-card {
  border: 2px solid #409eff;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.role-name {
  font-weight: bold;
  font-size: 16px;
}

.role-description {
  color: #666;
  font-size: 14px;
}

.hierarchy-card {
  margin-bottom: 20px;
}

.hierarchy-tags {
  min-height: 60px;
  padding: 10px 0;
}

.hierarchy-tag {
  margin-right: 8px;
  margin-bottom: 8px;
  font-size: 14px;
  padding: 0 12px;
  height: 32px;
  line-height: 32px;
}

.add-hierarchy-section {
  padding-top: 10px;
}

.empty-text {
  color: #999;
  font-size: 14px;
  padding: 10px 0;
}
</style>

