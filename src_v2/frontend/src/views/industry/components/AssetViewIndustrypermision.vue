<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { http } from '@/http'
import { ElMessage } from 'element-plus'
import type { InputNumberInstance } from 'element-plus/lib/components/index.js'
import { Loading, Edit } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()

// ============== 管理员功能 ==============
const haveAdminRole = computed(() => {
    return authStore.user?.roles.includes('admin') || false
})

const selectedUserName = ref<string>('')
const userList = ref<Array<{ userName: string }>>([])
const userListLoading = ref(false)

const fetchUserList = async () => {
    if (!haveAdminRole.value) {
        return
    }
    userListLoading.value = true
    try {
        const res = await http.get('/permission/users')
        const data = await res.json()
        if (data.status !== 200) {
            ElMessage.error(data.message || '获取用户列表失败')
            return
        }
        userList.value = data.data || []
    } catch (error) {
        ElMessage.error('获取用户列表失败')
    } finally {
        userListLoading.value = false
    }
}

// 监听用户选择变化，重新加载权限列表
watch(selectedUserName, () => {
    getUserAllContainerPermission(true)
})

interface HandleSearchItemCountForm {
    item_name: string
    item_id: InputNumberInstance | null
    item_location: string
    container_id: string
    data: any[]
}

const handleSearchItemCountdialogVisible = ref(false)
const handleSearchContainerdialogVisible = ref(false)
const handleSearchItemCountdialogLoading = ref(false)
const handleSearchItemCountForm = ref<HandleSearchItemCountForm>({
    item_name: '',
    item_id: null,
    item_location: '',
    container_id: '',
    data: []
})
const handleSearchItemCountdialog = () => {
    console.log("handleSearchItemCount")
    handleSearchItemCountdialogVisible.value = true
    console.log("handleSearchItemCountdialogVisible", handleSearchItemCountdialogVisible.value)
}

const handleSearchItemCount = async () => {
    const payload: any = {
        item_name: handleSearchItemCountForm.value.item_name
    }
    
    // 如果是管理员且选择了用户，传递 user_name 参数
    if (haveAdminRole.value && selectedUserName.value) {
        payload.user_name = selectedUserName.value
    }
    
    const res = await http.post('/EVE/asset/searchContainerByItemNameAndQuantity', payload)
    const data = await res.json()
    console.log("handleSearchItemCount", data)
    if (data.status !== 200) {
        ElMessage.error(data.message)
        return
    }
    handleSearchItemCountForm.value.data = data.data
    // handleSearchItemCountForm.value.item_location = data.data.item_location
    // handleSearchItemCountForm.value.container_id = data.data.container_id
}

const handleSearchContainer = async () => {
    await getUserAllContainerPermission(true)
    console.log("handleSearchContainer complete")
}

const handleAddIndustrypermision = async (row: any) => {
    handleSearchItemCountdialogLoading.value = true
    if (!row.container.tag) {
        ElMessage.error("请输入标签")
        handleSearchItemCountdialogLoading.value = false
        return
    }
    console.log("handleSearchItemCountdialogLoading", handleSearchItemCountdialogLoading.value)
    const payload: any = {
        container: row.container,
        asset: row.asset,
        structure: row.structure,
        system: row.system,
        tag: row.container.tag
    }
    
    // 如果是管理员且选择了用户，传递 user_name 参数
    if (haveAdminRole.value && selectedUserName.value) {
        payload.user_name = selectedUserName.value
    }
    
    const res = await http.post('/EVE/industry/addIndustrypermision', payload)
    const data = await res.json()
    if (data.status !== 200) {
        ElMessage.error(data.message)
        handleSearchItemCountdialogLoading.value = false
        return
    }
    ElMessage.success(data.message)
    handleSearchItemCountdialogLoading.value = false
    handleSearchItemCountdialogVisible.value = false
    await getUserAllContainerPermission(true)
}

const userContainerPermission = ref([])
const userContainerPermissionLoading = ref(false)
const getUserAllContainerPermission = async ( force_refresh = false ) => {
    console.log("getUserAllContainerPermission in")
    userContainerPermissionLoading.value = true
    const payload: any = {
        force_refresh: force_refresh
    }
    
    // 如果是管理员且选择了用户，传递 user_name 参数
    if (haveAdminRole.value && selectedUserName.value) {
        payload.user_name = selectedUserName.value
    }
    
    const res = await http.post('/EVE/industry/getUserAllContainerPermission', payload)
    const data = await res.json()
    console.log("getUserAllContainerPermission data", data)
    if (data.status !== 200) {
        userContainerPermissionLoading.value = false
        ElMessage.error(data.message)
        return
    }
    console.log("getUserAllContainerPermission data.data", data.data)
    userContainerPermission.value = data.data
    userContainerPermissionLoading.value = false
}

