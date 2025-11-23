<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { useHelpStore } from '@/stores/help'
import { marked } from 'marked'

// 导入图片资源
import docIndustry1 from '@/assets/doc-industry-1.png'
import docIndustry2 from '@/assets/doc-industry-2.png'
import docIndustry3 from '@/assets/doc-industry-3.png'
import docStorage1 from '@/assets/doc-storage-1.png'
import docStorage2 from '@/assets/doc-storage-2.png'
import docStorage3 from '@/assets/doc-storage-3.png'
import docSetting1 from '@/assets/doc-setting-1.png'

// 创建图片路径映射
const imageMap: Record<string, string> = {
  '/assets/doc-industry-1.png': docIndustry1,
  '/assets/doc-industry-2.png': docIndustry2,
  '/assets/doc-industry-3.png': docIndustry3,
  '/assets/doc-storage-1.png': docStorage1,
  '/assets/doc-storage-2.png': docStorage2,
  '/assets/doc-storage-3.png': docStorage3,
  '/assets/doc-setting-1.png': docSetting1
}

// 配置 marked
marked.setOptions({
  breaks: true, // 支持换行
  gfm: true,    // GitHub Flavored Markdown
})

// 全屏图片查看状态
const imageViewerVisible = ref(false)
const imageViewerSrc = ref('')

// 打开图片查看器
const openImageViewer = (src: string) => {
  imageViewerSrc.value = src
  imageViewerVisible.value = true
}

// 关闭图片查看器
const closeImageViewer = () => {
  imageViewerVisible.value = false
  imageViewerSrc.value = ''
}

// 转义 HTML 属性值
const escapeHtml = (str: string): string => {
  const div = document.createElement('div')
  div.textContent = str
  return div.innerHTML
}

// 自定义图片渲染器
const renderer = new marked.Renderer()
const originalImage = renderer.image.bind(renderer)
renderer.image = (href: string, title: string | null, text: string) => {
  // 如果图片路径在映射中，使用映射的路径
  const imageSrc = imageMap[href] || href
  // 转义属性值
  const altText = escapeHtml(text || '')
  const titleText = escapeHtml(title || text || '')
  // 添加可点击的样式类和 data 属性
  return `<img src="${imageSrc}" alt="${altText}" title="${titleText}" class="clickable-image" data-image-src="${imageSrc}" style="cursor: pointer;" />`
}

// 导入 markdown 文件（使用 ?raw 后缀）
import summaryWhatIsKahunaSystem from '@/docs/summary-what-is-kahuna-system.md?raw'
const summaryWhatIsKahunaSystemHtml = marked(summaryWhatIsKahunaSystem, { renderer }) as string
import summaryPrice from '@/docs/summary-price.md?raw'
const summaryPriceHtml = marked(summaryPrice, { renderer }) as string
import summaryQA from '@/docs/summary-QA.md?raw'
const summaryQAHtml = marked(summaryQA, { renderer }) as string

import gettingStartIndustry from '@/docs/getting-start-industry.md?raw'
const gettingStartIndustryHtml = marked(gettingStartIndustry, { renderer }) as string
import gettingStartStorage from '@/docs/getting-start-storage.md?raw'
const gettingStartStorageHtml = marked(gettingStartStorage, { renderer }) as string
import gettingStartSetting from '@/docs/getting-start-setting.md?raw'
const gettingStartSettingHtml = marked(gettingStartSetting, { renderer }) as string

const helpStore = useHelpStore()

// 目录数据结构
interface HelpSection {
  id: string
  title: string
  children?: HelpSection[]
  content?: string
}

// 目录结构（从 markdown 文件加载内容）
const helpSections = ref<HelpSection[]>([
  {
    id: 'intro',
    title: '简介',
    children: [
      { id: 'intro-overview', title: '什么是 Kahuna System？', content: summaryWhatIsKahunaSystemHtml },
      { id: 'intro-price', title: '关于收费', content: summaryPriceHtml },
      { id: 'intro-QA', title: '常见问题', content: summaryQAHtml }
    ]
  },
  {
    id: 'getting-started',
    title: '快速开始',
    children: [
      { id: 'getting-started-industry', title: '工业', content: gettingStartIndustryHtml },
      { id: 'getting-started-storage', title: '库存管理【Alpha订阅】', content: gettingStartStorageHtml },
      { id: 'getting-started-setting', title: '设置', content: gettingStartSettingHtml }
    ]
  }
])

