<script setup lang="ts">
import { computed } from 'vue'
import { Box, Document, InfoFilled, Loading, Search, WarningFilled } from '@element-plus/icons-vue'

/**
 * KEmpty — 统一空状态
 * ---------------------------------------------------------------
 * 结构固定为三件套：**一个图标 + 一句「为什么空」 + 一个主操作**（操作可选）。
 * 收敛此前 23 个文件里 39 处 `el-empty description="暂无数据"`（+ 各自样式）。
 *
 * 原则：
 *  - `why` 必须是「为什么」，不是复述「空的」。写「还没有创建计划」而不是「暂无数据」；
 *  - 最多一个主操作按钮（克制，避免空状态变成第二个工具栏）；
 *  - 图标/文字/间距全部 `--k-*` token，深浅色自动切换。
 */
const props = withDefaults(
  defineProps<{
    /** 为什么是空的（一句话，必填） */
    why: string
    /** 补充说明：下一步怎么做 / 数据从哪来 */
    hint?: string
    /** 图标语义 */
    icon?: 'empty' | 'search' | 'error' | 'info' | 'loading' | 'doc'
    /** 主操作文案；不传则不渲染按钮（可用 #action 插槽自定义） */
    actionText?: string
    /** 主操作 loading */
    actionLoading?: boolean
    /** 尺寸：sm 表格内 / md 卡片内 / lg 整页 */
    size?: 'sm' | 'md' | 'lg'
    /** 贴边紧凑模式（放进表格 #empty 或窄卡片时用） */
    inline?: boolean
  }>(),
  { hint: '', icon: 'empty', actionText: '', actionLoading: false, size: 'md', inline: false }
)

const emit = defineEmits<{ (e: 'action'): void }>()

const ICONS = {
  empty: Box,
  search: Search,
  error: WarningFilled,
  info: InfoFilled,
  loading: Loading,
  doc: Document,
}

const iconComp = computed(() => ICONS[props.icon] ?? Box)
const iconSize = computed(() => (props.size === 'sm' ? 20 : props.size === 'lg' ? 40 : 28))
</script>

<template>
  <div
    class="k-empty"
    :class="[`k-empty--${size}`, inline ? 'k-empty--inline' : '', icon === 'loading' ? 'is-loading' : '']"
    role="status"
  >
    <span class="k-empty__icon" aria-hidden="true">
      <el-icon :size="iconSize"><component :is="iconComp" /></el-icon>
    </span>

    <p class="k-empty__why" :title="why">{{ why }}</p>
    <p v-if="hint" class="k-empty__hint" :title="hint">{{ hint }}</p>

    <div v-if="$slots.action || actionText" class="k-empty__action">
      <slot name="action">
        <el-button type="primary" :loading="actionLoading" @click="emit('action')">
          {{ actionText }}
        </el-button>
      </slot>
    </div>

    <slot />
  </div>
</template>

<style scoped>
.k-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--k-space-2);
  padding: var(--k-space-6) var(--k-space-4);
  text-align: center;
  color: var(--k-color-text-secondary);
  min-width: 0;
}

.k-empty--sm {
  gap: var(--k-space-1);
  padding: var(--k-space-4) var(--k-space-3);
}

.k-empty--lg {
  gap: var(--k-space-3);
  padding: var(--k-space-7) var(--k-space-5);
}

.k-empty--inline {
  padding: var(--k-space-4) var(--k-space-3);
}

.k-empty__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--k-color-text-tertiary);
}

.k-empty.is-loading .k-empty__icon {
  animation: k-empty-spin 1.4s linear infinite;
}

@keyframes k-empty-spin {
  to {
    transform: rotate(360deg);
  }
}

.k-empty__why {
  margin: 0;
  max-width: 42ch;
  font-size: var(--k-font-md);
  font-weight: 600;
  line-height: 1.5;
  color: var(--k-color-text-secondary);
  overflow-wrap: anywhere;
}

.k-empty--sm .k-empty__why {
  font-size: var(--k-font-sm);
}

.k-empty__hint {
  margin: 0;
  max-width: 52ch;
  font-size: var(--k-font-xs);
  line-height: 1.6;
  color: var(--k-color-text-tertiary);
  overflow-wrap: anywhere;
}

.k-empty__action {
  margin-top: var(--k-space-2);
  display: flex;
  align-items: center;
  gap: var(--k-space-2);
}

.k-empty--sm .k-empty__action {
  margin-top: var(--k-space-1);
}
</style>
