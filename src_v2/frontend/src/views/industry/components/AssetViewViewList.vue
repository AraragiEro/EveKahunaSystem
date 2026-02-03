<script setup lang="ts">
import { ref, onMounted, computed, watch, nextTick } from 'vue'
import { http } from '@/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Share, Setting, Delete, View, Plus, Loading } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import DefaultView from './assetViewComponent/defaultView.vue'
import SellView from './assetViewComponent/sellView.vue'
import WatchView from './assetViewComponent/watchView.vue'
import StatisticsView from './assetViewComponent/statisticsView.vue'

const authStore = useAuthStore()

// ============== 资产视图缓存 ==============
// 缓存数据结构
interface AssetViewCacheData {
    data: any  // 视图数据（对象或数组）
    view_type: string  // 视图类型
    config: any  // 视图配置
    expireTime: number  // 过期时间戳
}

// 缓存键前缀
const ASSET_VIEW_CACHE_PREFIX = 'asset_view_data_'
// 缓存有效期：15分钟（900,000毫秒）
const CACHE_EXPIRE_TIME = 15 * 60 * 1000

// 计算15分钟后的过期时间戳
const getCacheExpireTime = (): number => {
    return Date.now() + CACHE_EXPIRE_TIME
}

// 检查缓存是否有效
const isCacheValid = (cacheData: AssetViewCacheData | null): boolean => {
    if (!cacheData) {
        return false
    }
    const now = Date.now()
    return cacheData.expireTime > now
}

// 保存视图数据到 localStorage
const saveAssetViewCache = (sid: string, data: any, view_type: string, config: any) => {
    try {
        const cacheData: AssetViewCacheData = {
            data,
            view_type,
            config,
            expireTime: getCacheExpireTime()
        }
        const key = `${ASSET_VIEW_CACHE_PREFIX}${sid}`
        localStorage.setItem(key, JSON.stringify(cacheData))
        console.log(`资产视图缓存已保存: ${key}`)
    } catch (error) {
        console.error(`保存资产视图缓存失败 ${sid}:`, error)
    }
}

// 从 localStorage 加载视图数据
const loadAssetViewCache = (sid: string): AssetViewCacheData | null => {
    try {
        const key = `${ASSET_VIEW_CACHE_PREFIX}${sid}`
        const data = localStorage.getItem(key)
        if (data) {
            const cacheData = JSON.parse(data) as AssetViewCacheData
            if (isCacheValid(cacheData)) {
                console.log(`从缓存加载资产视图: ${key}`)
                return cacheData
            } else {
                // 缓存已过期，删除
                localStorage.removeItem(key)
                console.log(`资产视图缓存已过期，已删除: ${key}`)
            }
        }
    } catch (error) {
        console.error(`加载资产视图缓存失败 ${sid}:`, error)
    }
    return null
}

// ============== 资产视图组件映射 ==============
// 未来添加新组件时，只需在此处添加映射关系即可
const viewComponentMap: Record<string, any> = {
    'default': DefaultView,
    'sell': SellView,
    'watch': WatchView,
    'statistics': StatisticsView,
    // 未来可以轻松添加更多组件类型，例如：
    // 'buy': BuyView,
    // 'manufacture': ManufactureView,
    // 'research': ResearchView,
}

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

// 监听用户选择变化，重新加载资产视图列表
watch(selectedUserName, () => {
    getAssetViewList()
})

const assetViewList = ref<any[]>([])
const getAssetViewList = async () => {
    const params: any = {}
    if (haveAdminRole.value && selectedUserName.value) {
        params.user_name = selectedUserName.value
    }
    const res = await http.get('/EVE/asset/getAssetViewList', params)
    const data = await res.json()
    if (data.status !== 200) {
        ElMessage.error(data.message || '获取资产视图列表失败')
        return
    }
    assetViewList.value = data.data
}

const assetViewDialogVisible = ref(false)
const assetViewDialogLoading = ref(false)
const assetView = ref<any[]>([])
const AssetViewDialogSid = ref('')
const assetViewLastUpdateTime = ref<number>(Date.now())

// 刷新资产视图数据（强制刷新，跳过缓存）
const refreshAssetView = async () => {
    if (!AssetViewDialogSid.value) return

    assetViewDialogLoading.value = true

    try {
        // 强制刷新，从API获取数据
        const res = await http.get('/EVE/asset/getAssetViewData', {
            asset_view_sid: AssetViewDialogSid.value
        })
        const data = await res.json()
        assetViewDialogLoading.value = false

        if (data.status !== 200) {
            ElMessage.error(data.message)
            return
        }

        // 处理数据格式
        let processedData: any
        // 统计视图保持对象格式，其他视图转换为数组
        if (data.view_type === 'statistics') {
            processedData = data.data || {}
            assetView.value = processedData
        } else {
            // 后端返回的是对象（字典），需要转换为数组
            processedData = Object.values(data.data || {})
            assetView.value = processedData
        }

        AssetViewDialogType.value = data.view_type
        AssetViewDialogConfig.value = data.config

        // 更新最后更新时间
        assetViewLastUpdateTime.value = Date.now()

        // 保存到缓存
        saveAssetViewCache(AssetViewDialogSid.value, processedData, data.view_type, data.config)

        ElMessage.success('刷新成功')
    } catch (error) {
        assetViewDialogLoading.value = false
        ElMessage.error('刷新失败')
    }
}

