<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { http } from '@/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Share, Setting, Delete, View, Plus } from '@element-plus/icons-vue'
import DefaultView from './assetViewComponent/defaultView.vue'
import SellView from './assetViewComponent/sellView.vue'
import WatchView from './assetViewComponent/watchView.vue'

// ============== 资产视图组件映射 ==============
// 未来添加新组件时，只需在此处添加映射关系即可
const viewComponentMap: Record<string, any> = {
    'default': DefaultView,
    'sell': SellView,
    'watch': WatchView,
    // 未来可以轻松添加更多组件类型，例如：
    // 'buy': BuyView,
    // 'manufacture': ManufactureView,
    // 'research': ResearchView,
}

const assetViewList = ref<any[]>([])
const getAssetViewList = async () => {
    const res = await http.get('/EVE/asset/getAssetViewList')
    const data = await res.json()
    assetViewList.value = data.data
}

const assetViewDialogVisible = ref(false)
const assetViewDialogLoading = ref(false)
const assetView = ref<any[]>([])
const AssetViewDialogSid = ref('')
const handleViewAssetView = async (assetViewItem: any) => {
    assetViewDialogVisible.value = true
    assetViewDialogLoading.value = true

    const res = await http.get('/EVE/asset/getAssetViewData', {
        asset_view_sid: assetViewItem.sid
    })
    const data = await res.json()
    assetViewDialogLoading.value = false
    if (data.status !== 200) {
        ElMessage.error(data.message)
        return
    }
    // 后端返回的是对象（字典），需要转换为数组
    assetView.value = Object.values(data.data || {})
    AssetViewDialogType.value = data.view_type
    AssetViewDialogConfig.value = data.config
    AssetViewDialogSid.value = assetViewItem.sid
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
    ]
})

// ============== 过滤类型选项 ==============
const filterTypeOptions = ref([
    { value: 'group', label: 'group' },
    { value: 'meta', label: 'meta' },
    { value: 'marketGroup', label: 'marketGroup' },
    { value: 'category', label: 'category' },
    { value: 'type_id', label: 'type_id' },
    { value: 'location_flag', label: 'location_flag' }
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
}

const saveAssetViewConfig = async () => {
    // 将 filter_groups 转换回 filter 数组格式
    const filters = assetViewSetForm.value.filter_groups
        .filter(group => group.filter_type && group.filter_value)
        .map(group => ({
            type: group.filter_type,
            value: group.filter_value
        }))

    const res = await http.post('/EVE/asset/saveAssetViewConfig', {
        sid: assetViewSetForm.value.sid,
        tag: assetViewSetForm.value.tag,
        public: assetViewSetForm.value.public,
        filter: filters,
        view_type: assetViewSetForm.value.view_type,
        config: assetViewSetForm.value.config
    })
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
        
        // 尝试调用删除 API（如果后端支持）
        try {
            const res = await http.delete('/EVE/asset/deleteAssetView', {
                sid: assetViewItem.sid
            })
            const data = await res.json()
            if (data.status !== 200) {
                ElMessage.error(data.message || '删除失败')
                return
            }
            ElMessage.success(data.message || '删除成功')
            await getAssetViewList()
        } catch (error: any) {
            // 如果 API 不存在，提示用户
            if (error?.message?.includes('404') || error?.message?.includes('Not Found')) {
                ElMessage.warning('删除功能需要后端 API 支持，请联系管理员')
            } else {
                ElMessage.error('删除失败：' + (error?.message || '未知错误'))
            }
        }
    } catch (error) {
        // 用户取消删除
    }
}

// ============== 增加监控 ==============
const addMonitorDialogVisible = ref(false)
const selectedContainerTag = ref('')

interface ContainerPermissionItem {
    tag: string
}

const ContainerPermissionSuggestions = ref<ContainerPermissionItem[]>([])
const StructureContainerPermissionCreateFilter = (queryString: string) => {
    return (item: ContainerPermissionItem) => {
        return item.tag.toLowerCase().indexOf(queryString.toLowerCase()) === 0
    }
}

const fetchContainerPermissionSuggestions = async (queryString: string, cb: (suggestions: ContainerPermissionItem[]) => void) => {
    const res = await http.post('/EVE/industry/getUserAllContainerPermission', {
        force_refresh: false
    })
    const data = await res.json()
    console.log("fetchContainerPermissionSuggestions data", data)
    ContainerPermissionSuggestions.value = data.data
    
    const results = queryString
        ? ContainerPermissionSuggestions.value.filter(StructureContainerPermissionCreateFilter(queryString))
        : ContainerPermissionSuggestions.value
    cb(results)
}

const handleOpenAddMonitorDialog = () => {
    addMonitorDialogVisible.value = true
    selectedContainerTag.value = ''
}

const handleAddMonitor = async () => {
    if (!selectedContainerTag.value) {
        ElMessage.warning('请选择库存许可')
        return
    }
    
    try {
        const res = await http.post('/EVE/asset/createAssetView', {
            container_tag: selectedContainerTag.value
        })
        const data = await res.json()
        if (data.status !== 200) {
            ElMessage.error(data.message)
            return
        }
        ElMessage.success(data.message || '创建监控成功')
        addMonitorDialogVisible.value = false
        selectedContainerTag.value = ''
        await getAssetViewList()
    } catch (error) {
        ElMessage.error('创建监控失败')
    }
}