// localStorage 键名
const STORAGE_KEY_ACTIVE_SECTION = 'help-drawer-active-section'
const STORAGE_KEY_ACTIVE_SUB_SECTION = 'help-drawer-active-sub-section'
const STORAGE_KEY_OPENED_SECTIONS = 'help-drawer-opened-sections'

// 验证 section ID 是否有效
const isValidSectionId = (sectionId: string): boolean => {
  return helpSections.value.some(s => s.id === sectionId)
}

// 验证 subSection ID 是否有效
const isValidSubSectionId = (subSectionId: string): boolean => {
  for (const section of helpSections.value) {
    if (section.children?.some(child => child.id === subSectionId)) {
      return true
    }
  }
  return false
}

// 从 localStorage 加载保存的状态
const loadSavedState = () => {
  try {
    const savedSectionId = localStorage.getItem(STORAGE_KEY_ACTIVE_SECTION)
    const savedSubSectionId = localStorage.getItem(STORAGE_KEY_ACTIVE_SUB_SECTION)
    const savedOpenedSections = localStorage.getItem(STORAGE_KEY_OPENED_SECTIONS)

    // 验证并恢复一级目录
    if (savedSectionId && isValidSectionId(savedSectionId)) {
      let sectionId = savedSectionId
      let subSectionId = ''
      let openedSectionsList: string[] = []

      // 如果保存了 subSectionId，验证其有效性并找到对应的 sectionId
      if (savedSubSectionId && isValidSubSectionId(savedSubSectionId)) {
        subSectionId = savedSubSectionId
        // 找到 subSection 对应的 section
        for (const section of helpSections.value) {
          if (section.children?.some(child => child.id === savedSubSectionId)) {
            sectionId = section.id
            break
          }
        }
      }

      // 恢复展开的目录列表
      if (savedOpenedSections) {
        try {
          openedSectionsList = JSON.parse(savedOpenedSections).filter((id: string) => isValidSectionId(id))
        } catch {
          openedSectionsList = []
        }
      }

      // 确保当前激活的 section 在展开列表中
      if (sectionId && !openedSectionsList.includes(sectionId)) {
        openedSectionsList.push(sectionId)
      }

      return {
        sectionId,
        subSectionId,
        openedSections: openedSectionsList.length > 0 ? openedSectionsList : [sectionId]
      }
    }
  } catch (error) {
    console.warn('加载保存的状态失败:', error)
  }
  return null
}

// 保存状态到 localStorage
const saveState = () => {
  try {
    localStorage.setItem(STORAGE_KEY_ACTIVE_SECTION, activeSectionId.value)
    localStorage.setItem(STORAGE_KEY_ACTIVE_SUB_SECTION, activeSubSectionId.value)
    localStorage.setItem(STORAGE_KEY_OPENED_SECTIONS, JSON.stringify(openedSections.value))
  } catch (error) {
    console.warn('保存状态失败:', error)
  }
}

// 初始化状态（从 localStorage 或使用默认值）
const savedState = loadSavedState()
const defaultSectionId = helpSections.value[0]?.id || ''
const defaultSubSectionId = helpSections.value[0]?.children?.[0]?.id || ''

// 当前选中的目录项
const activeSectionId = ref<string>(savedState?.sectionId || defaultSectionId)
const activeSubSectionId = ref<string>(savedState?.subSectionId || defaultSubSectionId)

// 已展开的一级目录列表
const openedSections = ref<string[]>(savedState?.openedSections || [defaultSectionId])

// 监听状态变化并保存
watch([activeSectionId, activeSubSectionId, openedSections], () => {
  saveState()
}, { deep: true })

// 当前显示的内容
const currentContent = computed(() => {
  if (activeSubSectionId.value) {
    // 查找二级目录的内容
    for (const section of helpSections.value) {
      if (section.children) {
        const subSection = section.children.find(child => child.id === activeSubSectionId.value)
        if (subSection) {
          return subSection.content || '内容待填充...'
        }
      }
    }
  }
  // 如果没有二级目录，查找一级目录的内容
  const section = helpSections.value.find(s => s.id === activeSectionId.value)
  return section?.content || '内容待填充...'
})

