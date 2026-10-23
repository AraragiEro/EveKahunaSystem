<script setup lang="ts">
import { computed } from 'vue'
import logoImg from '@/assets/logo.jpg'
import {
  APP_VERSION,
  GITHUB_REPO_URL,
  OPEN_SOURCE_LICENSE,
  SITE_NAME,
  copyrightYear,
} from '@/config/site'

interface Props {
  /** compact：应用内底部细条；landing：落地页居中页脚 */
  variant?: 'compact' | 'landing'
  /** 版本号，默认取站点常量 */
  version?: string
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'compact',
  version: '',
})

const donateLink = computed(() => import.meta.env.VITE_DONATE_LINK as string | undefined)
const qqGroupNumber = computed(() => import.meta.env.VITE_QQ_GROUP as string | undefined)
const showDonate = computed(() => !!donateLink.value)
const showQQGroup = computed(() => !!qqGroupNumber.value)

const displayVersion = computed(() => props.version || APP_VERSION)
const year = copyrightYear()
</script>

<template>
  <footer class="app-footer" :class="`variant-${variant}`">
    <div class="footer-inner">
      <div class="footer-brand">
        <img :src="logoImg" :alt="SITE_NAME" class="brand-logo" width="20" height="20" />
        <span class="brand-name">{{ SITE_NAME }}</span>
        <span class="brand-version">{{ displayVersion }}</span>
      </div>

      <nav class="footer-links" aria-label="页脚导航">
        <a :href="GITHUB_REPO_URL" target="_blank" rel="noopener">GitHub</a>
        <span class="footer-sep" aria-hidden="true"></span>
        <router-link to="/announcements">公告</router-link>
        <template v-if="showQQGroup">
          <span class="footer-sep" aria-hidden="true"></span>
          <span class="footer-text">QQ群 {{ qqGroupNumber }}</span>
        </template>
        <template v-if="showDonate">
          <span class="footer-sep" aria-hidden="true"></span>
          <a :href="donateLink" target="_blank" rel="noopener">支持作者</a>
        </template>
      </nav>

      <div class="footer-legal">
        <span class="legal-copy">© {{ year }} {{ SITE_NAME }}</span>
        <span class="footer-sep" aria-hidden="true"></span>
        <span class="legal-license">{{ OPEN_SOURCE_LICENSE }}</span>
      </div>
    </div>
  </footer>
</template>

<style scoped>
.app-footer {
  position: relative;
  flex-shrink: 0;
  color: var(--k-color-text-secondary);
}

/* 头发丝分隔线：两端淡出，比整条实线安静 */
.app-footer::before {
  content: '';
  position: absolute;
  inset: 0 0 auto 0;
  height: 1px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    var(--k-color-border) 16%,
    var(--k-color-border) 84%,
    transparent 100%
  );
  pointer-events: none;
}

.footer-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}

/* ---------- 品牌区 ---------- */

.footer-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.brand-logo {
  width: 20px;
  height: 20px;
  border-radius: var(--k-radius-xs);
  object-fit: contain;
  opacity: 0.9;
}

.brand-name {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--k-color-text);
  white-space: nowrap;
}

.brand-version {
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.04em;
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--k-color-surface-soft);
  color: var(--k-color-text-secondary);
  white-space: nowrap;
}

/* ---------- 链接区 ---------- */

.footer-links {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  justify-content: center;
}

.footer-links a,
.footer-text {
  font-size: 12px;
  color: var(--k-color-text-secondary);
  text-decoration: none;
  transition: color 0.18s ease;
}

.footer-links a:hover {
  color: var(--k-color-primary);
}

.footer-sep {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.35;
  flex-shrink: 0;
}

/* ---------- 版权区 ---------- */

.footer-legal {
  display: flex;
  align-items: center;
  gap: 10px;
  white-space: nowrap;
}

.legal-copy,
.legal-license {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--k-color-text-secondary);
  opacity: 0.68;
}

/* ---------- 两种场合 ---------- */

.app-footer.variant-compact {
  height: 48px;
  padding: 0 20px;
}

.app-footer.variant-compact .footer-inner {
  height: 100%;
}

.app-footer.variant-landing {
  padding: 40px 24px 36px;
}

.app-footer.variant-landing .footer-inner {
  flex-direction: column;
  gap: 18px;
}

.app-footer.variant-landing .footer-links {
  gap: 16px;
}

.app-footer.variant-landing .footer-links a,
.app-footer.variant-landing .footer-text {
  font-size: 13px;
}

.app-footer.variant-landing .brand-name {
  font-size: 13px;
}

@media (max-width: 900px) {
  .app-footer.variant-compact {
    height: auto;
    padding: 12px 14px;
  }

  .app-footer.variant-compact .footer-inner {
    flex-direction: column;
    gap: 8px;
    align-items: flex-start;
  }

  .app-footer.variant-compact .footer-links {
    justify-content: flex-start;
  }
}
</style>
