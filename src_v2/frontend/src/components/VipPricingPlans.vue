<script setup lang="ts">
import { pricingPlans } from '@/data/pricingPlans'
import KCard from '@/components/k/KCard.vue'

// Props定义
const props = withDefaults(defineProps<{
  showContactInfo?: boolean
}>(), {
  showContactInfo: false
})
</script>

<template>
  <div class="vip-pricing-plans">
    <div class="pricing-grid">
      <KCard
        v-for="(plan, index) in pricingPlans"
        :key="index"
        hover
        padding="none"
        :class="['pricing-card', { 'pricing-card-popular': plan.isPopular }]"
      >
        <div class="pricing-header" :style="{ '--plan-accent': plan.color }">
          <h3 class="pricing-name">{{ plan.name }}</h3>
          <div class="pricing-price">
            <span class="price-amount">{{ plan.price }}</span>
            <span class="price-unit" v-if="plan.priceUnit">{{ plan.priceUnit }}</span>
          </div>
          <div v-if="plan.hasTrial" class="pricing-trial">
            {{ plan.trialText }}
          </div>
          <div v-if="plan.note" class="pricing-note">
            {{ plan.note }}
          </div>
        </div>
        <div class="pricing-features">
          <div
            v-for="(feature, featureIndex) in plan.features"
            :key="featureIndex"
            class="feature-group"
          >
            <h4 class="feature-category">{{ feature.category }}</h4>
            <ul v-if="feature.items && feature.items.length > 0" class="feature-list">
              <li v-for="(item, itemIndex) in feature.items" :key="itemIndex" class="feature-item">
                {{ item }}
              </li>
            </ul>
          </div>
        </div>
      </KCard>
    </div>

    <div v-if="showContactInfo" class="contact-info">
      <el-alert type="info" :closable="false" show-icon>
        <template #title>
          <span class="contact-title">请联系网站管理员获取VIP</span>
        </template>
      </el-alert>
    </div>
  </div>
</template>

<style scoped>
.vip-pricing-plans {
  width: 100%;
}

.pricing-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 32px;
  margin-bottom: 32px;
  /* 三张卡等高，底部对齐；原来用 start 会参差不齐 */
  align-items: stretch;
}

.pricing-card {
  border-radius: var(--k-radius-lg);
  transition: border-color 0.25s ease, box-shadow 0.25s ease, transform 0.25s ease;
  overflow: hidden;
  background: var(--k-color-surface);
  border: 1px solid var(--k-color-border);
  position: relative;
  /* 让卡片内部纵向撑满，内容少的那张也不会矮一截 */
  display: flex;
  flex-direction: column;
  height: 100%;
}

/* KCard 默认 body 有 24px 内边距，会把顶部强调条和分区背景隔开，这里清掉 */
.pricing-card :deep(.k-card__body) {
  padding: 0;
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

.pricing-card:hover {
  transform: translateY(-4px);
  border-color: color-mix(in srgb, var(--k-color-primary) 45%, var(--k-color-border));
  box-shadow: var(--k-shadow-md);
}

.pricing-card-popular {
  border-color: var(--k-color-primary);
  box-shadow: 0 8px 24px color-mix(in srgb, var(--k-color-primary) 22%, transparent);
}

/* 「推荐」改成卡片右上角的胶囊徽标，不再用会溢出圆角的斜角丝带 */
.pricing-card-popular::before {
  content: '推荐';
  position: absolute;
  top: 14px;
  right: 14px;
  background: var(--k-color-primary);
  color: var(--k-color-text-inverse);
  padding: 2px 10px;
  border-radius: var(--k-radius-pill);
  font-size: var(--k-font-xs);
  font-weight: 600;
  letter-spacing: 0.02em;
  z-index: 10;
  box-shadow: 0 2px 8px color-mix(in srgb, var(--k-color-primary) 30%, transparent);
}

.pricing-header {
  position: relative;
  padding: 32px 24px;
  text-align: center;
  background: var(--k-color-surface);
}

/* 顶部强调色条：用伪元素画，跟着卡片圆角走，不会再悬空成一条线 */
.pricing-header::before {
  content: '';
  position: absolute;
  inset: 0 0 auto 0;
  height: 4px;
  background: var(--plan-accent, var(--k-color-primary));
}

.pricing-name {
  font-size: 24px;
  font-weight: 600;
  color: var(--k-color-text);
  margin: 0 0 16px 0;
}

.pricing-price {
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: 8px;
  margin-bottom: 16px;
}

.price-amount {
  font-size: 42px;
  font-weight: 700;
  color: var(--k-color-text);
  line-height: 1;
}

.price-unit {
  font-size: 16px;
  color: var(--k-color-text-secondary);
  font-weight: 500;
}

.pricing-trial {
  display: inline-block;
  background: linear-gradient(135deg, var(--k-color-warning) 0%, color-mix(in srgb, var(--k-color-warning) 62%, var(--k-color-tint)) 100%);
  color: #201804;
  padding: 6px 16px;
  border-radius: var(--k-radius-pill);
  font-size: var(--k-font-sm);
  font-weight: 600;
  margin-top: 8px;
  box-shadow: 0 2px 8px color-mix(in srgb, var(--k-color-warning) 30%, transparent);
}

.pricing-note {
  font-size: 12px;
  color: var(--k-color-text-secondary);
  margin-top: 12px;
  line-height: 1.5;
}

/* 深色模式：KCard 的底/描边/文字全部走 --k-* token，深浅自动切换，
   原先给 .el-card/.el-card__body 补的两条深色覆盖变成同值重复声明，已删除。 */

.pricing-features {
  padding: 24px;
  /* 撑满剩余高度，让三张卡的底部对齐 */
  flex: 1;
}

.feature-group {
  margin-bottom: 24px;
}

.feature-group:last-child {
  margin-bottom: 0;
}

.feature-category {
  font-size: 16px;
  font-weight: 600;
  color: var(--k-color-text);
  margin: 0 0 12px 0;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--k-color-border);
}

.feature-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.feature-item {
  font-size: 14px;
  color: var(--k-color-text-secondary);
  line-height: 1.8;
  padding: 6px 0;
  padding-left: 20px;
  position: relative;
  /* 减少中文换行出现单字孤行 */
  text-wrap: pretty;
}

.feature-item::before {
  content: '✓';
  position: absolute;
  left: 0;
  color: var(--k-color-success);
  font-weight: 600;
}

.contact-info {
  margin-top: 32px;
  padding: 0 8px;
}

.contact-title {
  font-size: 16px;
  font-weight: 500;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .pricing-grid {
    grid-template-columns: 1fr;
    gap: 24px;
  }

  .pricing-card-popular::before {
    top: 12px;
    right: 12px;
  }

  .price-amount {
    font-size: 36px;
  }

  .pricing-header {
    padding: 24px 20px;
  }

  .pricing-features {
    padding: 20px;
  }
}
</style>