const handleDeleteIndustrypermision = async (row: any) => {
    const payload: any = {
        asset_owner_id: row.asset_owner_id,
        asset_container_id: row.asset_container_id
    }
    
    // 如果是管理员且选择了用户，传递 user_name 参数
    if (haveAdminRole.value && selectedUserName.value) {
        payload.user_name = selectedUserName.value
    }
    
    const res = await http.post('/EVE/industry/deleteIndustrypermision', payload)
    const data = await res.json()
    if (data.status !== 200) {
        ElMessage.error(data.message)
        return
    }
    ElMessage.success(data.message)
    await getUserAllContainerPermission(true)
    console.log("handleDeleteIndustrypermision", row)
}

const handleViewContent = (row: any) => {
    console.log("handleViewContent", row)
}

// 编辑标签相关状态
const editTagDialogVisible = ref(false)
const editingRow = ref<any>(null)
const newTag = ref<string>('')
const editTagLoading = ref(false)

const handleEditTag = (row: any) => {
    editingRow.value = row
    newTag.value = row.tag || ''
    editTagDialogVisible.value = true
}

const handleSaveTag = async () => {
    if (!editingRow.value) {
        return
    }
    
    editTagLoading.value = true
    const payload: any = {
        asset_owner_id: editingRow.value.asset_owner_id,
        asset_container_id: editingRow.value.asset_container_id,
        tag: newTag.value
    }
    
    // 如果是管理员且选择了用户，传递 user_name 参数
    if (haveAdminRole.value && selectedUserName.value) {
        payload.user_name = selectedUserName.value
    }
    
    try {
        const res = await http.post('/EVE/industry/updateContainerPermissionTag', payload)
        const data = await res.json()
        if (data.status !== 200) {
            ElMessage.error(data.message)
            return
        }
        ElMessage.success(data.message)
        editTagDialogVisible.value = false
        await getUserAllContainerPermission(true)
    } catch (error) {
        ElMessage.error('修改标签失败')
    } finally {
        editTagLoading.value = false
    }
}

// 同步许可到计划配置
const syncPermissionToPlanConfigLoading = ref(false)
const handleSyncPermissionToPlanConfig = async () => {
    syncPermissionToPlanConfigLoading.value = true
    const payload: any = {}
    
    // 如果是管理员且选择了用户，传递 user_name 参数
    if (haveAdminRole.value && selectedUserName.value) {
        payload.user_name = selectedUserName.value
    }
    
    try {
        const res = await http.post('/EVE/industry/syncPermissionToPlanConfig', payload)
        const data = await res.json()
        if (data.status !== 200) {
            ElMessage.error(data.message || '同步失败')
            return
        }
        
        // 显示详细的同步结果
        const result = data.data || {}
        const created = result.created || 0
        const updated = result.updated || 0
        const deleted = result.deleted || 0
        
        let message = '同步完成'
        if (created > 0 || updated > 0 || deleted > 0) {
            const parts: string[] = []
            if (created > 0) parts.push(`创建 ${created} 个`)
            if (updated > 0) parts.push(`更新 ${updated} 个`)
            if (deleted > 0) parts.push(`删除 ${deleted} 个`)
            message = `同步完成：${parts.join('，')}配置`
        } else {
            message = '同步完成：无需更改'
        }
        
        ElMessage.success(message)
        // 可选：刷新权限列表
        await getUserAllContainerPermission(true)
    } catch (error: any) {
        ElMessage.error(error.message || '同步失败')
    } finally {
        syncPermissionToPlanConfigLoading.value = false
    }
}


interface TypeItem {
    value: string
}
const TypeSuggestions = ref<TypeItem[]>([])
const fetchTypeSuggestions = async (queryString: string, cb: (suggestions: TypeItem[]) => void) => {
    const res = await http.post('/EVE/industry/getTypeSuggestionsList', {
        type_name: queryString
    })
    const data = await res.json()

    TypeSuggestions.value = data.data
    const results = queryString
    ? TypeSuggestions.value
    : []

    cb(results)
}