const handleViewAssetView = async (assetViewItem: any) => {
    assetViewDialogVisible.value = true
    assetViewDialogLoading.value = true

    // 先尝试从缓存加载数据
    const cachedData = loadAssetViewCache(assetViewItem.sid)
    if (cachedData) {
        // 缓存有效，直接使用缓存数据
        assetViewDialogLoading.value = false
        console.log("handleViewAssetView 使用缓存数据", cachedData)
        // 统计视图保持对象格式，其他视图转换为数组
        if (cachedData.view_type === 'statistics') {
            assetView.value = cachedData.data || {}
        } else {
            // 如果缓存的数据已经是数组，直接使用；否则转换为数组
            assetView.value = Array.isArray(cachedData.data)
                ? cachedData.data
                : Object.values(cachedData.data || {})
        }
        AssetViewDialogType.value = cachedData.view_type
        AssetViewDialogConfig.value = cachedData.config
        AssetViewDialogSid.value = assetViewItem.sid
        // 更新最后更新时间（使用缓存时，使用当前时间）
        assetViewLastUpdateTime.value = Date.now()
        return
    }

    // 缓存无效或不存在，从API获取数据
    const res = await http.get('/EVE/asset/getAssetViewData', {
        asset_view_sid: assetViewItem.sid
    })
    const data = await res.json()
    assetViewDialogLoading.value = false
    if (data.status !== 200) {
        ElMessage.error(data.message)
        return
    }
    console.log("handleViewAssetView data", data)

    // 处理数据格式
    let processedData: any
    // 统计视图保持对象格式，其他视图转换为数组
    if (data.view_type === 'statistics') {
        processedData = data.data || {}
        assetView.value = processedData
    } else {
        // 后端返回的是对象（字典），需要转换为数组
        processedData = Object.values(data.data || {})
        assetView.value = processedData
    }

    AssetViewDialogType.value = data.view_type
    AssetViewDialogConfig.value = data.config
    AssetViewDialogSid.value = assetViewItem.sid

    // 更新最后更新时间
    assetViewLastUpdateTime.value = Date.now()

    // 保存到缓存
    saveAssetViewCache(assetViewItem.sid, processedData, data.view_type, data.config)
}

// ============== 资产视图设置对话框 ==============
const assetViewSetDialogVisible = ref(false)
const AssetViewDialogType = ref('default')
const AssetViewDialogConfig = ref({
    price_base: "jita_sell",
    percent: 1.0
})

// 根据类型动态获取对应的组件
const currentViewComponent = computed(() => {
    return viewComponentMap[AssetViewDialogType.value] || DefaultView
})
const assetViewSetForm = ref({
    sid: '',
    tag: '',
    public: false,
    view_type: 'default',
    config: {
        price_base: "jita_sell",
        percent: 1.0
    },
    filter_groups: [
        {
            index: 0,
            filter_type: '',
            filter_value: ''
        }
    ],
    asset_container_id_list: [] as Array<{ container_id: number, owner_id: number, location_flag: string | null }>
})

// ============== 过滤类型选项 ==============
const filterTypeOptions = ref([
    { value: 'group', label: 'group' },
    { value: 'meta', label: 'meta' },
    { value: 'marketGroup', label: 'marketGroup' },
    { value: 'category', label: 'category' },
    { value: 'type_id', label: 'type_id' },
])

// ============== location_flag 固定选项列表 ==============
const locationFlagOptions = ref([
    { value: 'CorpSAG1', label: '公司机库1' },
    { value: 'CorpSAG2', label: '公司机库2' },
    { value: 'CorpSAG3', label: '公司机库3' },
    { value: 'CorpSAG4', label: '公司机库4' },
    { value: 'CorpSAG5', label: '公司机库5' },
    { value: 'CorpSAG6', label: '公司机库6' },
    { value: 'CorpSAG7', label: '公司机库7' },
])

// ============== 过滤组管理 ==============
const current_filter_type = ref('')

const before_fetch_filter_suggestions = (filter_type: string) => {
    console.log("before_fetch_filter_suggestions filter_type", filter_type)
    current_filter_type.value = filter_type
}

interface TypeItem {
    value: string
}

