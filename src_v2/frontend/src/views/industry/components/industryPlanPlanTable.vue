<template>
  <table>
    <thead>
      <tr>
        <th>产品</th>
        <th>数量</th>
        <th>操作</th>
      </tr>
    </thead>
    <tbody class="industry-plan-product-table">
      <tr v-for="item in list" :key="item.row_id" class="cursor-move">
        <td>{{ item.type_name_zh }}</td>
        <td><el-input-number v-model="item.quantity" :min="0" :max="1000000" /></td>
        <td><div>
          <el-button type="primary" plain @click="handleDeleteProduct(item)">
            删除
          </el-button>
        </div></td>
      </tr>
    </tbody>
  </table>
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