// 处理一级目录点击
const handleSectionClick = (sectionId: string) => {
  activeSectionId.value = sectionId
  const section = helpSections.value.find(s => s.id === sectionId)
  if (section?.children && section.children.length > 0) {
    activeSubSectionId.value = section.children[0].id
    // 确保该一级目录在展开列表中
    if (!openedSections.value.includes(sectionId)) {
      openedSections.value.push(sectionId)
    }
  } else {
    activeSubSectionId.value = ''
  }
}

// 处理菜单选择事件（包括一级和二级目录）
const handleMenuSelect = (index: string) => {
  // 检查是否是一级目录
  const section = helpSections.value.find(s => s.id === index)
  if (section) {
    // 如果是一级目录，切换到第一个子项
    handleSectionClick(index)
  } else {
    // 如果是二级目录，直接切换
    activeSubSectionId.value = index
    // 同时更新对应的一级目录，并确保该一级目录保持展开
    for (const sec of helpSections.value) {
      if (sec.children?.some(child => child.id === index)) {
        activeSectionId.value = sec.id
        // 确保该一级目录在展开列表中
        if (!openedSections.value.includes(sec.id)) {
          openedSections.value.push(sec.id)
        }
        break
      }
    }
  }
}

// 处理子菜单展开/收起事件
const handleSubMenuOpen = (index: string) => {
  if (!openedSections.value.includes(index)) {
    openedSections.value.push(index)
  }
}

const handleSubMenuClose = (index: string) => {
  const idx = openedSections.value.indexOf(index)
  if (idx > -1) {
    openedSections.value.splice(idx, 1)
  }
}

// 为图片添加点击事件
const setupImageClickHandlers = () => {
  nextTick(() => {
    const contentElement = document.querySelector('.help-content-text')
    if (contentElement) {
      const images = contentElement.querySelectorAll('img.clickable-image')
      images.forEach((img) => {
        // 移除旧的事件监听器（如果存在）
        const newImg = img.cloneNode(true) as HTMLElement
        img.parentNode?.replaceChild(newImg, img)
        
        // 添加点击事件
        newImg.addEventListener('click', () => {
          const src = newImg.getAttribute('data-image-src') || newImg.getAttribute('src') || ''
          if (src) {
            openImageViewer(src)
          }
        })
      })
    }
  })
}

// 监听内容变化，重新设置图片点击事件
watch(currentContent, () => {
  setupImageClickHandlers()
})

// 组件挂载时设置图片点击事件
onMounted(() => {
  setupImageClickHandlers()
})
</script>

<template>
  <el-drawer
    v-model="helpStore.isOpen"
    title="指南"
    :size="800"
    direction="rtl"
    :before-close="helpStore.closeHelp"
  >
    <div class="help-drawer-container">
      <!-- 左侧目录导航 -->
      <div class="help-sidebar">
        <el-scrollbar>
          <el-menu
            :key="`menu-${activeSubSectionId || activeSectionId}-${openedSections.join(',')}`"
            :default-active="activeSubSectionId || activeSectionId"
            class="help-menu"
            @select="handleMenuSelect"
            :default-openeds="openedSections"
            @open="handleSubMenuOpen"
            @close="handleSubMenuClose"
          >
            <template v-for="section in helpSections" :key="section.id">
              <!-- 一级目录 -->
              <el-sub-menu :index="section.id">
                <template #title>
                  <span @click.stop="handleSectionClick(section.id)">{{ section.title }}</span>
                </template>
                <!-- 二级目录 -->
                <el-menu-item
                  v-for="child in section.children"
                  :key="child.id"
                  :index="child.id"
                >
                  <span>{{ child.title }}</span>
                </el-menu-item>
              </el-sub-menu>
            </template>
          </el-menu>
        </el-scrollbar>
      </div>

      <!-- 右侧内容区域 -->
      <div class="help-content">
        <el-scrollbar>
          <div class="help-content-inner">
            <div class="help-content-text" v-html="currentContent"></div>
          </div>
        </el-scrollbar>
      </div>
    </div>

    <!-- 全屏图片查看器 -->
    <el-dialog
      v-model="imageViewerVisible"
      :width="'90%'"
      :show-close="true"
      :close-on-click-modal="true"
      :close-on-press-escape="true"
      align-center
      class="image-viewer-dialog"
      @close="closeImageViewer"
    >
      <div class="image-viewer-container">
        <img :src="imageViewerSrc" alt="预览图片" class="image-viewer-img" />
      </div>
    </el-dialog>
  </el-drawer>
