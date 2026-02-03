<script setup lang="ts">
import { computed } from 'vue'
import VipPricingPlans from './VipPricingPlans.vue'

// Props定义
const props = defineProps<{
  modelValue: boolean
}>()

// Emits定义
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

// 计算属性：控制弹窗显示
const dialogVisible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
})
</script>

<template>
  <el-dialog v-model="dialogVisible" title="VIP订阅方案" width="90%" :max-width="1200" :close-on-click-modal="true"
    :close-on-press-escape="true" align-center class="vip-pricing-dialog">
    <div class="vip-pricing-content">
      <div class="pricing-header-info">
        <p class="pricing-subtitle">可领取Omega 7天试用</p>
        <p class="pricing-notice">
          收费策略可能会根据服务器资源、联盟政策等因素变动，暂不接受年卡等长期订阅
        </p>
      </div>

      <VipPricingPlans :show-contact-info="true" />
    </div>
  </el-dialog>
</template>

<style scoped>
.vip-pricing-content {
  padding: 20px 0;
}

.pricing-header-info {
  text-align: center;
  margin-bottom: 32px;
}

.pricing-subtitle {
  font-size: 18px;
  color: #64748b;
  margin: 0 0 12px 0;
}

.pricing-notice {
  font-size: 14px;
  color: #909399;
  margin: 0;
  font-style: italic;
}

</style>
