import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import EsiModuleStatus from '../esiModuleStatus.vue'

describe('EsiModuleStatus', () => {
  const mountComponent = () =>
    mount(EsiModuleStatus, {
      global: {
        stubs: {
          'el-tabs': {
            name: 'ElTabs',
            template: '<div class="el-tabs-stub"><slot /></div>',
            props: ['modelValue'],
          },
          'el-tab-pane': {
            name: 'ElTabPane',
            template: '<div class="el-tab-pane-stub"><slot /></div>',
            props: ['label', 'name'],
          },
          'el-alert': {
            name: 'ElAlert',
            template: '<div><slot name="title" /><slot /></div>',
            props: ['type', 'closable', 'showIcon'],
          },
          'el-input': {
            name: 'ElInput',
            template: '<div><slot name="prefix" /><slot /></div>',
            props: ['modelValue', 'placeholder', 'clearable', 'style'],
          },
          'el-select': {
            name: 'ElSelect',
            template: '<div><slot /></div>',
            props: ['modelValue', 'placeholder', 'style'],
          },
          'el-option': {
            name: 'ElOption',
            template: '<div />',
            props: ['label', 'value'],
          },
          'el-table': {
            name: 'ElTable',
            template: '<div><slot /></div>',
            props: ['data', 'loading', 'stripe', 'style'],
          },
          'el-table-column': {
            name: 'ElTableColumn',
            template: '<div><slot :row="{}" /></div>',
            props: ['label', 'width', 'minWidth', 'fixed', 'prop', 'align'],
          },
          'el-tag': {
            name: 'ElTag',
            template: '<span><slot /></span>',
            props: ['type', 'size', 'effect'],
          },
          'el-button': {
            name: 'ElButton',
            template: '<button><slot /></button>',
            props: ['size', 'type', 'disabled'],
          },
          'el-icon': {
            name: 'ElIcon',
            template: '<span><slot /></span>',
          },
          'el-card': {
            name: 'ElCard',
            template: '<div class="el-card-stub"><slot /></div>',
            props: ['shadow'],
          },
          'el-progress': {
            name: 'ElProgress',
            template: '<div class="el-progress-stub" />',
            props: ['percentage', 'color', 'strokeWidth', 'status'],
          },
        },
      },
    })

  it('组件能够正常渲染', () => {
    const wrapper = mountComponent()
    expect(wrapper.find('.esi-module-status').exists()).toBe(true)
  })

  it('包含3个标签页', () => {
    const wrapper = mountComponent()
    const tabPanes = wrapper.findAll('.el-tab-pane-stub')
    expect(tabPanes).toHaveLength(3)
  })

  it('显示 TQ 服务器状态横幅', () => {
    const wrapper = mountComponent()
    expect(wrapper.find('.tq-banner').exists()).toBe(true)
    expect(wrapper.find('.tq-label').text()).toBe('TQ 服务器状态')
  })
})
