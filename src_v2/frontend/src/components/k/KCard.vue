<script setup lang="ts">
/**
 * KCard — 统一卡片容器
 * ---------------------------------------------------------------
 * 收敛此前 33 个文件里各写一遍的 `.xxx-card` / `el-card` + `.card-header`。
 * 只做「容器」这一件事：外壳（底/描边/圆角/阴影）+ 标题区 + 正文 + 页脚。
 * 所有颜色/间距/圆角/字号都来自 `--k-*` token，深浅色由 theme.css 自动切换。
 *
 * 用法：
 *   <KCard title="最终产品成本占比"> … </KCard>
 *   <KCard title="计划列表"><template #actions><el-button>新建</el-button></template> … </KCard>
 *   <KCard flush><KTable … /></KCard>   <!-- 表格贴边，不留内边距 -->
 */
withDefaults(
  defineProps<{
    /** 标题（也可用 #header 完全自定义） */
    title?: string
    /** 标题下一行小字 */
    subtitle?: string
    /** 内边距档位：none 贴边 / sm 紧凑 / md 常规 */
    padding?: 'none' | 'sm' | 'md'
    /** 顶部语义色条，用于区分图表卡 */
    tone?: '' | 'primary' | 'success' | 'warning' | 'danger' | 'accent'
    /** hover 时抬升阴影（可点击卡片用） */
    hover?: boolean
    /** 正文内边距归零，让表格/图表自己贴边 */
    flush?: boolean
  }>(),
  { title: '', subtitle: '', padding: 'md', tone: '', hover: false, flush: false }
)
</script>

<template>
  <section
    class="k-card"
    :class="[
      `k-card--pad-${padding}`,
      tone ? `k-card--tone-${tone}` : '',
      hover ? 'k-card--hover' : '',
      flush ? 'k-card--flush' : '',
    ]"
  >
    <header v-if="title || $slots.header || $slots.actions" class="k-card__header">
      <slot name="header">
        <div class="k-card__titles">
          <h3 class="k-card__title">{{ title }}</h3>
          <p v-if="subtitle" class="k-card__subtitle">{{ subtitle }}</p>
        </div>
      </slot>
      <div v-if="$slots.actions" class="k-card__actions">
        <slot name="actions" />
      </div>
    </header>

    <div class="k-card__body">
      <slot />
    </div>

    <footer v-if="$slots.footer" class="k-card__footer">
      <slot name="footer" />
    </footer>
  </section>
</template>

<style scoped>
.k-card {
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--k-color-surface);
  border: 1px solid var(--k-color-border-subtle);
  border-radius: var(--k-radius-md);
  box-shadow: var(--k-shadow-section);
  color: var(--k-color-text);
  transition:
    box-shadow var(--k-dur-2) var(--k-ease),
    border-color var(--k-dur-2) var(--k-ease);
}

.k-card--hover:hover {
  box-shadow: var(--k-shadow-md);
  border-color: var(--k-color-border);
}

/* ── 顶部语义色条 ───────────────────────────────────────────── */
.k-card--tone-primary::before,
.k-card--tone-success::before,
.k-card--tone-warning::before,
.k-card--tone-danger::before,
.k-card--tone-accent::before {
  content: '';
  position: absolute;
  inset: 0 0 auto 0;
  height: 3px;
  border-radius: var(--k-radius-md) var(--k-radius-md) 0 0;
  background: var(--k-card-tone);
}

.k-card--tone-primary {
  --k-card-tone: var(--k-color-primary);
}
.k-card--tone-success {
  --k-card-tone: var(--k-color-success);
}
.k-card--tone-warning {
  --k-card-tone: var(--k-color-warning);
}
.k-card--tone-danger {
  --k-card-tone: var(--k-color-danger);
}
.k-card--tone-accent {
  --k-card-tone: var(--k-color-accent-1);
}

/* ── 头部 ───────────────────────────────────────────────────── */
.k-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--k-space-3);
  padding: var(--k-space-4) var(--k-space-5);
  border-bottom: 1px solid var(--k-color-border-faint);
}

.k-card__titles {
  display: flex;
  flex-direction: column;
  gap: var(--k-space-1);
  min-width: 0;
}

.k-card__title {
  margin: 0;
  font-size: var(--k-font-md);
  font-weight: 600;
  line-height: 1.4;
  color: var(--k-color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.k-card__subtitle {
  margin: 0;
  font-size: var(--k-font-xs);
  color: var(--k-color-text-secondary);
}

.k-card__actions {
  display: flex;
  align-items: center;
  gap: var(--k-space-2);
  flex: none;
}

/* ── 正文 / 页脚 ─────────────────────────────────────────────── */
.k-card__body {
  flex: 1 1 auto;
  min-width: 0;
}

.k-card--pad-md .k-card__body {
  padding: var(--k-space-5);
}
.k-card--pad-sm .k-card__body {
  padding: var(--k-space-3) var(--k-space-4);
}
.k-card--pad-none .k-card__body {
  padding: 0;
}

.k-card--flush .k-card__body {
  padding: 0;
}

.k-card__footer {
  padding: var(--k-space-3) var(--k-space-5);
  border-top: 1px solid var(--k-color-border-faint);
  background: var(--k-color-surface-soft);
  border-radius: 0 0 var(--k-radius-md) var(--k-radius-md);
}

/* 有页脚时正文不再自己收圆角，交给外壳 overflow 处理 */
.k-card--flush.k-card--pad-none .k-card__body {
  border-radius: 0;
}
</style>
