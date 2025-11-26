<script setup lang="ts">
import { ref, computed } from 'vue'
import { Check, List, ArrowRight, CircleCheckFilled, CircleCloseFilled } from '@element-plus/icons-vue'

interface TodoItem {
  id: string
  title: string
  completed: boolean
  children?: TodoItem[]
}

// 待办事项数据
const todoItems = ref<TodoItem[]>([
  {
    id: 'web-platform',
    title: 'Web 应用平台开发',
    completed: true,
    children: [
      { id: 'frontend', title: '前端框架搭建', completed: true },
      { id: 'esi-queue', title: 'ESI 访问队列控制', completed: true },
      {
        id: 'database',
        title: '数据库重构',
        completed: true,
        children: [
          { id: 'postgres-redis', title: 'PostgreSQL 和 Redis 部署', completed: true }
        ]
      }
    ]
  },
  {
    id: 'core-features',
    title: '核心功能',
    completed: false,
    children: [
      {
        id: 'industry-plan',
        title: '工业计划的计算与拆解',
        completed: true,
        children: [
          { id: 'product-list', title: '可调整的产品清单', completed: true },
          { id: 'calc-config', title: '可调整的计算配置', completed: true },
        ]
      },
      {
        id: 'data-report',
        title: '详细的数据报表',
        completed: false,
        children: [
          { id: 'plan-tree', title: '计划分解树', completed: true },
          { id: 'material-list', title: '材料清单', completed: true },
          { id: 'workflow', title: '可参考可执行的工作流', completed: true },
          { id: 'purchase-list', title: '可复制的采购清单', completed: true },
          { id: 'cost-analysis', title: '成本成分比例分析', completed: true },
          { id: 'salary-calc', title: '合作工业的薪水计算', completed: true },
          { id: 'logistics', title: '可参考的物流计划', completed: true },
          { id: 'data-report', title: '化矿购买推荐', completed: false },
        ]
      },
      {
        id: 'market-analysis',
        title: '市场分析',
        completed: false,
        children: [
          { id: 'market-price', title: '市场价格查看', completed: false },
          { id: 'price-monitor', title: '自选清单的价格监控', completed: false },
          { id: 'profit-calc', title: '自选产品清单的利润计算', completed: false },
          { id: 'product-detail', title: '市场单品的详细数据计算【成本、利润等】', completed: false },
          { id: 'region-profit', title: '特定星域的市场利润计算', completed: false }
        ]
      }
    ]
  },
  {
    id: 'others',
    title: '其他',
    completed: false,
    children: [
      { id: 'permission', title: '服务权限分级', completed: true },
      { id: 'invite-code', title: '邀请码生成', completed: true },
      { id: 'help-doc', title: '内建使用说明', completed: true },
      { id: 'performance', title: '性能优化', completed: false },
      { id: 'ux-improve', title: '用户体验改进', completed: false,
        children: [
          { id: 'ux-improve-1', title: '带管理员账号的初始化', completed: false },
          { id: 'ux-improve-2', title: '可直接部署的docker镜像', completed: false },
        ]
      },
      { id: 'docs', title: '文档完善', completed: false,
        children: [
          { id: 'getting-start', title: '如何开始', completed: true },
          { id: 'industry-plan', title: '工业计划', completed: true },
          { id: 'storage', title: '库存管理', completed: true },
          { id: 'setting', title: '设置', completed: true },
        ]
      }
    ]
  }
])

// 计算总体进度
const progress = computed(() => {
  const calculateProgress = (items: TodoItem[]): { total: number; completed: number } => {
    let total = 0
    let completed = 0
    
    items.forEach(item => {
      total++
      if (item.completed) {
        completed++
      }
      
      if (item.children) {
        const childProgress = calculateProgress(item.children)
        total += childProgress.total
        completed += childProgress.completed
      }
    })
    
    return { total, completed }
  }
  
  const stats = calculateProgress(todoItems.value)
  return {
    percentage: stats.total > 0 ? Math.round((stats.completed / stats.total) * 100) : 0,
    completed: stats.completed,
    total: stats.total
  }
})

// 展开/折叠状态
const expandedItems = ref<Set<string>>(new Set(['web-platform', 'core-features', 'others']))
const toggleExpand = (id: string) => {
  if (expandedItems.value.has(id)) {
    expandedItems.value.delete(id)
  } else {
    expandedItems.value.add(id)
  }
}
</script>