</template>

<style scoped>
.help-drawer-container {
  display: flex;
  height: calc(100vh - 60px);
  overflow: hidden;
  background-color: #f5f7fa;
}

.help-sidebar {
  width: 240px;
  border-right: 1px solid #e1e8ed;
  flex-shrink: 0;
  height: 100%;
  background-color: white;
}

.help-menu {
  border-right: none;
  height: 100%;
  background-color: white;
}

.help-content {
  flex: 1;
  height: 100%;
  overflow: hidden;
  background-color: white;
}

.help-content-inner {
  padding: 24px;
  min-height: 100%;
  background-color: white;
}

.help-content-text {
  line-height: 1.8;
  color: #2c3e50;
  font-size: 14px;
  background-color: white;
}

.help-content-text :deep(h1) {
  font-size: 24px;
  font-weight: 600;
  margin: 0 0 16px 0;
  color: #2c3e50;
  border-bottom: 2px solid #e1e8ed;
  padding-bottom: 8px;
}

.help-content-text :deep(h2) {
  font-size: 20px;
  font-weight: 600;
  margin: 24px 0 12px 0;
  color: #2c3e50;
}

.help-content-text :deep(h3) {
  font-size: 16px;
  font-weight: 600;
  margin: 16px 0 8px 0;
  color: #2c3e50;
}

.help-content-text :deep(p) {
  margin: 0 0 12px 0;
  color: #64748b;
}

.help-content-text :deep(ul),
.help-content-text :deep(ol) {
  margin: 0 0 12px 0;
  padding-left: 24px;
  color: #64748b;
}

.help-content-text :deep(li) {
  margin: 4px 0;
}

.help-content-text :deep(code) {
  background-color: #f1f5f9;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  color: #e11d48;
}

.help-content-text :deep(pre) {
  background-color: #f8fafc;
  border: 1px solid #e1e8ed;
  border-radius: 6px;
  padding: 16px;
  overflow-x: auto;
  margin: 12px 0;
}

.help-content-text :deep(pre code) {
  background-color: transparent;
  padding: 0;
  color: #2c3e50;
}

.help-content-text :deep(img) {
  max-width: 100%;
  height: auto;
  border-radius: 4px;
  margin: 12px 0;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  transition: all 0.3s ease;
}

.help-content-text :deep(img.clickable-image) {
  cursor: pointer;
  transition: all 0.3s ease;
}

.help-content-text :deep(img.clickable-image:hover) {
  transform: scale(1.02);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  opacity: 0.9;
}

/* 菜单项样式优化 */
:deep(.el-menu-item) {
  color: #64748b;
  transition: all 0.2s;
}

:deep(.el-menu-item:hover) {
  background-color: #f1f5f9;
  color: #2c3e50;
}

:deep(.el-menu-item.is-active) {
  background-color: #e0f2fe;
  color: #0284c7;
  font-weight: 500;
}

:deep(.el-sub-menu__title) {
  color: #2c3e50;
  font-weight: 500;
  transition: all 0.2s;
}

:deep(.el-sub-menu__title:hover) {
  background-color: #f1f5f9;
  color: #2c3e50;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .help-drawer-container {
    flex-direction: column;
  }

  .help-sidebar {
    width: 100%;
    height: 200px;
    border-right: none;
    border-bottom: 1px solid #e1e8ed;
  }

  .help-content {
    height: calc(100% - 200px);
  }
}

/* 全屏图片查看器样式 */
:deep(.image-viewer-dialog) {
  .el-dialog__body {
    padding: 0;
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 60vh;
    background-color: rgba(0, 0, 0, 0.9);
  }
}

.image-viewer-container {
  width: 100%;
  height: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 20px;
}

.image-viewer-img {
  max-width: 100%;
  max-height: 90vh;
  width: auto;
  height: auto;
  object-fit: contain;
  border-radius: 4px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}
</style>

