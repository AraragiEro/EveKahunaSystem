<script setup lang="ts">
import { ref } from 'vue'

const corpLinesTotal = ref(100)
const corpLinesRunning = ref(30)

const personalLinesTotal = ref(100)
const personalLinesRunning = ref(30)

</script>

<template>
<el-container>
  <el-header>
    <el-button type="primary">新增</el-button>
  </el-header>
  <el-main>

    <!-- 流水线 -->
    <el-row :gutter="16">
      <el-col :xs="24" :sm="12" :md="8" class="mb-4">
        <div class="statistic-card">
          <el-statistic :value="corpLinesRunning" :title="corpLinesTotal">
            <template #title>
              <div>
                公司流水线
              </div>
            </template>
            <template #suffix> / {{corpLinesTotal}} </template>
          </el-statistic>
        </div>
      </el-col>

      <el-col :xs="24" :sm="12" :md="8" class="mb-4">
        <div class="statistic-card">
          <el-statistic :value="personalLinesRunning" :title="personalLinesTotal">
            <template #title>
              <div>
                个人流水线
              </div>
            </template>
            <template #suffix>/ {{personalLinesTotal}}</template>
          </el-statistic>
        </div>
      </el-col>
    </el-row>


  </el-main>
</el-container>
</template>

<style scoped>
:global(h2#card-usage ~ .example .example-showcase) {
  background-color: var(--el-fill-color) !important;
}

.el-statistic {
  --el-statistic-content-font-size: 28px;
}

.statistic-card {
  height: 100%;
  padding: 20px;
  border-radius: 4px;
  background-color: var(--el-bg-color-overlay);
}

.statistic-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--el-text-color-regular);
  margin-top: 16px;
}

.statistic-footer .footer-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.statistic-footer .footer-item span:last-child {
  display: inline-flex;
  align-items: center;
  margin-left: 4px;
}

.green {
  color: var(--el-color-success);
}
.red {
  color: var(--el-color-error);
}
</style>