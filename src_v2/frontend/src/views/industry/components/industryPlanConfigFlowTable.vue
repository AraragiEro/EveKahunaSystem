<template>
  <div class="table-container">
    <el-scrollbar class="table-scrollbar">
      <table class="card-table" :class="{ 'compact-mode': cardStyleMode === 'compact' }">
        <thead>
          <tr class="table-header">
            <th>配置类型</th>
            <th>配置描述</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody class="industry-plan-config-flow-table">
          <tr v-for="item in list" :key="item.config_id" class="card-row cursor-move"
            :class="{ 'compact-mode': cardStyleMode === 'compact' }">
            <td class="config-type-name">
              <el-tag
                :size="cardStyleMode === 'compact' ? 'small' : undefined"
                :class="['config-type-tag', `config-type-tag-${item.config_type}`]"
                type="light"
              >
                {{ configTypeMap[item.config_type] }}
              </el-tag>
            </td>
            <td class="config-description">
              <el-tooltip :content="formatConfigValue(item.config_type, item.config_value)" placement="top"
                effect="dark" :popper-options="{ modifiers: [{ name: 'offset', options: { offset: [0, 8] } }] }">
                <div class="config-description-text" v-if="item.config_tag">
                  {{ item.config_tag }}
                </div>
                <div class="config-description-text" v-else>
                  {{ formatConfigValue(item.config_type, item.config_value) }}
                </div>
              </el-tooltip>
            </td>
            <td class="action-cell">
              <el-tooltip content="修改配置" placement="top">
                <el-button text :icon="Edit" :size="cardStyleMode === 'compact' ? 'small' : undefined"
                  aria-label="修改配置" @click="handleModifyConfigFlow(item)" />
              </el-tooltip>
              <el-tooltip content="删除配置" placement="top">
                <el-button text type="danger" :icon="Delete"
                  :size="cardStyleMode === 'compact' ? 'small' : undefined" aria-label="删除配置"
                  @click="handleDeleteConfigFlowConfig(item)" />
              </el-tooltip>
            </td>
          </tr>
        </tbody>
      </table>
      <!-- 空态：列表为空时给「为什么空 + 下一步」，不再用 tbody::after 伪装文案 -->
      <KEmpty v-if="!list.length" why="还没有配置流程" hint="从配置库把配置添加到计划后，这里会按配置顺序生成流程"
        size="sm" inline />
    </el-scrollbar>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { http } from '@/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Edit } from '@element-plus/icons-vue'
import KEmpty from '@/components/k/KEmpty.vue'

interface PlanConfigObject {
  "config_id": number,
  "config_tag"?: string,
  "config_index_id": number,
  "config_type": string,
  "config_value": object
}
interface Props {
  list: PlanConfigObject[]
  cardStyleMode?: 'normal' | 'compact'
}
const props = withDefaults(defineProps<Props>(), {
  cardStyleMode: 'normal'
})

const emit = defineEmits<{
  'modify-config-flow': [item: PlanConfigObject]
  'delete-config-flow': [item: PlanConfigObject]
}>()

const handleModifyConfigFlow = (item: PlanConfigObject) => {
  emit('modify-config-flow', item)
}

const configTypeMap = ref<{ [key: string]: string }>({
  "StructureRigConfig": "建筑插件",
  "StructureAssignConf": "建筑分配",
  "MaterialTagConf": "原材料标记",
  "DefaultBlueprintConf": "缺省蓝图参数",
  "LoadAssetConf": "载入库存",
    "MaxJobSplitCountConf": "最大作业拆分控制",
    "TaxConfig": "税收"
})