const fetchFilterSuggestions = async (queryString: string, cb: (suggestions: TypeItem[]) => void) => {
    if (current_filter_type.value === 'location_flag') {
        // location_flag 使用固定选项列表
        const results = queryString
            ? locationFlagOptions.value.filter(item =>
                item.value.toLowerCase().indexOf(queryString.toLowerCase()) === 0
            ).map(item => ({ value: item.value }))
            : locationFlagOptions.value.map(item => ({ value: item.value }))
        cb(results)
        return
    }

    if (current_filter_type.value === 'type_id') {
        // type_id 使用 getTypeSuggestionsList API
        const res = await http.post('/EVE/industry/getTypeSuggestionsList', {
            type_name: queryString
        })
        const data = await res.json()
        const results = queryString ? (data.data || []) : []
        cb(results)
        return
    }

    // group, meta, marketGroup, category 使用 getGroupSuggestions API
    if (['group', 'meta', 'marketGroup', 'category'].includes(current_filter_type.value)) {
        const res = await http.post('/EVE/industry/getGroupSuggestions', {
            assign_type: current_filter_type.value,
            query: queryString
        })
        const data = await res.json()
        const results = queryString ? (data.data || []) : []
        cb(results)
        return
    }

    // 默认返回空数组
    cb([])
}

const add_filter_group = () => {
    assetViewSetForm.value.filter_groups.push({
        index: assetViewSetForm.value.filter_groups.length,
        filter_type: '',
        filter_value: ''
    })
}

const delete_filter_group = (index: number) => {
    assetViewSetForm.value.filter_groups.splice(index, 1)
    // 重新索引
    assetViewSetForm.value.filter_groups.forEach((group, idx) => {
        group.index = idx
    })
}

// ============== 设置资产视图 ==============
const handleSetAssetView = (assetViewItem: any) => {
    console.log("handleSetAssetView assetViewItem", assetViewItem)
    assetViewSetDialogVisible.value = true
    assetViewSetForm.value.sid = assetViewItem.sid
    assetViewSetForm.value.tag = assetViewItem.tag || ''
    assetViewSetForm.value.public = assetViewItem.public || false
    assetViewSetForm.value.view_type = assetViewItem.view_type || 'default'
    assetViewSetForm.value.config = assetViewItem.config || {
        price_base: "jita_sell",
        percent: 1.0
    }

    // 将后端返回的 filter 数组转换为 filter_groups 格式
    const filters = assetViewItem.filter || []
    if (filters.length === 0) {
        assetViewSetForm.value.filter_groups = [{
            index: 0,
            filter_type: '',
            filter_value: ''
        }]
    } else {
        assetViewSetForm.value.filter_groups = filters.map((f: any, idx: number) => ({
            index: idx,
            filter_type: f.type || '',
            filter_value: f.value || ''
        }))
    }

    // 设置容器ID列表
    assetViewSetForm.value.asset_container_id_list = assetViewItem.asset_container_id_list || []
}

const saveAssetViewConfig = async () => {
    // 将 filter_groups 转换回 filter 数组格式
    const filters = assetViewSetForm.value.filter_groups
        .filter(group => group.filter_type && group.filter_value)
        .map(group => ({
            type: group.filter_type,
            value: group.filter_value
        }))

    const payload: any = {
        sid: assetViewSetForm.value.sid,
        tag: assetViewSetForm.value.tag,
        public: assetViewSetForm.value.public,
        filter: filters,
        view_type: assetViewSetForm.value.view_type,
        config: assetViewSetForm.value.config
    }

    // 如果是管理员且选择了用户，传递 user_name 参数
    if (haveAdminRole.value && selectedUserName.value) {
        payload.user_name = selectedUserName.value
    }

    const res = await http.post('/EVE/asset/saveAssetViewConfig', payload)
    const data = await res.json()
    if (data.status !== 200) {
        ElMessage.error(data.message)
        return
    }
    ElMessage.success(data.message || '保存成功')
    assetViewSetDialogVisible.value = false
    await getAssetViewList()
}

// ============== 复制公开链接 ==============
const copyPublicLink = async (assetViewItem: any) => {
    const publicUrl = `${window.location.origin}/storage/${assetViewItem.sid}`

    try {
        await navigator.clipboard.writeText(publicUrl)
        ElMessage.success('公开链接已复制到剪贴板')
    } catch (error) {
        // 如果 clipboard API 不可用，使用备用方法
        const textArea = document.createElement('textarea')
        textArea.value = publicUrl
        textArea.style.position = 'fixed'
        textArea.style.opacity = '0'
        document.body.appendChild(textArea)
        textArea.select()
        try {
            document.execCommand('copy')
            ElMessage.success('公开链接已复制到剪贴板')
        } catch (err) {
            ElMessage.error('复制失败，请手动复制链接')
        }
        document.body.removeChild(textArea)
    }
}

