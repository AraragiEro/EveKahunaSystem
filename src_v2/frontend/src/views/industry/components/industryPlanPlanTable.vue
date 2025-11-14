<template>
  <div class="table-container">
    <el-scrollbar height="56vh">
    <table class="card-table">
      <thead>
        <tr class="table-header">
          <th>产品</th>
          <th>数量</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody class="industry-plan-product-table">
        <tr v-for="item in list" :key="item.row_id" class="card-row cursor-move">
          <td class="product-name">{{ item.type_name_zh }}</td>
          <td class="quantity-cell">
            <el-input-number v-model="item.quantity" :min="0" :max="1000000" />
          </td>
          <td class="action-cell">
            <el-button type="primary" plain @click="handleDeleteProduct(item)">
              删除
            </el-button>
          </td>
        </tr>
      </tbody>
    </table>
  </el-scrollbar>
  </div>
</template>

<script setup lang="ts">
interface PlanProductTableData {
  "row_id": number,
  "index_id": number,
  "product_type_id": number,
  "quantity": number,
  "type_name": string,
  "type_name_zh": string
}
interface Props {
  list: PlanProductTableData[]
}
const props = defineProps<Props>()

const handleDeleteProduct = (item: PlanProductTableData) => {
  const index = props.list.findIndex(product => product.index_id === item.index_id)
  if (index !== -1) {
    props.list.splice(index, 1)
  }
}

</script>

<style scoped>
.table-container {
  width: 100%;
  padding: 8px 0;
}

.card-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0 12px;
  background: transparent;
}

.table-header {
  background: transparent;
}

.table-header th {
  padding: 12px 16px;
  text-align: left;
  font-weight: 600;
  font-size: 14px;
  color: #606266;
  border: none;
  background: transparent;
}

.industry-plan-product-table {
  display: table-row-group;
}

.card-row {
  background: #ffffff;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  margin-bottom: 12px;
  display: table-row;
  border: none;
}

.card-row:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  transform: translateY(-2px);
  background: #ffffff;
}

.card-row td {
  padding: 16px;
  border: none;
  background: transparent;
  vertical-align: middle;
}

.card-row:first-child td:first-child {
  border-top-left-radius: 12px;
}

.card-row:first-child td:last-child {
  border-top-right-radius: 12px;
}

.card-row:last-child td:first-child {
  border-bottom-left-radius: 12px;
}

.card-row:last-child td:last-child {
  border-bottom-right-radius: 12px;
}

.product-name {
  font-size: 15px;
  font-weight: 500;
  color: #303133;
  min-width: 200px;
}

.quantity-cell {
  width: 180px;
}

.quantity-cell :deep(.el-input-number) {
  width: 100%;
}

.quantity-cell :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #dcdfe6 inset;
  border-radius: 4px;
  transition: all 0.2s;
}

.quantity-cell :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px #c0c4cc inset;
}

.action-cell {
  width: 120px;
  text-align: right;
}

.action-cell .el-button {
  transition: all 0.2s;
}

.action-cell .el-button:hover {
  transform: scale(1.05);
}

/* 拖拽时的视觉反馈 */
.card-row.sortable-ghost {
  opacity: 0.5;
  background: #f5f7fa;
}

.card-row.sortable-drag {
  opacity: 0.8;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.16);
}

/* 响应式设计 */
@media (max-width: 768px) {
  .table-container {
    padding: 4px 0;
  }

  .card-table {
    border-spacing: 0 8px;
  }

  .card-row td {
    padding: 12px;
  }

  .product-name {
    min-width: 150px;
    font-size: 14px;
  }

  .quantity-cell {
    width: 140px;
  }

  .action-cell {
    width: 100px;
  }

  .table-header th {
    padding: 10px 12px;
    font-size: 13px;
  }
}

/* 空状态优化 */
.industry-plan-product-table:empty::after {
  content: '暂无产品';
  display: block;
  text-align: center;
  padding: 40px;
  color: #909399;
  font-size: 14px;
}
</style>