<template>
  <div class="home-view">
    <div class="header-section">
      <h1 class="page-title">
        <el-icon><List /></el-icon>
        当前TODO LIST
      </h1>
      <div class="progress-card">
        <el-card shadow="hover" class="progress-stat-card">
          <div class="progress-content">
            <div class="progress-info">
              <div class="progress-label">
                <el-icon><List /></el-icon>
                <span>总体进度</span>
              </div>
              <div class="progress-text">
                {{ progress.completed }} / {{ progress.total }} 已完成
              </div>
            </div>
            <el-progress
              :percentage="progress.percentage"
              :stroke-width="12"
              :show-text="false"
              color="#409eff"
            />
            <div class="progress-percentage">{{ progress.percentage }}%</div>
          </div>
        </el-card>
      </div>
    </div>

    <div class="todo-list">
      <el-card
        v-for="item in todoItems"
        :key="item.id"
        shadow="hover"
        class="todo-card"
        :class="{ 'completed-card': item.completed }"
      >
        <template #header>
          <div class="card-header" @click="toggleExpand(item.id)">
            <div class="header-left">
              <el-icon class="expand-icon" :class="{ expanded: expandedItems.has(item.id) }">
                <ArrowRight />
              </el-icon>
              <el-tag
                :type="item.completed ? 'success' : 'warning'"
                :effect="item.completed ? 'dark' : 'plain'"
                class="status-tag"
              >
                <el-icon v-if="item.completed"><CircleCheckFilled /></el-icon>
                <el-icon v-else><CircleCloseFilled /></el-icon>
                <span>{{ item.completed ? '已完成' : '进行中' }}</span>
              </el-tag>
              <span class="item-title">{{ item.title }}</span>
            </div>
          </div>
        </template>

        <div v-show="expandedItems.has(item.id)" class="card-content">
          <div v-if="item.children" class="children-list">
            <div
              v-for="child in item.children"
              :key="child.id"
              class="child-item"
              :class="{ 'child-completed': child.completed }"
            >
              <div class="child-header">
                <el-tag
                  :type="child.completed ? 'success' : 'info'"
                  :effect="child.completed ? 'light' : 'plain'"
                  size="small"
                  class="child-status-tag"
                >
                  <el-icon v-if="child.completed"><CircleCheckFilled /></el-icon>
                  <el-icon v-else><CircleCloseFilled /></el-icon>
                </el-tag>
                <span class="child-title">{{ child.title }}</span>
              </div>

              <!-- 三级子项 -->
              <div v-if="child.children" class="grandchildren-list">
                <div
                  v-for="grandchild in child.children"
                  :key="grandchild.id"
                  class="grandchild-item"
                  :class="{ 'grandchild-completed': grandchild.completed }"
                >
                  <el-tag
                    :type="grandchild.completed ? 'success' : 'info'"
                    :effect="grandchild.completed ? 'light' : 'plain'"
                    size="small"
                    class="grandchild-status-tag"
                  >
                    <el-icon v-if="grandchild.completed"><CircleCheckFilled /></el-icon>
                    <el-icon v-else><CircleCloseFilled /></el-icon>
                  </el-tag>
                  <span class="grandchild-title">{{ grandchild.title }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.home-view {
  padding: 24px;
  max-width: 1200px;
  margin: 0 auto;
  background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
  min-height: calc(100vh - 60px);
}

.header-section {
  margin-bottom: 24px;
}

.page-title {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 28px;
  font-weight: 600;
  color: #2c3e50;
  margin: 0 0 20px 0;
}

.page-title .el-icon {
  font-size: 32px;
  color: #409eff;
}

.progress-card {
  margin-bottom: 24px;
}

.progress-stat-card {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
  color: white;
}

.progress-stat-card :deep(.el-card__body) {
  padding: 20px;
}

.progress-content {
  display: flex;
  align-items: center;
  gap: 20px;
}

.progress-info {
  flex: 1;
}

.progress-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 500;
  margin-bottom: 8px;
  color: rgba(255, 255, 255, 0.9);
}

.progress-text {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.8);
  margin-bottom: 12px;
}

.progress-percentage {
  font-size: 24px;
  font-weight: 600;
  color: white;
  min-width: 60px;
  text-align: right;
}

.progress-stat-card :deep(.el-progress-bar__outer) {
  background-color: rgba(255, 255, 255, 0.3);
}

.progress-stat-card :deep(.el-progress-bar__inner) {
  background-color: white;
}

.todo-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.todo-card {
  transition: all 0.3s ease;
  border-radius: 8px;
  overflow: hidden;
}

.todo-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.completed-card {
  opacity: 0.85;
}

.completed-card :deep(.el-card__header) {
  background-color: #f0f9ff;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  user-select: none;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
}

.expand-icon {
  transition: transform 0.3s ease;
  color: #909399;
  font-size: 16px;
}

.expand-icon.expanded {
  transform: rotate(90deg);
}

.status-tag {
  font-weight: 500;
  padding: 4px 12px;
}

.status-tag .el-icon {
  margin-right: 4px;
}

.item-title {
  font-size: 18px;
  font-weight: 600;
  color: #2c3e50;
}

.card-content {
  padding-top: 16px;
  animation: slideDown 0.3s ease;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.children-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-left: 8px;
  border-left: 2px solid #e4e7ed;
  margin-left: 20px;
}

.child-item {
  padding: 12px;
  background-color: #fafafa;
  border-radius: 6px;
  transition: all 0.2s ease;
}

.child-item:hover {
  background-color: #f5f7fa;
}

.child-completed {
  opacity: 0.7;
}

.child-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.child-status-tag {
  flex-shrink: 0;
}

.child-title {
  font-size: 15px;
  color: #606266;
  font-weight: 500;
}

.grandchildren-list {
  margin-top: 12px;
  margin-left: 32px;
  padding-left: 16px;
  border-left: 2px dashed #dcdfe6;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.grandchild-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  background-color: white;
  border-radius: 4px;
  transition: all 0.2s ease;
}

.grandchild-item:hover {
  background-color: #f5f7fa;
}

.grandchild-completed {
  opacity: 0.7;
}

.grandchild-status-tag {
  flex-shrink: 0;
}

.grandchild-title {
  font-size: 14px;
  color: #909399;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .home-view {
    padding: 16px;
  }

  .page-title {
    font-size: 24px;
  }

  .progress-content {
    flex-direction: column;
    align-items: flex-start;
  }

  .progress-percentage {
    text-align: left;
  }

  .children-list {
    margin-left: 10px;
  }

  .grandchildren-list {
    margin-left: 20px;
  }
}
</style>