// ============== 删除资产视图 ==============
const handleDeleteAssetView = async (assetViewItem: any) => {
    try {
        await ElMessageBox.confirm(
            `确定要删除资产视图 "${assetViewItem.tag || assetViewItem.sid}" 吗？`,
            '确认删除',
            {
                confirmButtonText: '确定',
                cancelButtonText: '取消',
                type: 'warning',
            }
        )

        const payload: any = {
            sid: assetViewItem.sid
        }

        // 如果是管理员且选择了用户，传递 user_name 参数
        if (haveAdminRole.value && selectedUserName.value) {
            payload.user_name = selectedUserName.value
        }

        const res = await http.delete('/EVE/asset/deleteAssetView', payload)
        const data = await res.json()
        if (data.status !== 200) {
            ElMessage.error(data.message || '删除失败')
            return
        }
        ElMessage.success(data.message || '删除成功')
        await getAssetViewList()
    } catch (error: any) {
        ElMessage.error('删除失败：' + (error?.message || '未知错误'))
    }
}

// ============== 增加监控 ==============
const addMonitorDialogVisible = ref(false)
const selectedContainers = ref<Array<{ container_id: number, owner_id: number }>>([])
const newViewTag = ref('')
const containerPermissionList = ref<any[]>([])
const containerPermissionLoading = ref(false)

interface ContainerPermissionItem {
    asset_container_id: number
    asset_owner_id: number
    structure_id: number
    structure_name: string
    system_id: number
    system_name: string
    owner_type: string
    owner_name: string
    tag: string
}

const fetchContainerPermissionList = async () => {
    containerPermissionLoading.value = true
    const payload: any = {
        force_refresh: false
    }

    // 如果是管理员且选择了用户，传递 user_name 参数
    if (haveAdminRole.value && selectedUserName.value) {
        payload.user_name = selectedUserName.value
    }

    try {
        const res = await http.post('/EVE/industry/getUserAllContainerPermission', payload)
        const data = await res.json()
        if (data.status !== 200) {
            ElMessage.error(data.message || '获取容器许可列表失败')
            containerPermissionList.value = []
            return
        }
        // 使用数组替换确保响应式更新
        containerPermissionList.value = Array.isArray(data.data) ? [...data.data] : []
        console.log("fetchContainerPermissionList containerPermissionList", containerPermissionList.value)
    } catch (error) {
        ElMessage.error('获取容器许可列表失败')
    } finally {
        containerPermissionLoading.value = false
    }
}

const handleOpenAddMonitorDialog = async () => {
    selectedContainers.value = []
    newViewTag.value = ''
    // 在打开对话框前设置加载状态，确保用户立即看到加载提示
    containerPermissionLoading.value = true
    addMonitorDialogVisible.value = true
    // 等待对话框渲染完成后再加载数据
    await nextTick()
    await fetchContainerPermissionList()
    // 确保表格数据更新后清除选择状态
    await nextTick()
    if (containerTableRef.value) {
        containerTableRef.value.clearSelection()
    }
}

const handleSelectAll = () => {
    containerPermissionList.value.forEach((row: any) => {
        containerTableRef.value?.toggleRowSelection(row, true)
    })
}

const handleUnselectAll = () => {
    containerTableRef.value?.clearSelection()
}

const containerTableRef = ref()

const handleTableSelectionChange = (selection: any[]) => {
    selectedContainers.value = selection.map(item => ({
        container_id: item.asset_container_id,
        owner_id: item.asset_owner_id
    }))
}

const handleToggleSelection = (containerId: number, ownerId: number) => {
    const index = selectedContainers.value.findIndex(
        item => item.container_id === containerId && item.owner_id === ownerId
    )
    if (index > -1) {
        selectedContainers.value.splice(index, 1)
    } else {
        selectedContainers.value.push({ container_id: containerId, owner_id: ownerId })
    }
}

const handleAddMonitor = async () => {
    if (!newViewTag.value || newViewTag.value.trim() === '') {
        ElMessage.warning('请输入标签')
        return
    }

    if (selectedContainers.value.length === 0) {
        ElMessage.warning('请至少选择一个容器')
        return
    }

    const payload: any = {
        container_list: selectedContainers.value,
        tag: newViewTag.value.trim()
    }

    // 如果是管理员且选择了用户，传递 user_name 参数
    if (haveAdminRole.value && selectedUserName.value) {
        payload.user_name = selectedUserName.value
    }

    try {
        const res = await http.post('/EVE/asset/createAssetView', payload)
        const data = await res.json()
        if (data.status !== 200) {
            ElMessage.error(data.message)
            return
        }
        ElMessage.success(data.message || '创建监控成功')
        addMonitorDialogVisible.value = false
        selectedContainers.value = []
        newViewTag.value = ''
        await getAssetViewList()
    } catch (error) {
        ElMessage.error('创建监控失败')
    }
}

// ============== 管理容器 ==============
const manageContainerDialogVisible = ref(false)
const manageContainerSelected = ref<Array<{ container_id: number, owner_id: number, location_flag: string | null }>>([])
const manageContainerList = ref<any[]>([])
const manageContainerLoading = ref(false)
const manageContainerTableRef = ref()

const isSettingManageContainerSelection = ref(false)

