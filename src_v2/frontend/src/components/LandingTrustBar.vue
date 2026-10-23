<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { http } from '@/http'

interface Corporation {
  id: number
  name: string
  ticker: string
  member_count: number
  icon_url: string
}

interface StatsData {
  user_count: number
  corp_count: number
  corporations: Corporation[]
}

const loading = ref(true)
const userCount = ref(0)
const corpCount = ref(0)
const corporations = ref<Corporation[]>([])
const expanded = ref(false)

const toggleExpand = () => {
  expanded.value = !expanded.value
}

onMounted(async () => {
  try {
    const resp = await http.get('/public/landing/stats')
    const json = await resp.json()
    if (json.status === 200 && json.data) {
      const d = json.data as StatsData
      userCount.value = d.user_count
      corpCount.value = d.corp_count
      corporations.value = d.corporations || []
    }
  } catch {
    // 接口不可用时静默降级，不阻塞页面
  } finally {
    loading.value = false
  }
})

// 复制一份用于无限滚动
const tickerList = computed(() => {
  const list = corporations.value
  if (list.length === 0) return []
  // 至少复制到 20 个以保证滚动连续性
  const repeated: Corporation[] = []
  while (repeated.length < Math.max(list.length * 2, 20)) {
    repeated.push(...list)
  }
  return repeated
})
</script>

<template>
  <section v-if="!loading" class="trust-bar">
    <!-- 统计数字 -->
    <div class="trust-stats">
      <div class="trust-stat">
        <span class="trust-stat-num">{{ userCount }}+</span>
        <span class="trust-stat-label">工业家在使用</span>
      </div>
      <div class="trust-divider" />
      <div class="trust-stat">
        <span class="trust-stat-num">{{ corpCount }}+</span>
        <span class="trust-stat-label">军团 / 公司</span>
      </div>
    </div>

    <!-- 公司区域 -->
    <div
      v-if="corporations.length > 0"
      class="trust-marquee-wrap"
      :class="{ 'is-expanded': expanded }"
      @click="toggleExpand"
    >
      <!-- 收起态：无限滚动（常驻 DOM，通过 opacity 隐藏） -->
      <div v-show="!expanded" class="trust-marquee-track">
        <a
          v-for="(corp, i) in tickerList"
          :key="`${corp.id}-${i}`"
          class="trust-corp-item"
          :title="`${corp.name} [${corp.ticker}] · ${corp.member_count.toLocaleString()} 成员`"
        >
          <img
            :src="corp.icon_url"
            :alt="corp.ticker"
            class="trust-corp-icon"
            loading="lazy"
            @error="($event.target as HTMLImageElement).style.display = 'none'"
          />
          <span class="trust-corp-ticker">{{ corp.ticker }}</span>
        </a>
      </div>

      <!-- 展开态：静态网格（常驻 DOM，通过 CSS transition 淡入） -->
      <div class="trust-corp-grid" :class="{ 'is-visible': expanded }">
        <a
          v-for="corp in corporations"
          :key="corp.id"
          class="trust-corp-item"
          :title="`${corp.name} [${corp.ticker}] · ${corp.member_count.toLocaleString()} 成员`"
        >
          <img
            :src="corp.icon_url"
            :alt="corp.ticker"
            class="trust-corp-icon"
            loading="lazy"
            @error="($event.target as HTMLImageElement).style.display = 'none'"
          />
          <span class="trust-corp-ticker">{{ corp.ticker }}</span>
        </a>
      </div>

      <!-- 点击提示 -->
      <div class="trust-expand-hint">{{ expanded ? '点击收起' : '点击展开全部' }}</div>
    </div>
  </section>
</template>

<style scoped>
.trust-bar {
  max-width: 1240px;
  margin: 0 auto;
  padding: 36px 20px;
  text-align: center;
}

.trust-stats {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 40px;
  margin-bottom: 28px;
}

.trust-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.trust-stat-num {
  font-size: 28px;
  font-weight: 700;
  color: var(--k-color-text);
}

.trust-stat-label {
  font-size: 14px;
  color: var(--k-color-text-secondary);
}

.trust-divider {
  width: 1px;
  height: 36px;
  background: var(--k-color-border);
}

/* 滚动容器 */
.trust-marquee-wrap {
  max-height: 64px;
  overflow: hidden;
  cursor: pointer;
  mask-image: linear-gradient(
    to right,
    transparent 0%,
    black 8%,
    black 92%,
    transparent 100%
  );
  transition:
    max-height 0.55s cubic-bezier(0.4, 0, 0.2, 1),
    mask-image 0.45s ease;
}

/* 展开态 */
.trust-marquee-wrap.is-expanded {
  max-height: 520px;
  mask-image: none;
  overflow-y: auto;
}

.trust-marquee-track {
  display: flex;
  gap: 28px;
  width: max-content;
  animation: trust-scroll 60s linear infinite;
}

/* 展开态网格 — 初始隐藏，展开时淡入 */
.trust-corp-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: center;
  padding: 4px 12px;
  opacity: 0;
  transform: translateY(-10px);
  transition:
    opacity 0.35s ease 0.1s,
    transform 0.35s ease 0.1s;
  pointer-events: none;
}

.trust-corp-grid.is-visible {
  opacity: 1;
  transform: translateY(0);
  pointer-events: auto;
}

.trust-corp-item {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  padding: 8px 16px;
  border-radius: 12px;
  background: var(--k-color-surface-soft);
  text-decoration: none;
  transition: background 0.2s;
}

.trust-corp-item:hover {
  background: var(--k-color-primary-soft);
}

.trust-corp-icon {
  width: 28px;
  height: 28px;
  border-radius: var(--k-radius-sm);
  object-fit: contain;
}

.trust-corp-ticker {
  font-size: 14px;
  font-weight: 600;
  color: var(--k-color-text-secondary);
  letter-spacing: 0.02em;
}

/* 展开/收起提示 */
.trust-expand-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--k-color-text-tertiary, #999);
  transition:
    color 0.25s ease,
    opacity 0.3s ease;
  user-select: none;
}

.trust-marquee-wrap:not(.is-expanded):hover .trust-expand-hint {
  color: var(--k-color-primary);
}

@keyframes trust-scroll {
  0% {
    transform: translateX(0);
  }
  100% {
    transform: translateX(-50%);
  }
}

/* 响应式 */
@media (max-width: 768px) {
  .trust-stats {
    gap: 24px;
  }

  .trust-stat-num {
    font-size: 22px;
  }

  .trust-marquee-track {
    gap: 16px;
  }

  .trust-corp-item {
    padding: 6px 12px;
  }

  .trust-corp-icon {
    width: 22px;
    height: 22px;
  }
}
</style>
