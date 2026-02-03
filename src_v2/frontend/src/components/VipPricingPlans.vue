<script setup lang="ts">
import { pricingPlans } from '@/data/pricingPlans'

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
      <el-card
        v-for="(plan, index) in pricingPlans"
        :key="index"
        shadow="hover"
        :class="['pricing-card', { 'pricing-card-popular': plan.isPopular }]"
      >
        <div class="pricing-header" :style="{ borderTopColor: plan.color }">
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
      </el-card>
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
}

.pricing-card {
  border-radius: 16px;
  transition: all 0.3s ease;
  overflow: hidden;
  background: white;
  border: 2px solid transparent;
  position: relative;
}

.pricing-card:hover {
  transform: translateY(-8px);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.15);
}

.pricing-card-popular {
  border-color: #409eff;
  box-shadow: 0 8px 24px rgba(64, 158, 255, 0.2);
}

.pricing-card-popular::before {
  content: '推荐';
  position: absolute;
  top: 16px;
  right: -32px;
  background: #409eff;
  color: white;
  padding: 4px 40px;
  font-size: 12px;
  font-weight: 600;
  transform: rotate(45deg);
  z-index: 10;
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.3);
}

.pricing-header {
  padding: 32px 24px;
  text-align: center;
  border-top: 4px solid;
  background: linear-gradient(to bottom, rgba(255, 255, 255, 0.95), rgba(255, 255, 255, 0.85));
}

.pricing-name {
  font-size: 24px;
  font-weight: 600;
  color: #2c3e50;
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
  color: #2c3e50;
  line-height: 1;
}

.price-unit {
  font-size: 16px;
  color: #64748b;
  font-weight: 500;
}

.pricing-trial {
  display: inline-block;
  background: linear-gradient(135deg, #e6a23c 0%, #f0c674 100%);
  color: white;
  padding: 6px 16px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 600;
  margin-top: 8px;
  box-shadow: 0 2px 8px rgba(230, 162, 60, 0.3);
}

.pricing-note {
  font-size: 12px;
  color: #909399;
  margin-top: 12px;
  line-height: 1.5;
}

.pricing-features {
  padding: 24px;
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
  color: #2c3e50;
  margin: 0 0 12px 0;
  padding-bottom: 8px;
  border-bottom: 1px solid #e4e7ed;
}

.feature-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.feature-item {
  font-size: 14px;
  color: #64748b;
  line-height: 1.8;
  padding: 6px 0;
  padding-left: 20px;
  position: relative;
}

.feature-item::before {
  content: '✓';
  position: absolute;
  left: 0;
  color: #67c23a;
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
    right: -28px;
    padding: 3px 35px;
    font-size: 11px;
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