const handleOpenManageContainerDialog = async () => {
    // 先保存当前选中的容器列表，确保 location_flag 字段存在
    manageContainerSelected.value = assetViewSetForm.value.asset_container_id_list
        ? assetViewSetForm.value.asset_container_id_list.map(item => ({
            container_id: item.container_id,
            owner_id: item.owner_id,
            location_flag: item.location_flag ?? null
        }))
        : []
    // 在打开对话框前设置加载状态，确保用户立即看到加载提示
    manageContainerLoading.value = true
    // 打开对话框
    manageContainerDialogVisible.value = true
    // 等待对话框渲染完成
    await nextTick()
    // 加载容器列表
    await fetchManageContainerList()
    // 等待表格数据更新和渲染完成
    await nextTick()
    // 设置选中状态
    setManageContainerSelection()
}

const fetchManageContainerList = async () => {
    manageContainerLoading.value = true
    const payload: any = {
        force_refresh: false
    }

    // 如果是管理员且选择了用户，传递 user_name 参数
    if (haveAdminRole.value && selectedUserName.value) {
        payload.user_name = selectedUserName.value
    }

    try {
        const res = await http.post('/EVE/industry/getUserAllContainerPermission', payload)
        const data = await res.json()
        if (data.status !== 200) {
            ElMessage.error(data.message || '获取容器许可列表失败')
            return
        }
        // 使用数组替换确保响应式更新
        manageContainerList.value = Array.isArray(data.data) ? [...data.data] : []
    } catch (error) {
        ElMessage.error('获取容器许可列表失败')
    } finally {
        manageContainerLoading.value = false
    }
}

const setManageContainerSelection = async () => {
    if (!manageContainerTableRef.value || !manageContainerList.value.length) return

    // 保存当前应该选中的容器列表（防止被清空）
    const targetSelection = [...manageContainerSelected.value]

    isSettingManageContainerSelection.value = true
    try {
        // 先清除所有选择
        manageContainerTableRef.value.clearSelection()
        // 等待清除操作完成
        await nextTick()

        // 设置选中状态
        manageContainerList.value.forEach((row: any) => {
            const isSelected = targetSelection.some(
                item => item.container_id === row.asset_container_id && item.owner_id === row.asset_owner_id && item.location_flag === row.location_flag
            )
            if (isSelected) {
                manageContainerTableRef.value?.toggleRowSelection(row, true)
            }
        })

        // 等待选择操作完成
        await nextTick()
        // 恢复 manageContainerSelected（防止被 clearSelection 触发的事件清空）
        manageContainerSelected.value = targetSelection
        // 再等待一个 tick 确保状态同步
        await nextTick()
        isSettingManageContainerSelection.value = false
    } catch (error) {
        isSettingManageContainerSelection.value = false
        console.error('设置管理容器选中状态失败:', error)
    }
}

const handleManageContainerSelectionChange = (selection: any[]) => {
    // 如果正在设置选中状态，忽略选择变化事件
    if (isSettingManageContainerSelection.value) {
        return
    }
    manageContainerSelected.value = selection.map(item => ({
        container_id: item.asset_container_id,
        owner_id: item.asset_owner_id,
        location_flag: item.location_flag ?? null
    }))
}

const handleManageContainerSelectAll = () => {
    manageContainerList.value.forEach((row: any) => {
        manageContainerTableRef.value?.toggleRowSelection(row, true)
    })
}

const handleManageContainerUnselectAll = () => {
    manageContainerTableRef.value?.clearSelection()
}

const handleSaveManageContainer = async () => {
    // 确保所有容器项都包含 location_flag 字段（如果缺失则设为 null）
    const containerList = manageContainerSelected.value.map(item => ({
        container_id: item.container_id,
        owner_id: item.owner_id,
        location_flag: item.location_flag ?? null
    }))

    const payload: any = {
        sid: assetViewSetForm.value.sid,
        container_list: containerList
    }

    // 如果是管理员且选择了用户，传递 user_name 参数
    if (haveAdminRole.value && selectedUserName.value) {
        payload.user_name = selectedUserName.value
    }
    console.log("handleSaveManageContainer payload", payload)
    try {
        const res = await http.post('/EVE/asset/saveAssetViewConfig', payload)
        const data = await res.json()
        if (data.status !== 200) {
            ElMessage.error(data.message)
            return
        }
        ElMessage.success('容器列表更新成功')
        manageContainerDialogVisible.value = false
        assetViewSetForm.value.asset_container_id_list = containerList.map(item => ({ ...item }))
        await getAssetViewList()
    } catch (error) {
        ElMessage.error('更新容器列表失败')
    }
}

// 监听对话框关闭，确保加载状态被重置
watch(addMonitorDialogVisible, (newVal) => {
    if (!newVal) {
        // 对话框关闭时重置加载状态
        containerPermissionLoading.value = false
    }
})

watch(manageContainerDialogVisible, (newVal) => {
    if (!newVal) {
        // 对话框关闭时重置加载状态
        manageContainerLoading.value = false
    }
})

onMounted(async () => {
    if (haveAdminRole.value) {
        await fetchUserList()
    }
    await getAssetViewList()
})


