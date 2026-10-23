<script setup lang="ts">
import { MoreFilled } from '@element-plus/icons-vue'
import type { KRowMenuItem } from './types'

/**
 * KRowMenu — 行内操作的「⋯ 更多」下拉
 * ---------------------------------------------------------------
 * 表格/卡片操作列里并列 3 个以上等权按钮时，收成「1 个主操作 + ⋯」：
 *   · 主操作（高频，例如「加入计划」「管理权限」）留在外面，直接点；
 *   · 低频操作进菜单，文案要能独立看懂（「移出自选列表」而不是「移出」）；
 *   · `danger: true` 的项（删除/移出）统一 danger 色，不放在外面当主图标。
 *
 * 用法：
 *   <KRowMenu :items="menuItems" @select="onMenuSelect" />
 *   const menuItems = [{ key: 'detail', label: '查看详情', icon: View },
 *                      { key: 'remove', label: '移出自选列表', icon: Delete, danger: true, divided: true }]
 *
 * 触发器样式透传：size / circle / text 等直接写在组件上，落到内部 el-button。
 */
defineOptions({ inheritAttrs: false })

withDefaults(
  defineProps<{
    items: KRowMenuItem[]
    /** 触发器无障碍名称 */
    label?: string
  }>(),
  { label: '更多操作' }
)

const emit = defineEmits<{ (e: 'select', key: string): void }>()

const handleCommand = (key: string) => emit('select', key)
</script>

<template>
  <el-dropdown trigger="click" @command="handleCommand">
    <el-button v-bind="$attrs" class="k-row-menu__trigger" :aria-label="label" :title="label">
      <el-icon><MoreFilled /></el-icon>
    </el-button>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item
          v-for="item in items"
          :key="item.key"
          :command="item.key"
          :disabled="item.disabled"
          :divided="item.divided"
          :class="{ 'k-row-menu__danger': item.danger }"
        >
          <el-icon v-if="item.icon" class="k-row-menu__icon"><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<style scoped>
.k-row-menu__trigger {
  flex: none;
}

.k-row-menu__icon {
  margin-right: var(--k-space-1);
}

/* 删除项的颜色在 theme.css 的 popper 桥接旁统一放行（那里有 !important，
   teleport 出去的菜单项也命中），这里不再重复写颜色规则。 */
</style>
