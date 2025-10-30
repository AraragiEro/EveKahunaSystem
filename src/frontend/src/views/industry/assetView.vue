<script setup lang="ts">
import { ref } from 'vue'
import { Setting } from '@element-plus/icons-vue'
import axios from 'axios';
import { ElMessage } from 'element-plus';

const containerList = ref([])

const getContainerList = async () => {
  const response = await axios.get('/api/asset/container/list');
  console.log('API返回数据:', response.data);
  containerList.value = response.data; // 赋值给ref
}
getContainerList(); // 组件加载时调用

const deleteContainer = async (id: string) => {
  const response = await axios.post('/api/asset/container/delete', { id });
  if (response.data.code === 200) {
    ElMessage.success('删除成功');
  } else {
    ElMessage.error('删除失败');
  }

  
}
</script>

<template>
<div style="display: flex;">
  <div class="asset-col" style="width: 300px;">
    <div class="asset-table-header">
      <el-button>添加库存</el-button>
    </div>
    <div class="asset-table-container">
      <el-table :data="containerList" height="100%">
        <el-table-column label="容器名称">
          <template #default="row">
            <el-tag class="custom-tag" :title="row.row.name">{{ row.row.name }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="70">
          <template #default="row">
            <el-button type="danger" icon="Delete" circle />
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
  <div class="asset-col">
    <div class="asset-view">
      <h1>资产视图</h1>
    </div>
  </div>
</div>
</template>

<style scoped>
.asset-view-row {
  background-color: #ffffff;
  padding: 20px;
  display: flex;
  height: calc(100vh - 40px); /* 距离顶部和底部各留20px */
  width: 100%;
  border-radius: 12px;
  box-sizing: border-box;
}

.asset-col {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding-left: 10px;
}

.asset-table-header {
  height: 48px; /* 固定按钮高度 */
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 2px;
  flex-shrink: 0;
}

.asset-table-container {
  flex: 1 1 0;
  display: flex;
  flex-direction: column;
  background-color: #757575;
  border-radius: 5px;
  padding: 5px;
  min-height: 0; /* 关键，防止溢出 */
  max-height: calc(100vh - 40px - 48px - 20px); /* 总高度-按钮-内边距 */
}

.asset-table-container .el-table {
  flex: 1 1 auto;
  min-height: 0;
  width: 100%;
  background-color: #666666;
  overflow: hidden;
}

.asset-table-container .el-table {
  background-color: #666666;
}

.asset-table-container .el-table .el-table__row {
  border-radius: 5px;
}
</style>