</script>

<template>
    <div class="asset-view-container">
        <!-- 管理员用户选择器 -->
        <div v-if="haveAdminRole" class="admin-user-selector">
            <el-form-item label="选择用户" style="margin-bottom: 16px;">
                <el-select v-model="selectedUserName" placeholder="选择用户（留空显示当前用户）" filterable clearable
                    :loading="userListLoading" style="width: 300px;">
                    <el-option v-for="user in userList" :key="user.userName" :label="user.userName"
                        :value="user.userName" />
                </el-select>
            </el-form-item>
        </div>

        <div class="asset-view-grid">
            <!-- 增加监控卡片 -->
            <el-card class="add-monitor-card" shadow="hover" @click="handleOpenAddMonitorDialog">
                <div class="add-monitor-content">
                    <el-icon class="add-icon">
                        <Plus />
                    </el-icon>
                    <div class="add-monitor-text">增加监控</div>
                </div>
            </el-card>

            <!-- 资产视图卡片 -->
            <el-card v-for="assetView in assetViewList" :key="assetView.sid" class="asset-view-card" shadow="hover"
                @click="handleViewAssetView(assetView)">
                <div class="card-header">
                    <div class="card-info">
                        <div class="card-title">{{ assetView.tag || '未命名视图' }}</div>
                        <div class="card-sid">ID: {{ assetView.sid }}</div>
                    </div>
                    <el-badge v-if="assetView.public" value="公开" class="public-badge" />
                </div>

                <div class="card-actions" @click.stop>
                    <el-tooltip content="查看详情" placement="top">
                        <el-button circle size="medium" type="primary" @click="handleViewAssetView(assetView)">
                            <el-icon>
                                <View />
                            </el-icon>
                        </el-button>
                    </el-tooltip>
                    <el-tooltip content="设置" placement="top">
                        <el-button circle size="medium" type="primary" plain @click="handleSetAssetView(assetView)">
                            <el-icon>
                                <Setting />
                            </el-icon>
                        </el-button>
                    </el-tooltip>
                    <el-tooltip content="分享链接" placement="top">
                        <el-button circle size="medium" type="success" plain :disabled="!assetView.public"
                            @click="copyPublicLink(assetView)">
                            <el-icon>
                                <Share />
                            </el-icon>
                        </el-button>
                    </el-tooltip>
                    <el-tooltip content="删除" placement="top">
                        <el-button circle size="medium" type="danger" plain @click="handleDeleteAssetView(assetView)">
                            <el-icon>
                                <Delete />
                            </el-icon>
                        </el-button>
                    </el-tooltip>
                </div>
            </el-card>
        </div>
    </div>

    <el-dialog v-model="assetViewDialogVisible" title="资产视图" width="80%" class="asset-view-dialog">
        <component :is="currentViewComponent" :loading="assetViewDialogLoading" :asset-view="assetView"
            :sid="AssetViewDialogSid" :view_type="AssetViewDialogType" :config="AssetViewDialogConfig"
            :last-update-time="assetViewLastUpdateTime" @refresh="refreshAssetView" />
    </el-dialog>

    <el-dialog v-model="assetViewSetDialogVisible" title="设置资产视图" width="700px" class="asset-view-set-dialog">
        <el-form :model="assetViewSetForm" label-width="120px" class="asset-view-set-form">
            <el-form-item label="标签">
                <el-input v-model="assetViewSetForm.tag" placeholder="请输入标签" />
            </el-form-item>
            <el-form-item>
                <el-select v-model="assetViewSetForm.view_type" placeholder="视图类型">
                    <el-option label="默认" value="default" />
                    <el-option label="销售" value="sell" />
                    <el-option label="监控" value="watch" />
                    <el-option label="统计" value="statistics" />
                </el-select>
            </el-form-item>

            <!-- 销售视图配置 -->
            <el-form-item v-if="assetViewSetForm.view_type === 'sell'">
                <el-select v-model="assetViewSetForm.config.price_base" placeholder="价格基准">
                    <el-option label="jita出单" value="jita_sell" />
                    <el-option label="jita中间" value="jita_mid" />
                    <el-option label="jita收单" value="jita_buy" />
                </el-select>
            </el-form-item>
            <el-form-item v-if="assetViewSetForm.view_type === 'sell'">
                <el-input-number v-model="assetViewSetForm.config.percent" placeholder="百分比" :min="0" :max="1"
                    :step="0.01" />
            </el-form-item>

            <el-form-item label="是否公开">
                <el-switch v-model="assetViewSetForm.public" />
                <span class="form-hint">公开后可通过链接访问</span>
            </el-form-item>

            <el-form-item label="管理容器">
                <el-button @click="handleOpenManageContainerDialog" type="primary" plain>
                    管理容器
                </el-button>
                <span class="form-hint">修改监控的容器列表</span>
            </el-form-item>

            <el-divider content-position="left">过滤条件</el-divider>

            <div class="filter-groups">
                <el-card v-for="group in assetViewSetForm.filter_groups" :key="group.index" class="filter-group-card"
                    shadow="never">
                    <template #header>
                        <div class="filter-group-header">
                            <span>过滤组 #{{ group.index + 1 }}</span>
                            <el-button @click="delete_filter_group(group.index)" type="danger" size="small" text
                                :icon="Delete">
                                删除
                            </el-button>
                        </div>
                    </template>
                    <el-form-item label="过滤类型">
                        <el-select v-model="group.filter_type" placeholder="请选择过滤类型" style="width: 100%">
                            <el-option v-for="item in filterTypeOptions" :key="item.value" :label="item.label"
                                :value="item.value" />
                        </el-select>
                    </el-form-item>
                    <el-form-item label="过滤值">
                        <el-autocomplete v-model="group.filter_value" :fetch-suggestions="fetchFilterSuggestions"
                            value-key="value" @click="before_fetch_filter_suggestions(group.filter_type)"
                            placeholder="请输入过滤值" style="width: 100%" />
                    </el-form-item>
                </el-card>
            </div>

            <el-button @click="add_filter_group" type="primary" size="small" :icon="Plus" class="add-filter-btn">
                增加过滤组
            </el-button>

            <div class="dialog-actions">
                <el-button @click="assetViewSetDialogVisible = false">取消</el-button>
                <el-button @click="saveAssetViewConfig" type="primary">保存</el-button>
            </div>
        </el-form>
    </el-dialog>

    <el-dialog v-model="addMonitorDialogVisible" title="增加监控" width="1000px" class="add-monitor-dialog">
        <el-form label-width="120px" class="add-monitor-form" :model="{ tag: newViewTag }">
            <el-form-item label="标签" required>
                <el-input v-model="newViewTag" placeholder="请输入标签（必填）" style="width: 100%" />
            </el-form-item>
            <el-form-item label="选择容器">
                <div class="container-selector">
                    <div class="selector-actions">
                        <el-button size="small" @click="handleSelectAll">全选</el-button>
                        <el-button size="small" @click="handleUnselectAll">反选</el-button>
                        <span class="selected-count">已选择 {{ selectedContainers.length }} 个容器</span>
                    </div>
                    <div v-if="containerPermissionLoading" class="loading-tip">
                        <el-icon class="is-loading">
                            <Loading />
                        </el-icon>
                        <span>正在加载容器列表...</span>
                    </div>
                    <el-table ref="containerTableRef" :key="`container-table-${addMonitorDialogVisible}`"
                        :data="containerPermissionList" :loading="containerPermissionLoading"
                        :row-key="(row: any) => `${row.asset_container_id}-${row.asset_owner_id}`" max-height="400px"
                        @selection-change="handleTableSelectionChange">
                        <el-table-column type="selection" :reserve-selection="true" width="55"
                            :selectable="(row: any) => true" />
                        <el-table-column prop="tag" label="标签" width="120" />
                        <el-table-column prop="structure_name" label="结构名称" width="200" />
                        <el-table-column prop="system_name" label="星系" width="150" />
                        <el-table-column prop="owner_name" label="所有者" width="150" />
                        <el-table-column prop="owner_type" label="类型" width="100">
                            <template #default="scope">
                                <span>{{ scope.row.owner_type === 'character' ? '角色' : '公司' }}</span>
                            </template>
                        </el-table-column>
                    </el-table>
                </div>
            </el-form-item>
            <div class="dialog-actions">
                <el-button @click="addMonitorDialogVisible = false">取消</el-button>
                <el-button @click="handleAddMonitor" type="primary">创建</el-button>
            </div>
        </el-form>
    </el-dialog>

    <el-dialog v-model="manageContainerDialogVisible" title="管理容器" width="950" class="manage-container-dialog">
        <div class="container-selector">
            <div class="selector-actions">
                <el-button size="small" @click="handleManageContainerSelectAll">全选</el-button>
                <el-button size="small" @click="handleManageContainerUnselectAll">反选</el-button>
                <span class="selected-count">已选择 {{ manageContainerSelected.length }} 个容器</span>
            </div>
            <div v-if="manageContainerLoading" class="loading-tip">
                <el-icon class="is-loading">
                    <Loading />
                </el-icon>
                <span>正在加载容器列表...</span>
            </div>
            <el-table ref="manageContainerTableRef" :key="`manage-container-table-${manageContainerDialogVisible}`"
                :data="manageContainerList" :loading="manageContainerLoading"
                :row-key="(row: any) => `${row.asset_container_id}-${row.asset_owner_id}-${row.location_flag}`"
                max-height="400px" @selection-change="handleManageContainerSelectionChange">
                <el-table-column type="selection" :reserve-selection="true" width="55"
                    :selectable="(row: any) => true" />
                <el-table-column prop="tag" label="标签" width="120" />
                <el-table-column prop="structure_name" label="结构名称" width="200" />
                <el-table-column prop="system_name" label="星系" width="150" />
                <el-table-column prop="owner_name" label="所有者" width="150" />
                <el-table-column prop="location_flag" label="位置标志" width="150" />
                <el-table-column prop="owner_type" label="类型" width="100">
                    <template #default="scope">
                        <span>{{ scope.row.owner_type === 'character' ? '角色' : '公司' }}</span>
                    </template>
                </el-table-column>
            </el-table>
        </div>
        <div class="dialog-actions">
            <el-button @click="manageContainerDialogVisible = false">取消</el-button>
            <el-button @click="handleSaveManageContainer" type="primary">保存</el-button>
        </div>
    </el-dialog>
