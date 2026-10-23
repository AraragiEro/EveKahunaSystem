<script setup lang="ts">
/**
 * 工业 · 总览
 * ---------------------------------------------------------------
 * 这里原先写死了「公司流水线 30/100」「个人流水线 30/100」四个常量，
 * 以及一个没有绑定任何 @click 的「新增」按钮——打开页面看到的全是假数。
 * 目前后端还没有按账号聚合产线/作业的接口，因此本页改为明确的空态，
 * 等接口就绪后再接真实数据（不要再回退成占位数字）。
 */
import KCard from '@/components/k/KCard.vue'
import KEmpty from '@/components/k/KEmpty.vue'
</script>

<template>
  <div class="industry-overview">
    <KCard title="工业总览" subtitle="公司 / 个人流水线的占用情况">
      <KEmpty
        size="lg"
        icon="info"
        why="流水线统计还没有接入真实数据"
        hint="需要后端提供按账号聚合的公司/个人产线与作业数据；接口就绪前这里不展示占位数字。"
      />
    </KCard>
  </div>
</template>

<style scoped>
.industry-overview {
  padding: 20px;
}
</style>
