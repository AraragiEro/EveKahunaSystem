<script setup lang="ts">
import { ref } from 'vue'
import { Aim, Connection, Tickets, Money, ShoppingCart } from '@element-plus/icons-vue'
import KCard from '@/components/k/KCard.vue'

interface UtilityItem {
  name: string
  description: string
  icon: any
  url: string
}

const utils = ref<UtilityItem[]>([
  {
    name: 'ZKB',
    description: 'KB网',
    icon: Aim,
    url: 'https://zkillboard.com/',
  },
  {
    name: 'SEAT\n小肥猪火锅城',
    description: 'FRT IT系统',
    icon: Connection,
    url: 'https://seat.winterco.org/',
  },
  {
    name: '联盟合同',
    description: '联盟合同',
    icon: Tickets,
    url: '/allianceContract',
  },
  {
    name: 'LP商店',
    description: '势力军团LP价值评估与排行',
    icon: ShoppingCart,
    url: '/corpShop',
  },
  {
    name: '估价器',
    description: '物品估价工具',
    icon: Money,
    url: '/utils/estimator',
  },
  {
    name: '行星工业',
    description: 'P2-P4 利润分析',
    icon: Money,
    url: '/utils/piProfit',
    newWindow: true,
  },
])

const isExternal = (url: string): boolean => url.startsWith('http')
</script>

<template>
  <el-container class="utils-view">
    <el-header class="utils-header">
      <div class="header-content">
        <div class="header-accent" />
        <h1>实用工具</h1>
        <p class="header-subtitle">实用工具集合</p>
      </div>
      <div class="header-glow" />
    </el-header>

    <el-main class="utils-main">
      <div class="utils-grid">
        <template v-for="item in utils" :key="item.name">
          <a
            v-if="isExternal(item.url) || item.newWindow"
            :href="item.url"
            target="_blank"
            rel="noopener noreferrer"
            class="card-link"
          >
            <KCard class="utils-card" padding="none">
              <div class="card-inner">
                <div class="icon-wrap">
                  <el-icon :size="40" class="card-icon">
                    <component :is="item.icon" />
                  </el-icon>
                </div>
                <h3 class="card-title">{{ item.name }}</h3>
                <p class="card-desc">{{ item.description }}</p>
              </div>
            </KCard>
          </a>

          <router-link
            v-else
            :to="item.url"
            class="card-link"
          >
            <KCard class="utils-card" padding="none">
              <div class="card-inner">
                <div class="icon-wrap">
                  <el-icon :size="40" class="card-icon">
                    <component :is="item.icon" />
                  </el-icon>
                </div>
                <h3 class="card-title">{{ item.name }}</h3>
                <p class="card-desc">{{ item.description }}</p>
              </div>
            </KCard>
          </router-link>
        </template>
      </div>
    </el-main>
  </el-container>
</template>

<style scoped>
.utils-view {
  height: 100%;
  display: flex;
  flex-direction: column;
}

/* Header */
.utils-header {
  position: relative;
  flex-shrink: 0;
  margin: 16px 24px 0;
  padding: 0 24px;
  height: auto;
  min-height: 72px;
  display: flex;
  align-items: center;
  background: var(--k-color-surface);
  border: 1px solid var(--k-color-border);
  border-radius: var(--k-radius-md);
  overflow: hidden;
}

.utils-header::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(
    90deg,
    color-mix(in srgb, var(--k-color-primary) 70%, transparent) 0%,
    color-mix(in srgb, var(--k-color-primary) 20%, transparent) 60%,
    transparent 100%
  );
}

.header-content {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-accent {
  width: 4px;
  height: 28px;
  border-radius: 2px;
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--k-color-primary) 90%, var(--k-color-tint)) 0%,
    var(--k-color-primary) 100%
  );
  box-shadow: 0 0 10px color-mix(in srgb, var(--k-color-primary) 45%, transparent);
}

.utils-header h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 0.04em;
  background: linear-gradient(
    135deg,
    var(--k-color-text) 0%,
    color-mix(in srgb, var(--k-color-primary) 65%, var(--k-color-text)) 100%
  );
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.header-subtitle {
  display: none;
}