</template>

<style scoped>
/* 主容器 */
.asset-view-container {
    padding: 20px;
}

/* 管理员用户选择器 */
.admin-user-selector {
    margin-bottom: 20px;
    padding: 16px;
    background-color: #f5f7fa;
    border-radius: 4px;
    border: 1px solid #e4e7ed;
}

/* 网格布局 */
.asset-view-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 20px;
    max-width: auto;
}

/* 增加监控卡片 */
.add-monitor-card {
    min-height: 200px;
    cursor: pointer;
    transition: all 0.3s ease;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border: none;
}

.add-monitor-card:hover {
    transform: translateY(-4px);
    box-shadow: 0 8px 24px rgba(102, 126, 234, 0.4);
}

.add-monitor-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    min-height: 160px;
    color: white;
}

.add-icon {
    font-size: 48px;
    margin-bottom: 16px;
    opacity: 0.9;
}

.add-monitor-text {
    font-size: 18px;
    font-weight: 500;
}

/* 资产视图卡片 */
.asset-view-card {
    min-height: 200px;
    cursor: pointer;
    transition: all 0.3s ease;
    position: relative;
}

.asset-view-card:hover {
    transform: translateY(-4px);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

.card-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 16px;
}

.card-info {
    flex: 1;
}

.card-title {
    font-size: 16px;
    font-weight: 600;
    color: #303133;
    margin-bottom: 8px;
    word-break: break-word;
}

