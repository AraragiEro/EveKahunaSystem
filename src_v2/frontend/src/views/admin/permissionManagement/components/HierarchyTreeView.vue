<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { http } from '@/http'
import type { Role } from '../types'

const hierarchyTreeData = ref<any[]>([])
const hierarchyTreeLoading = ref(false)

// 构建角色层级关系树
const buildHierarchyTree = async () => {
  hierarchyTreeLoading.value = true
  try {
    // 获取所有角色
    const rolesResponse = await http.get('/permission/roles')
    if (!rolesResponse.ok) {
      throw new Error('获取角色列表失败')
    }
    const rolesData = await rolesResponse.json()
    const allRoles = rolesData.data || []
    
    // 获取所有角色的层级关系
    const hierarchyMap = new Map<string, { parents: string[], children: string[] }>()
    
    for (const role of allRoles) {
      try {
        const hierarchyResponse = await http.get(`/permission/roles/${role.roleName}/hierarchy`)
        if (hierarchyResponse.ok) {
          const hierarchyData = await hierarchyResponse.json()
          hierarchyMap.set(role.roleName, {
            parents: hierarchyData.data.parentRoles || [],
            children: hierarchyData.data.childRoles || []
          })
        }
      } catch (error) {
        hierarchyMap.set(role.roleName, { parents: [], children: [] })
      }
    }
    
    // 找到所有根节点（没有父角色的节点）
    const rootRoles = allRoles.filter((role: Role) => {
      const hierarchy = hierarchyMap.get(role.roleName)
      return !hierarchy || hierarchy.parents.length === 0
    })
    
    // 递归构建树节点
    const buildTreeNode = (roleName: string, visited: Set<string>): any => {
      if (visited.has(roleName)) {
        // 检测到循环引用，返回空节点
        return null
      }
      visited.add(roleName)
      
      const hierarchy = hierarchyMap.get(roleName)
      const children = hierarchy?.children || []
      
      const node: any = {
        label: roleName,
        id: roleName,
        children: []
      }
      
      const childNodes: any[] = []
      for (const childName of children) {
        const childNode = buildTreeNode(childName, new Set(visited))
        if (childNode) {
          childNodes.push(childNode)
        }
      }
      
      if (childNodes.length > 0) {
        node.children = childNodes
      }
      
      return node
    }
    
    // 构建树
    const treeData: any[] = []
    for (const role of rootRoles) {
      const node = buildTreeNode(role.roleName, new Set())
      if (node) {
        treeData.push(node)
      }
    }
    
    // 处理没有父节点的孤立节点
    const processedRoles = new Set<string>()
    const traverseTree = (nodes: any[]) => {
      for (const node of nodes) {
        processedRoles.add(node.id)
        if (node.children && node.children.length > 0) {
          traverseTree(node.children)
        }
      }
    }
    traverseTree(treeData)
    
    // 添加孤立节点
    for (const role of allRoles) {
      if (!processedRoles.has(role.roleName)) {
        treeData.push({
          label: role.roleName,
          id: role.roleName,
          children: []
        })
      }
    }
    
    hierarchyTreeData.value = treeData
  } catch (error: any) {
    ElMessage.error(error?.message || '构建角色层级关系树失败')
  } finally {
    hierarchyTreeLoading.value = false
  }
}

// 加载角色层级关系树
const loadHierarchyTree = () => {
  buildHierarchyTree()
}

onMounted(() => {
  loadHierarchyTree()
})

defineExpose({
  loadHierarchyTree
})
</script>

<template>
  <div class="hierarchy-tree-view">
    <div class="toolbar">
      <el-button type="primary" @click="loadHierarchyTree">刷新</el-button>
    </div>
    <div class="hierarchy-tree-container">
      <el-tree
        v-loading="hierarchyTreeLoading"
        :data="hierarchyTreeData"
        :props="{ children: 'children', label: 'label' }"
        default-expand-all
        node-key="id"
        class="hierarchy-tree"
      >
        <template #default="{ node, data }">
          <span class="tree-node">
            <el-tag size="small" type="info">{{ data.label }}</el-tag>
          </span>
        </template>
      </el-tree>
      <div v-if="!hierarchyTreeLoading && hierarchyTreeData.length === 0" class="empty-tree">
        暂无角色层级关系，请先在角色管理中设置层级关系
      </div>
    </div>
  </div>
</template>

<style scoped>
.hierarchy-tree-view {
  padding: 20px;
}

.toolbar {
  margin-bottom: 20px;
}

.hierarchy-tree-container {
  min-height: 400px;
  padding: 20px;
  background: #fafafa;
  border-radius: 8px;
}

.hierarchy-tree {
  background: #fff;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.tree-node {
  flex: 1;
  display: flex;
  align-items: center;
}

.empty-tree {
  text-align: center;
  padding: 60px 20px;
  color: #999;
  font-size: 14px;
}
</style>

