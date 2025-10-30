<script setup lang="ts">
import { ref, onMounted } from 'vue'
import mainSidebar from '../components/sideBar/mainSidebar.vue'
import { useRouter } from 'vue-router'

const router = useRouter()

const segmentValue = ref('overview')

const segmentItems = [
  {label: '总览视图', value: 'overview', icon: 'Apple', route: '/industry/overview'},
  {label: '库存管理', value: 'assetView', icon: 'Apple', route: '/industry/assetView'},
  {label: '工业计划', value: 'industryPlan', icon: 'Apple', route: '/industry/industryPlan'},
  {label: '流程拆解', value: 'flowDecomposition', icon: 'Apple', route: '/industry/flowDecomposition'},
  {label: '工作流', value: 'workflow', icon: 'Apple', route: '/industry/workflow'},
]

onMounted(() => {
  router.push('/industry/overview')
})

// 切换segment时，更新segmentValue，并跳转至对应路由
const handleSegmentChange = (value: string) => {
  segmentValue.value = value
  router.push(segmentItems.find(item => item.value === value)?.route || '/industry/overview')
}

</script>

<template>
  <el-container class="container-view">
    <el-aside width="90px">
       <el-segmented
       v-model="segmentValue"
       :options="segmentItems"
       direction="vertical"
       @change="handleSegmentChange"
       block
      />
    </el-aside>

    <el-container class="container-container">
      <router-view />
    </el-container>
  </el-container>
</template>

<style scoped>
.container-view {
  height: 100%;
}

.container-container {
  padding-left: 20px;
  padding-top: 10px;
  padding-bottom: 10px;
  height: 100% - 20px;
  width: 100% - 20px;
}

</style>