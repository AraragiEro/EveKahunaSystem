<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { http } from '@/http'
import { ElMessage } from 'element-plus'
import DefaultView from '../industry/components/assetViewComponent/defaultView.vue'
import SellView from '../industry/components/assetViewComponent/sellView.vue'

const route = useRoute()
const sid = route.params.sid as string

const loading = ref(false)
const assetView = ref<any[]>([])
const assetViewTag = ref<string>('')
const assetViewType = ref<string>('default')
const assetViewConfig = ref({
    price_base: 'jita_sell',
    percent: 1.0
})
const errorMessage = ref<string>('')

// 组件映射
const viewComponentMap: Record<string, any> = {
    'default': DefaultView,
    'sell': SellView,
}

// 根据类型动态获取对应的组件
const currentViewComponent = computed(() => {
    return viewComponentMap[assetViewType.value] || DefaultView
})

const fetchPublicStorageData = async () => {
    if (!sid) {
        errorMessage.value = '缺少资产视图ID'
        return
    }

    loading.value = true
    errorMessage.value = ''
    
    try {
        const res = await http.get(`/public/storage/${sid}`)
        const data = await res.json()
        
        if (data.status !== 200) {
            errorMessage.value = data.message || '获取数据失败'
            ElMessage.error(data.message || '获取数据失败')
            return
        }
        
        // 后端返回的是对象（字典），需要转换为数组
        assetView.value = Object.values(data.data || {})
        assetViewTag.value = data.tag || ''
        assetViewType.value = data.view_type || 'default'
        assetViewConfig.value = data.config || {
            price_base: 'jita_sell',
            percent: 1.0
        }
    } catch (error: any) {
        errorMessage.value = error.message || '获取数据失败'
        ElMessage.error(error.message || '获取数据失败')
    } finally {
        loading.value = false
    }
}

onMounted(() => {
    fetchPublicStorageData()
})
</script>

<template>
    <div class="storage-container">
        <div class="storage-header">
            <h1 class="page-title">资产视图</h1>
            <div class="page-subtitle">{{ assetViewTag }}</div>
        </div>
        
        <div v-loading="loading" class="storage-content">
            <!-- 错误状态 -->
            <div v-if="errorMessage" class="error-state">
                <el-result
                    icon="error"
                    :title="errorMessage"
                    sub-title="请检查链接是否正确"
                />
            </div>
            
            <!-- 动态组件 -->
            <component 
                v-else
                :is="currentViewComponent"
                :loading="loading"
                :asset-view="assetView"
                :view_type="assetViewType"
                :config="assetViewConfig"
            />
        </div>
    </div>
</template>

<style scoped>
/* 主容器 */
.storage-container {
    min-height: 100vh;
    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    padding: 40px 20px;
}

/* 页面头部 */
.storage-header {
    max-width: 1400px;
    margin: 0 auto 32px;
    text-align: center;
}

.page-title {
    font-size: 32px;
    font-weight: 600;
    color: #2c3e50;
    margin: 0 0 8px 0;
}

.page-subtitle {
    font-size: 16px;
    color: #64748b;
    margin: 0;
}

/* 内容区域 */
.storage-content {
    max-width: 1400px;
    margin: 0 auto;
    min-height: 400px;
}

/* 错误状态 */
.error-state {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 400px;
    background: white;
    border-radius: 8px;
    padding: 40px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

/* 响应式设计 */
@media (max-width: 768px) {
    .storage-container {
        padding: 20px 12px;
    }
    
    .page-title {
        font-size: 24px;
    }
    
    .page-subtitle {
        font-size: 14px;
    }
    
    .error-state {
        padding: 20px;
        min-height: 300px;
    }
}
</style>