onMounted(async () => {
    if (haveAdminRole.value) {
        await fetchUserList()
    }
    await getUserAllContainerPermission()
})
</script>
<template>
    <div style="display: flex; flex-direction: horizontal; gap: 10px;">
        <div style="min-width: 300px;">
            <!-- 管理员用户选择器 -->
            <div v-if="haveAdminRole" style="margin-bottom: 16px; padding: 16px; background-color: #f5f7fa; border-radius: 4px; border: 1px solid #e4e7ed;">
                <el-form-item label="选择用户" style="margin-bottom: 0;">
                    <el-select
                        v-model="selectedUserName"
                        placeholder="选择用户（留空显示当前用户）"
                        filterable
                        clearable
                        :loading="userListLoading"
                        style="width: 300px;"
                    >
                        <el-option
                            v-for="user in userList"
                            :key="user.userName"
                            :label="user.userName"
                            :value="user.userName"
                        />
                    </el-select>
                </el-form-item>
            </div>
            <el-button type="primary" @click="handleSearchItemCountdialog">搜索物品数目新增许可</el-button>
            <el-button type="primary" @click="handleSearchContainer">检索容器新增许可</el-button>
            <el-button type="primary" @click="handleSyncPermissionToPlanConfig" :loading="syncPermissionToPlanConfigLoading">同步许可到计划配置</el-button>
            <el-table
                :data="userContainerPermission"
                border
                v-loading="userContainerPermissionLoading"
                show-overflow-tooltip
            >
                <el-table-column label="资产类型" prop="owner_type" />
                <el-table-column label="所有者" prop="owner_name" width="200"/>
                <el-table-column label="容器ID" prop="asset_container_id" />
                <el-table-column label="建筑" prop="structure_name" width="250"/>
                <el-table-column label="星系" prop="system_name" />
                <el-table-column label="标签" prop="tag" width="200" sortable>
                    <template #default="scope">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span>{{ scope.row.tag }}</span>
                            <el-button 
                                size="small" 
                                :icon="Edit"
                                @click="handleEditTag(scope.row)"
                            />
                        </div>
                    </template>
                </el-table-column>
                <el-table-column label="操作" width="200">
                    <template #default="scope">
                        <el-button type="primary" @click="handleDeleteIndustrypermision(scope.row)">删除</el-button>
                        <!-- <el-button type="primary" @click="handleViewContent(scope.row)">查看内容</el-button> -->
                    </template>
                </el-table-column>
            </el-table>
        </div>
    </div>

    <el-dialog
        v-model="handleSearchItemCountdialogVisible"
        title="搜索物品新增许可"
        width="70%"
    >
        <el-form :model="handleSearchItemCountForm" label-width="120px">
            <el-form-item label="物品名">
                <el-autocomplete
                    v-model="handleSearchItemCountForm.item_name"
                    :fetch-suggestions="fetchTypeSuggestions"
                    value-key="value"
                />
            </el-form-item>
            <el-button type="primary" @click="handleSearchItemCount">
                搜索
            </el-button>
            <el-form-item label="搜索结果">
                <el-table
                    :data="handleSearchItemCountForm.data"
                    border
                    v-loading="handleSearchItemCountdialogLoading"
                    max-height="700px"
                >
                    <el-table-column label="名称" prop="asset.type_name" />
                    <el-table-column label="数量" prop="asset.quantity" />
                    <el-table-column label="建筑" prop="structure.structure_name" />
                    <el-table-column label="容器ID" prop="container.item_id" />
                    <el-table-column label="容器位置" prop="container.location_flag" />
                    <el-table-column label="标签" prop="container.tag">
                        <template #default="scope">
                            <el-input v-model="scope.row.container.tag" placeholder="请输入标签" />
                        </template>
                    </el-table-column>
                    <el-table-column label="操作" width="100">
                        <template #default="scope">
                            <el-button type="primary" @click="handleAddIndustrypermision(scope.row)">新增</el-button>
                        </template>
                    </el-table-column>
                </el-table>
            </el-form-item>
        </el-form>
    </el-dialog>

    <el-dialog
        v-model="editTagDialogVisible"
        title="修改标签"
        width="400px"
    >
        <el-form :model="{ tag: newTag }" label-width="80px">
            <el-form-item label="标签">
                <el-input 
                    v-model="newTag" 
                    placeholder="请输入标签"
                    maxlength="100"
                    show-word-limit
                />
            </el-form-item>
        </el-form>
        <template #footer>
            <span class="dialog-footer">
                <el-button @click="editTagDialogVisible = false">取消</el-button>
                <el-button 
                    type="primary" 
                    @click="handleSaveTag"
                    :loading="editTagLoading"
                >
                    确定
                </el-button>
            </span>
        </template>
    </el-dialog>
</template>