const handleDeleteConfigFlowConfig = async (item: PlanConfigObject) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除配置流程「${item.config_tag || item.config_id}」吗？此操作不可撤销。`,
      '删除配置流程',
      {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消'
      }
    )
  } catch {
    // 用户取消
    return
  }
  emit('delete-config-flow', item)
}

const formatConfigValue = (type: string, value: any) => {
  // 如果 value 是字符串，先解析为对象
  let parsedValue = value
  if (typeof value === 'string') {
    try {
      parsedValue = JSON.parse(value)
    } catch (e) {
      console.error("解析 config_value 失败:", e)
      return String(value)
    }
  }

  // 使用 parsedValue 而不是 value
  if (type === 'StructureRigConfig') {
    return `建筑: ${parsedValue.structure_name || 'N/A'}, 时间效率等级: ${parsedValue.time_eff_level ?? 0}, 材料效率等级: ${parsedValue.mater_eff_level ?? 0}`
  } else if (type === 'StructureAssignConf') {
    const keywordGroups = parsedValue.keyword_groups || []
    const keywords = keywordGroups.map((kg: any) => `${kg.keyword}(${kg.keyword_type})`).join(', ') || 'N/A'
    return `建筑: ${parsedValue.structure_name || 'N/A'}, 关键词组: ${keywords}`
  } else if (type === 'MaterialTagConf') {
    const keywordGroups = parsedValue.keyword_groups || []
    const keywords = keywordGroups.map((kg: any) => `${kg.keyword}(${kg.keyword_type})`).join(', ') || 'N/A'
    return `原材料标记: ${keywords}`
  } else if (type === 'DefaultBlueprintConf') {
    const keywordGroups = parsedValue.keyword_groups || []
    const keywords = keywordGroups.map((kg: any) => `${kg.keyword}(${kg.keyword_type})`).join(', ') || 'N/A'
    return `关键词组: ${keywords}, 时间效率: ${parsedValue.time_eff ?? 0}, 材料效率: ${parsedValue.mater_eff ?? 0}`
  } else if (type === 'LoadAssetConf') {
    return `库存许可: ${parsedValue.tag || parsedValue.container_tag || 'N/A'}`
  } else if (type === 'MaxJobSplitCountConf') {
    const keywordGroups = parsedValue.keyword_groups || []
    const keywords = keywordGroups.map((kg: any) => `${kg.keyword}(${kg.keyword_type})`).join(', ') || 'N/A'
    return `作业类型: ${keywords}, 判断类型: ${parsedValue.judge_type}, 最大数量: ${parsedValue.max_count}, 最大时间: ${parsedValue.max_time_day}天${parsedValue.max_time_date}`
  } else if (type === 'TaxConfig') {
    return `目标类别: ${parsedValue.target_category || 'N/A'}, 税率: ${parsedValue.tax_rate ?? 0}%`
  }

  return JSON.stringify(parsedValue)
}

const configTypeColorMap = ref<{ [key: string]: string }>({
  "StructureRigConfig": "#9fcfff",
  "StructureAssignConf": "#baff97",
  "MaterialTagConf": "#f7d095",
  "DefaultBlueprintConf": "#ffbaba",
  "LoadAssetConf": "#ffe3e3",
    "MaxJobSplitCountConf": "#cacdd3",
    "TaxConfig": "#f0a58f"
})

</script>

<style scoped>
.table-container {
  width: 100%;
  height: 100%;
  padding: 8px 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.table-scrollbar {
  flex: 1;
  min-height: 0;
}

.card-table {
  width: 100%;
  table-layout: fixed;
  /* 使用固定布局，更好地控制列宽 */
  border-collapse: separate;
  border-spacing: 0 6px;
  background: transparent;
}

.card-table.compact-mode {
  border-spacing: 0;
}

.table-header {
  background: transparent;
}

.table-header th {
  padding: 12px 16px;
  text-align: left;
  font-weight: 600;
  font-size: 14px;
  color: var(--k-color-text-secondary);
  border: none;
  background: transparent;
}

.table-header th:first-child {
  width: 110px;
  min-width: 110px;
  max-width: 110px;
}

.table-header th:nth-child(2) {
  /* 中间列不设置宽度，自动填充剩余空间 */
}

.table-header th:last-child {
  width: 84px;
}

.industry-plan-config-flow-table {
  display: table-row-group;
}

.card-row {
  background: var(--k-color-surface);
  border-radius: 12px;
  box-shadow: var(--k-shadow-sm);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  margin-bottom: 12px;
  display: table-row;
  border: none;
}

.card-row:hover {
  box-shadow: var(--k-shadow-sm);
  transform: translateY(-2px);
  background: var(--k-color-surface);
}

.card-row td {
  padding: 16px;
  border: none;
  background: transparent;
  vertical-align: middle;
}

.card-row.compact-mode td {
  padding: 1px 8px;
  height: calc(1em + 2px);
  line-height: 1em;
}

.card-row:first-child td:first-child {
  border-top-left-radius: 12px;
}

.card-row:first-child td:last-child {
  border-top-right-radius: 12px;
}

.card-row:last-child td:first-child {
  border-bottom-left-radius: 12px;
}

.card-row:last-child td:last-child {
  border-bottom-right-radius: 12px;
}

.config-type-name {
  font-size: 15px;
  font-weight: 500;
  color: var(--k-color-text);
  width: 110px;
  /* 固定第一列宽度 */
  min-width: 110px;
  max-width: 110px;
}

.compact-mode .config-type-name {
  font-size: 14px;
}

.config-description {
  font-size: 14px;
  color: var(--k-color-text-secondary);
  position: relative;
  /* 中间列自动填充剩余空间，不设置宽度 */
  overflow: hidden;
}

.compact-mode .config-description {
  font-size: 13px;
}

.config-description-text {
  line-height: 1.55;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  white-space: normal;
  width: 100%;
  cursor: help;
  font-size: var(--k-font-sm);
  font-weight: 500;
  color: var(--k-color-text);
}

.action-cell {
  width: 84px;
  min-width: 84px;
  max-width: 84px;
  text-align: right;
  white-space: nowrap;
}

.action-cell .el-button {
  width: 30px;
  padding: 0;
  margin-left: 4px;
  transition: color 0.2s ease;
}

.action-cell .el-button:first-child {
  margin-left: 0;
}

.compact-mode .action-cell {
  width: auto;
  display: flex;
  gap: 4px;
  justify-content: flex-end;
}

.compact-mode .action-cell .el-button {
  padding: 4px;
  min-height: auto;
  margin-left: 0;
}

/* 拖拽时的视觉反馈 */
.card-row.sortable-ghost {
  opacity: 0.5;
  background: var(--k-color-surface-soft);
}

.card-row.sortable-drag {
  opacity: 0.8;
  box-shadow: var(--k-shadow-md);
}

/* 响应式设计 */
@media (max-width: 768px) {
  .table-container {
    padding: 4px 0;
  }

  .card-table {
    border-spacing: 0 8px;
  }

  .card-row td {
    padding: 12px;
  }

  .config-type-name {
    font-size: 14px;
    width: 110px;
    min-width: 110px;
    max-width: 110px;
  }

  .config-description {
    font-size: 13px;
  }

  .action-cell {
    width: 150px;
  }

  .action-cell .el-button {
    padding: 8px 12px;
    font-size: 12px;
  }

  .table-header th {
    padding: 10px 12px;
    font-size: 13px;
  }

  .table-header th:first-child {
    width: 110px;
    min-width: 110px;
    max-width: 110px;
  }

  .table-header th:last-child {
    width: 110px;
    min-width: 110px;
    max-width: 110px;
  }
}

/* 空态已交给 KEmpty 组件（模板里 v-if="!list.length"），这里不再用 :empty 伪元素
   伪造「暂无配置」文案——伪元素既不可访问，也无法承载下一步说明。 */

/* 隐藏横向滚动条 */
:deep(.el-scrollbar__bar.is-horizontal) {
  display: none;
}

/* 确保内容不会超出容器，禁止横向滚动 */
:deep(.el-scrollbar__wrap) {
  overflow-x: hidden;
  overflow-y: auto;
}

/* 优化 tooltip 样式 */
:deep(.el-tooltip__popper) {
  max-width: 500px;
  word-break: break-word;
  white-space: normal;
}

/* Theme override
   这一段与文件前半部分的自有选择器完全同权重，靠「写在后面」取胜即可，
   不需要强制优先级；只有会和 theme.css 里带强制优先级的通用规则抢的声明
   （标签边框色、行尾按钮的文字色）才保留。 */
.table-container,
.card-table,
.card-row,
.table-header,
.industry-plan-config-flow-table {
  background: var(--k-color-surface);
  border-color: var(--k-color-border);
  color: var(--k-color-text);
}

.table-header th,
.config-description {
  color: var(--k-color-text-secondary);
}

.config-type-name,
.config-description-text {
  color: var(--k-color-text);
}

.card-row {
  box-shadow: var(--k-shadow-sm);
}

.card-row:hover {
  box-shadow: var(--k-shadow-md);
  background: color-mix(in srgb, var(--k-color-primary) 8%, var(--k-color-surface-soft));
}

/* 每个标签都同时带 .config-type-tag-* 分组类，下面分组规则同权重且更靠后，
   这里的 border-color / color 永远不会生效，遂去掉强制优先级。 */
:deep(.el-tag) {
  border-color: color-mix(in srgb, var(--k-color-primary) 30%, var(--k-color-border));
  color: var(--k-color-text);
}

:deep(.config-type-tag) {
  border-width: 1px;
  border-style: solid;
}

/* 配置类型标签收敛到 4 个色系：结构=主色、材料=成功色、规则=警示色、中性=灰
   边框色保留强制优先级：theme.css 用 `html .el-tag` 统一标签边框色（并在持续收敛权重），
   保留强压可确保全局规则一收紧也不会把上面的分组配色盖掉；背景/文字色没有对手，去掉。 */
:deep(.config-type-tag-StructureRigConfig),
:deep(.config-type-tag-StructureAssignConf) {
  background: color-mix(in srgb, var(--k-color-primary) 18%, var(--k-color-surface-soft));
  border-color: color-mix(in srgb, var(--k-color-primary) 38%, var(--k-color-border)) !important;
  color: color-mix(in srgb, var(--k-color-primary) 78%, var(--k-color-text));
}

:deep(.config-type-tag-MaterialTagConf),
:deep(.config-type-tag-LoadAssetConf) {
  background: color-mix(in srgb, var(--k-color-success) 16%, var(--k-color-surface-soft));
  border-color: color-mix(in srgb, var(--k-color-success) 36%, var(--k-color-border)) !important;
  color: color-mix(in srgb, var(--k-color-success) 74%, var(--k-color-text));
}

:deep(.config-type-tag-TaxConfig),
:deep(.config-type-tag-DefaultBlueprintConf) {
  background: color-mix(in srgb, var(--k-color-warning) 16%, var(--k-color-surface-soft));
  border-color: color-mix(in srgb, var(--k-color-warning) 36%, var(--k-color-border)) !important;
  color: color-mix(in srgb, var(--k-color-warning) 72%, var(--k-color-text));
}

:deep(.config-type-tag-MaxJobSplitCountConf) {
  background: var(--k-color-surface-soft);
  border-color: var(--k-color-border) !important;
  color: var(--k-color-text-secondary);
}

/* 行尾操作是图标按钮，不再套用全局按钮的渐变外壳。
   EP 的文本按钮最终取色自 --el-button-text-color，这里直接改这个变量最可靠。
   结构性复位（边框/底色/阴影/圆角）由 theme.css 的 `.el-button.is-text` 已经给到
   transparent / none，去掉强制优先级不会回退；文字色保留，否则会被全局文本按钮的
   主色盖掉。 */
.action-cell :deep(.el-button) {
  --el-button-text-color: var(--k-color-text-secondary);
  --el-button-hover-text-color: var(--k-color-primary);
  border: none;
  background: transparent;
  background-image: none;
  box-shadow: none;
  color: var(--k-color-text-secondary) !important;
  border-radius: var(--k-radius-xs);
}

.action-cell :deep(.el-button:hover) {
  transform: none;
  background: color-mix(in srgb, var(--k-color-primary) 14%, transparent) !important;
  color: var(--k-color-primary) !important;
}

/* 删除图标常态用压暗的危险色（直接打在 svg 上最稳），hover 才亮起来。
   图标自身声明优先于继承色，不需要强制优先级。 */
.action-cell :deep(.el-button.el-button--danger .el-icon),
.action-cell :deep(.el-button.el-button--danger svg) {
  color: color-mix(in srgb, var(--k-color-danger) 68%, var(--k-color-text-secondary));
  fill: currentColor;
}

/* hover 态取色与 theme.css 的危险文本按钮完全一致（同为危险色 14% 叠加），
   因此可以直接沿用 theme.css 的强制优先级声明。 */
.action-cell :deep(.el-button.el-button--danger:hover) {
  background: color-mix(in srgb, var(--k-color-danger) 14%, transparent);
  color: var(--k-color-danger);
}
</style>
