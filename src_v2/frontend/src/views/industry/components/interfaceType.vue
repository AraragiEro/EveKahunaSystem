<script setup lang="ts">

export interface PlanProductTableData {
  "row_id": number,
  "index_id": number,
  "product_type_id": number,
  "quantity": number,
  "type_name": string,
  "type_name_zh": string
}

export interface PlanTableData {
    "row_id": number,
    "plan_name": string,
    "user_name": string,
    "plan_settings": object,
    "products": PlanProductTableData[]
}
</script>

<template>
    <div>
        <h1>接口类型</h1>
    </div>
</template>

<style scoped>

</style>