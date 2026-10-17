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

export interface BpcDetail {
  runs: number
}

export interface BlueprintRequirementItem {
  type_id: number
  type_name: string
  type_name_zh: string
  missing_blueprint_type: '舰船' | '组件' | '反应' | '其他'
  bpc_count: number
  bpc_details: BpcDetail[]
  runs_total: number
  tech2_invention_source_bp_type_id: number | null
  tech2_invention_source_bp_type_name: string | null
}

export interface TaxConfig {
  target_category: string
  tax_rate: number
}

export interface TaxItem {
  category: string        // e.g. "矿物税"
  target_category: string // e.g. "矿物"
  tax_rate: number        // e.g. 10.0
  tax_amount: number      // calculated ISK amount
}
</script>

<template>
    <div>
        <h1>接口类型</h1>
    </div>
</template>

<style scoped>

</style>