.card-sid {
    font-size: 12px;
    color: #909399;
}

.public-badge {
    margin-left: 8px;
}

.public-badge :deep(.el-badge__content) {
    background-color: #67c23a;
    border-color: #67c23a;
    font-size: 11px;
    padding: 0 6px;
}

.card-actions {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
    margin-top: 16px;
    padding-top: 16px;
    border-top: 1px solid #f0f0f0;
}

/* 资产视图对话框 */
.asset-view-dialog :deep(.el-dialog__body) {
    padding: 24px;
    max-height: 70vh;
    overflow-y: auto;
}

/* 设置对话框 */
.asset-view-set-dialog :deep(.el-dialog__body) {
    padding: 24px;
}

.asset-view-set-form {
    max-height: 70vh;
    overflow-y: auto;
    padding-right: 8px;
}

.form-hint {
    margin-left: 12px;
    font-size: 12px;
    color: #909399;
}

.filter-groups {
    margin: 16px 0;
}

.filter-group-card {
    margin-bottom: 16px;
    border: 1px solid #e4e7ed;
}

.filter-group-card :deep(.el-card__header) {
    padding: 12px 16px;
    background-color: #f5f7fa;
    border-bottom: 1px solid #e4e7ed;
}

.filter-group-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-weight: 500;
    color: #606266;
}

.add-filter-btn {
    margin-bottom: 20px;
}

.dialog-actions {
    display: flex;
    justify-content: flex-end;
    gap: 12px;
    margin-top: 24px;
    padding-top: 20px;
    border-top: 1px solid #e4e7ed;
}

/* 增加监控对话框 */
.add-monitor-dialog :deep(.el-dialog__body) {
    padding: 24px;
}

.add-monitor-form {
    padding: 8px 0;
}

.add-monitor-form .dialog-actions {
    margin-top: 20px;
    padding-top: 20px;
    border-top: 1px solid #e4e7ed;
}

.container-selector {
    width: 100%;
}

.selector-actions {
    display: flex;
    gap: 12px;
    align-items: center;
    margin-bottom: 12px;
}

.selected-count {
    margin-left: auto;
    font-size: 14px;
    color: #606266;
}

.loading-tip {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px;
    margin-bottom: 12px;
    background-color: #f5f7fa;
    border-radius: 4px;
    color: #606266;
    font-size: 14px;
}

.loading-tip .el-icon {
    font-size: 16px;
    color: #409eff;
}

/* 响应式设计 */
@media (max-width: 768px) {
    .asset-view-grid {
        grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
        gap: 16px;
    }

    .asset-view-set-dialog,
    .add-monitor-dialog {
        width: 90% !important;
    }
}

@media (max-width: 480px) {
    .asset-view-container {
        padding: 12px;
    }

    .asset-view-grid {
        grid-template-columns: 1fr;
        gap: 12px;
    }

    .card-actions {
        flex-wrap: wrap;
    }
}
</style>