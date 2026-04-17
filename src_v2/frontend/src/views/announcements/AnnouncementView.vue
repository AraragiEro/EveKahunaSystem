<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { marked } from 'marked'
import dayjs from 'dayjs'
import mermaid from 'mermaid'

type RawMeta = Record<string, string>

interface AnnouncementItem {
  slug: string
  title: string
  publishedAt: string
  updatedAt?: string
  author?: string
  summary?: string
  tags: string[]
  meta: RawMeta
  content: string
  html: string
}

const route = useRoute()
const router = useRouter()
const announcementBodyRef = ref<HTMLElement | null>(null)
let mermaidInitialized = false

const markdownModules = import.meta.glob('/src/announcements/**/*.md', {
  eager: true,
  query: '?raw',
  import: 'default',
}) as Record<string, string>

const removeQuotes = (value: string): string => value.replace(/^["']|["']$/g, '').trim()

const parseFrontMatter = (rawText: string): { meta: RawMeta; content: string } => {
  const matched = rawText.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/)
  if (!matched) {
    return { meta: {}, content: rawText.trim() }
  }

  const [, metaBlock, content] = matched
  const meta: RawMeta = {}

  for (const line of metaBlock.split(/\r?\n/)) {
    const rawLine = line.trim()
    if (!rawLine || rawLine.startsWith('#')) {
      continue
    }

    const separatorIndex = rawLine.indexOf(':')
    if (separatorIndex === -1) {
      continue
    }

    const key = rawLine.slice(0, separatorIndex).trim()
    const value = rawLine.slice(separatorIndex + 1).trim()
    meta[key] = removeQuotes(value)
  }

  return { meta, content: content.trim() }
}

const parseTags = (value?: string): string[] => {
  if (!value) {
    return []
  }
  return value
    .split(',')
    .map((item) => removeQuotes(item))
    .filter(Boolean)
}

const formatDate = (value?: string): string => {
  if (!value) {
    return ''
  }
  const date = dayjs(value)
  return date.isValid() ? date.format('YYYY-MM-DD HH:mm') : value
}

const announcements = computed<AnnouncementItem[]>(() => {
  const entries: AnnouncementItem[] = []

  for (const [filePath, rawText] of Object.entries(markdownModules)) {
    const { meta, content } = parseFrontMatter(rawText)
    const normalizedPath = filePath.replace(/\\/g, '/')
    const slug = normalizedPath
      .replace(/^.*\/announcements\//, '')
      .replace(/\.md$/, '')
      .replace(/\//g, '-')

    const title = meta.title || slug
    const publishedAt = meta.published_at || meta.publishedAt || ''
    const updatedAt = meta.updated_at || meta.updatedAt || ''
    const author = meta.author || ''
    const summary = meta.summary || ''
    const tags = parseTags(meta.tags)

    entries.push({
      slug,
      title,
      publishedAt,
      updatedAt,
      author,
      summary,
      tags,
      meta,
      content,
      html: marked(content, { breaks: true }) as string,
    })
  }

  return entries.sort((a, b) => {
    const aTime = dayjs(a.publishedAt).valueOf()
    const bTime = dayjs(b.publishedAt).valueOf()
    return (Number.isNaN(bTime) ? 0 : bTime) - (Number.isNaN(aTime) ? 0 : aTime)
  })
})

const selectedSlug = computed<string>(() => {
  const querySlug = route.query.slug
  if (typeof querySlug === 'string' && querySlug.trim()) {
    return querySlug
  }
  return announcements.value[0]?.slug || ''
})

const selectedAnnouncement = computed<AnnouncementItem | undefined>(() => {
  return (
    announcements.value.find((item) => item.slug === selectedSlug.value) || announcements.value[0]
  )
})
const activeSlug = computed<string>(() => selectedAnnouncement.value?.slug || '')

const openAnnouncement = (slug: string) => {
  router.replace({
    path: '/announcements',
    query: { slug },
  })
}

const ensureMermaidInitialized = () => {
  if (mermaidInitialized) {
    return
  }
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: 'loose',
  })
  mermaidInitialized = true
}

const renderMermaidDiagrams = async () => {
  await nextTick()

  const body = announcementBodyRef.value
  if (!body) {
    return
  }

  const codeBlocks = body.querySelectorAll('pre code.language-mermaid, pre code.lang-mermaid')
  for (const codeBlock of codeBlocks) {
    const source = codeBlock.textContent?.trim()
    const preElement = codeBlock.closest('pre')
    if (!source || !preElement) {
      continue
    }
    const mermaidElement = document.createElement('div')
    mermaidElement.className = 'mermaid'
    mermaidElement.textContent = source
    preElement.replaceWith(mermaidElement)
  }

  const mermaidBlocks = body.querySelectorAll('.mermaid')
  if (!mermaidBlocks.length) {
    return
  }

  ensureMermaidInitialized()
  try {
    await mermaid.run({ nodes: Array.from(mermaidBlocks) as HTMLElement[] })
  } catch (error) {
    console.error('Mermaid 渲染失败:', error)
  }
}

watch(
  () => selectedAnnouncement.value?.slug,
  () => {
    void renderMermaidDiagrams()
  },
  { immediate: true },
)
</script>

<template>
  <div class="announcement-page">
    <header class="announcement-header">
      <h1>公告中心</h1>
      <el-button text @click="router.push('/landing')">返回 Landing</el-button>
    </header>

    <div class="announcement-layout">
      <aside class="announcement-list">
        <h2>公告列表</h2>
        <el-empty v-if="!announcements.length" description="暂无公告" />
        <button
          v-for="item in announcements"
          :key="item.slug"
          type="button"
          class="announcement-item"
          :class="{ active: item.slug === activeSlug }"
          @click="openAnnouncement(item.slug)"
        >
          <p class="item-title">{{ item.title }}</p>
          <p class="item-date">{{ formatDate(item.publishedAt) || '未设置发布时间' }}</p>
          <p v-if="item.summary" class="item-summary">{{ item.summary }}</p>
        </button>
      </aside>

      <main class="announcement-detail">
        <el-empty v-if="!selectedAnnouncement" description="请选择公告" />
        <template v-else>
          <section class="meta-panel">
            <h2>{{ selectedAnnouncement.title }}</h2>
            <p>发布时间：{{ formatDate(selectedAnnouncement.publishedAt) || '未设置' }}</p>
            <p v-if="selectedAnnouncement.updatedAt">
              更新时间：{{ formatDate(selectedAnnouncement.updatedAt) }}
            </p>
            <p v-if="selectedAnnouncement.author">作者：{{ selectedAnnouncement.author }}</p>
            <p v-if="selectedAnnouncement.summary">摘要：{{ selectedAnnouncement.summary }}</p>
            <div v-if="selectedAnnouncement.tags.length" class="tag-list">
              <el-tag v-for="tag in selectedAnnouncement.tags" :key="tag" size="small">{{ tag }}</el-tag>
            </div>
          </section>

          <el-divider />

          <article ref="announcementBodyRef" class="markdown-body" v-html="selectedAnnouncement.html" />
        </template>
      </main>
    </div>
  </div>
</template>

<style scoped>
.announcement-page {
  max-width: 1240px;
  margin: 0 auto;
  padding: 24px 20px 36px;
}

.announcement-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.announcement-header h1 {
  margin: 0;
  font-size: 30px;
}

.announcement-layout {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 16px;
}

.announcement-list,
.announcement-detail {
  border: 1px solid var(--k-color-border);
  border-radius: 12px;
  background: var(--k-color-surface);
}

.announcement-list {
  padding: 16px;
  max-height: calc(100dvh - 120px);
  overflow: auto;
}

.announcement-list h2 {
  margin: 0 0 12px;
  font-size: 18px;
}

.announcement-item {
  width: 100%;
  text-align: left;
  border: 1px solid var(--k-color-border);
  border-radius: 10px;
  padding: 10px 12px;
  background: var(--k-color-surface-soft);
  cursor: pointer;
  margin-bottom: 10px;
}

.announcement-item.active {
  border-color: var(--k-color-primary);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--k-color-primary) 30%, transparent);
}

.item-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.item-date {
  margin: 6px 0 0;
  color: var(--k-color-text-secondary);
  font-size: 12px;
}

.item-summary {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--k-color-text-secondary);
}

.announcement-detail {
  padding: 18px 22px;
  overflow: auto;
}

.meta-panel h2 {
  margin: 0 0 10px;
}

.meta-panel p {
  margin: 6px 0;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  margin-top: 1.2em;
}

.markdown-body :deep(p) {
  line-height: 1.8;
}

@media (max-width: 960px) {
  .announcement-layout {
    grid-template-columns: 1fr;
  }

  .announcement-list {
    max-height: none;
  }
}
</style>