.header-glow {
  position: absolute;
  top: -40%;
  right: -2%;
  width: 180px;
  height: 180px;
  border-radius: 50%;
  background: radial-gradient(
    circle,
    color-mix(in srgb, var(--k-color-primary) 18%, transparent) 0%,
    transparent 70%
  );
  pointer-events: none;
  opacity: 0.7;
}

/* Main */
.utils-main {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
}

/* Grid */
.utils-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 20px;
}

/* Link wrapper */
.card-link {
  text-decoration: none;
  color: inherit;
  display: block;
  border-radius: var(--k-radius-md);
  transition: transform 0.3s ease;
}

.card-link:hover {
  text-decoration: none;
}

/* Card */
.utils-card {
  height: 180px;
  transition:
    transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1),
    box-shadow 0.35s ease,
    border-color 0.35s ease,
    background 0.35s ease;
  cursor: pointer;
  position: relative;
  overflow: hidden;
}

.utils-card::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  pointer-events: none;
  opacity: 0;
  background:
    linear-gradient(
      120deg,
      transparent 20%,
      color-mix(in srgb, var(--k-color-primary) 12%, transparent) 50%,
      transparent 80%
    );
  transform: translateX(-100%);
  transition: transform 0.6s ease, opacity 0.4s ease;
}

.card-inner {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 20px;
  position: relative;
  z-index: 1;
}

/* Icon */
.icon-wrap {
  width: 72px;
  height: 72px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--k-color-primary) 10%, var(--k-color-surface-soft));
  border: 1px solid color-mix(in srgb, var(--k-color-primary) 18%, var(--k-color-border));
  transition:
    transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1),
    box-shadow 0.35s ease,
    background 0.35s ease,
    border-color 0.35s ease;
}

.card-icon {
  color: var(--k-color-primary);
  transition: transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}

/* Title */
.card-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--k-color-text);
  text-align: center;
  line-height: 1.4;
  white-space: pre-line;
  transition: color 0.3s ease;
}

/* Description */
.card-desc {
  margin: 0;
  font-size: 13px;
  color: var(--k-color-text-secondary);
  text-align: center;
  line-height: 1.4;
  transition: color 0.3s ease;
}

/* Hover states */
.card-link:hover .utils-card {
  transform: translateY(-6px) scale(1.02);
  border-color: color-mix(in srgb, var(--k-color-primary) 40%, var(--k-color-border));
  box-shadow:
    0 0 0 1px color-mix(in srgb, var(--k-color-primary) 25%, transparent),
    0 12px 32px color-mix(in srgb, var(--k-color-primary) 22%, transparent);
  background: color-mix(in srgb, var(--k-color-primary) 5%, var(--k-color-surface));
}

.card-link:hover .utils-card::before {
  opacity: 1;
  transform: translateX(100%);
}

.card-link:hover .icon-wrap {
  transform: scale(1.1);
  background: color-mix(in srgb, var(--k-color-primary) 16%, var(--k-color-surface-soft));
  border-color: color-mix(in srgb, var(--k-color-primary) 35%, var(--k-color-border));
  box-shadow:
    0 0 0 4px color-mix(in srgb, var(--k-color-primary) 10%, transparent),
    0 6px 20px color-mix(in srgb, var(--k-color-primary) 20%, transparent);
}

.card-link:hover .card-icon {
  transform: scale(1.08);
}

.card-link:hover .card-title {
  color: color-mix(in srgb, var(--k-color-primary) 70%, var(--k-color-text));
}

/* Active / pressed state */
.card-link:active .utils-card {
  transform: translateY(-2px) scale(1.01);
  transition-duration: 0.1s;
}

/* Responsive */
@media (max-width: 640px) {
  .utils-grid {
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 12px;
  }

  .utils-card {
    height: 160px;
  }

  .icon-wrap {
    width: 56px;
    height: 56px;
  }

  .card-icon {
    font-size: 28px !important;
  }

  .card-title {
    font-size: 14px;
  }

  .card-desc {
    font-size: 12px;
  }
}
</style>
