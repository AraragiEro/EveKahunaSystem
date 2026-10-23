import type { Component } from 'vue'

/**
 * KRowMenu 的菜单项定义。
 * 单独放在这里，避免调用方从 .vue 里 import 类型（script setup 不导出运行时/类型成员）。
 */
export interface KRowMenuItem {
  /** 事件回传的标识 */
  key: string
  /** 菜单文案（独立可读，别只写「移出」） */
  label: string
  /** 左侧图标（可选） */
  icon?: Component
  /** danger 色（删除类必须为 true） */
  danger?: boolean
  /** 与上一项之间加分隔线 */
  divided?: boolean
  /** 禁用（例如未公开时不能复制链接） */
  disabled?: boolean
}