onMounted(async () => {
    await getAssetViewList()
})


</script>

<template>
    <div class="asset-view-container">
        <div class="asset-view-grid">
            <!-- 增加监控卡片 -->
            <el-card class="add-monitor-card" shadow="hover" @click="handleOpenAddMonitorDialog">
                <div class="add-monitor-content">
                    <el-icon class="add-icon"><Plus /></el-icon>
                    <div class="add-monitor-text">增加监控</div>
                </div>
            </el-card>
            
            <!-- 资产视图卡片 -->
            <el-card 
                v-for="assetView in assetViewList" 
                :key="assetView.sid" 
                class="asset-view-card"
                shadow="hover"
                @click="handleViewAssetView(assetView)"
            >
                <div class="card-header">
                    <div class="card-info">
                        <div class="card-title">{{ assetView.tag || '未命名视图' }}</div>
                        <div class="card-sid">ID: {{ assetView.sid }}</div>
                    </div>
                    <el-badge v-if="assetView.public" value="公开" class="public-badge" />
                </div>
                
                <div class="card-actions" @click.stop>
                    <el-tooltip content="查看详情" placement="top">
                        <el-button 
                            circle 
                            size="medium" 
                            type="primary" 
                            @click="handleViewAssetView(assetView)"
                        >
                            <el-icon><View /></el-icon>
                        </el-button>
                    </el-tooltip>
                    <el-tooltip content="设置" placement="top">
                        <el-button 
                            circle 
                            size="medium" 
                            type="primary" 
                            plain
                            @click="handleSetAssetView(assetView)"
                        >
                            <el-icon><Setting /></el-icon>
                        </el-button>
                    </el-tooltip>
                    <el-tooltip content="分享链接" placement="top">
                        <el-button 
                            circle 
                            size="medium" 
                            type="success" 
                            plain
                            :disabled="!assetView.public"
                            @click="copyPublicLink(assetView)"
                        >
                            <el-icon><Share /></el-icon>
                        </el-button>
                    </el-tooltip>
                    <el-tooltip content="删除" placement="top">
                        <el-button 
                            circle 
                            size="medium" 
                            type="danger" 
                            plain
                            @click="handleDeleteAssetView(assetView)"
                        >
                            <el-icon><Delete /></el-icon>
                        </el-button>
                    </el-tooltip>
                </div>
            </el-card>
        </div>
    </div>

    <el-dialog v-model="assetViewDialogVisible" title="资产视图" width="80%" class="asset-view-dialog">
        <component 
            :is="currentViewComponent"
            :loading="assetViewDialogLoading" 
            :asset-view="assetView"
            :sid="AssetViewDialogSid"
            :view_type="AssetViewDialogType"
            :config="AssetViewDialogConfig"
        />
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
                <el-input-number v-model="assetViewSetForm.config.percent" placeholder="百分比" :min="0" :max="1" :step="0.01" />
            </el-form-item>

            <el-form-item label="是否公开">
                <el-switch v-model="assetViewSetForm.public" />
                <span class="form-hint">公开后可通过链接访问</span>
            </el-form-item>

            <el-divider content-position="left">过滤条件</el-divider>
            
            <div class="filter-groups">
                <el-card 
                    v-for="group in assetViewSetForm.filter_groups" 
                    :key="group.index" 
                    class="filter-group-card"
                    shadow="never"
                >
                    <template #header>
                        <div class="filter-group-header">
                            <span>过滤组 #{{ group.index + 1 }}</span>
                            <el-button
                                @click="delete_filter_group(group.index)"
                                type="danger"
                                size="small"
                                text
                                :icon="Delete"
                            >
                                删除
                            </el-button>
                        </div>
                    </template>
                    <el-form-item label="过滤类型">
                        <el-select v-model="group.filter_type" placeholder="请选择过滤类型" style="width: 100%">
                            <el-option
                                v-for="item in filterTypeOptions"
                                :key="item.value"
                                :label="item.label"
                                :value="item.value"
                            />
                        </el-select>
                    </el-form-item>
                    <el-form-item label="过滤值">
                        <el-autocomplete
                            v-model="group.filter_value"
                            :fetch-suggestions="fetchFilterSuggestions"
                            value-key="value"
                            @click="before_fetch_filter_suggestions(group.filter_type)"
                            placeholder="请输入过滤值"
                            style="width: 100%"
                        />
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

    <el-dialog v-model="addMonitorDialogVisible" title="增加监控" width="500px" class="add-monitor-dialog">
        <el-form label-width="120px" class="add-monitor-form">
            <el-form-item label="选择库存许可">
                <el-autocomplete
                    v-model="selectedContainerTag"
                    :fetch-suggestions="fetchContainerPermissionSuggestions"
                    value-key="tag"
                    placeholder="请选择库存许可"
                    style="width: 100%"
                />
            </el-form-item>
            <div class="dialog-actions">
                <el-button @click="addMonitorDialogVisible = false">取消</el-button>
                <el-button @click="handleAddMonitor" type="primary">创建</el-button>
            </div>
        </el-form>
    </el-dialog>
</template>

<style scoped>
/* 主容器 */
.asset-view-container {
    padding: 20px;
}

/* 网格布局 */
.asset-view-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 20px;
    max-width: 1400px;
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