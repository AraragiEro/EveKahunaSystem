<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown, ChatLineRound, Refresh, Search } from '@element-plus/icons-vue'
import { http } from '@/http'
import { useAuthStore } from '@/stores/auth'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-cn'
import { marked } from 'marked'

// 配置 dayjs
dayjs.extend(relativeTime)
dayjs.locale('zh-cn')

const authStore = useAuthStore()

interface MessageCardItem {
  id: number
  title: string
  content?: string
  content_snippet?: string
  type: 'bug' | 'feat' | 'chat'
  status: 'created' | 'in_progress' | 'closed'
  author: {
    id: string
    name: string
    avatarUrl?: string | null
  }
  created_at: string | null
  last_reply_at: string | null
  reply_count: number
  auto_closed: boolean
  is_hidden?: boolean
}

interface Pagination {
  page: number
  page_size: number
  total: number
  has_next: boolean
}

const loading = ref(false)
const loadingMore = ref(false)
const cards = ref<MessageCardItem[]>([])
const pagination = ref<Pagination>({
  page: 1,
  page_size: 20,
  total: 0,
  has_next: false
})

// 筛选条件
const statusFilter = ref<string[]>(['created', 'in_progress'])
const typeFilter = ref<string[]>([])
const mineOnly = ref(false)
const participatedOnly = ref(false)
const publisherSearch = ref('')
const createdFrom = ref<string | null>(null)
const createdTo = ref<string | null>(null)
const orderBy = ref<'created_at' | 'last_reply_at'>('last_reply_at')
const order = ref<'asc' | 'desc'>('desc')
const showHidden = ref(false) // 管理员筛选隐藏卡片

// 新建 card dialog
const createDialogVisible = ref(false)
const createForm = ref({
  type: 'chat' as 'bug' | 'feat' | 'chat',
  title: '',
  content: ''
})
const createSubmitting = ref(false)

// 详情面板 & 回复相关
const activeCard = ref<MessageCardItem | null>(null)
const detailLoading = ref(false)

interface MessageReplyItem {
  id: number
  author: {
    id: string
    name: string
    avatarUrl?: string | null
  }
  content: string
  created_at: string | null
  updated_at: string | null
  is_hidden?: boolean
}

const replies = ref<MessageReplyItem[]>([])
const replyPagination = ref<Pagination>({
  page: 1,
  page_size: 20,
  total: 0,
  has_next: false
})
const replyLoading = ref(false)
const replyLoadingMore = ref(false)
const replyContent = ref('')
const replySubmitting = ref(false)
const updatingStatus = ref(false)
const togglingHidden = ref(false)

// 卡片列表与回复列表直接透传后端结果（隐藏规则由后端控制）
const filteredCards = computed(() => cards.value)
const filteredReplies = computed(() => replies.value)

// 判断是否为管理员
const isAdmin = computed(() => {
  return authStore.user?.roles?.includes('admin') || false
})

// 时间格式化函数
const formatTime = (timeStr: string | null): string => {
  if (!timeStr) return '-'
  const time = dayjs(timeStr)
  const now = dayjs()
  const diffInHours = now.diff(time, 'hour')

  // 如果小于24小时，显示相对时间
  if (diffInHours < 24) {
    return time.fromNow()
  }
  // 如果小于7天，显示相对时间
  if (diffInHours < 168) {
    return time.fromNow()
  }
  // 否则显示格式化时间
  return time.format('YYYY-MM-DD HH:mm')
}

// 内容摘要截断函数
const getContentSnippet = (content: string | undefined, maxLength: number = 100): string => {
  if (!content) return ''
  // 移除 Markdown 语法标记（简单处理）
  const text = content.replace(/[#*_`\[\]()]/g, '').replace(/\n+/g, ' ').trim()
  if (text.length <= maxLength) return text
  return text.slice(0, maxLength) + '...'
}

// Markdown 渲染函数
const renderMarkdown = (content: string | undefined): string => {
  if (!content) return ''
  try {
    // marked 12.0.0 版本中 marked() 是同步的，返回 string
    return marked(content, { breaks: true }) as string
  } catch (err) {
    console.error('Markdown render error:', err)
    return content
  }
}

// 状态标签配置
const getStatusTagConfig = (status: 'created' | 'in_progress' | 'closed') => {
  const configs = {
    created: { type: 'warning' as const, label: '创建', class: 'status-tag-created' },
    in_progress: { type: 'success' as const, label: '进行中', class: 'status-tag-in-progress' },
    closed: { type: 'info' as const, label: '关闭', class: 'status-tag-closed' }
  }
  return configs[status]
}

// 类型标签配置
const getTypeTagConfig = (type: 'bug' | 'feat' | 'chat') => {
  const configs = {
    bug: { type: 'danger' as const, label: '漏洞提交' },
    feat: { type: 'success' as const, label: '新特性需求' },
    chat: { type: 'info' as const, label: '交流' }
  }
  return configs[type]
}

const statusOptions = [
  { value: 'created', label: '创建' },
  { value: 'in_progress', label: '进行中' },
  { value: 'closed', label: '关闭' }
]

const typeOptions = [
  { value: 'bug', label: '漏洞提交' },
  { value: 'feat', label: '新特性需求' },
  { value: 'chat', label: '交流' }
]

const orderOptions = [
  { value: 'last_reply_at', label: '按最后回复时间' },
  { value: 'created_at', label: '按创建时间' }
]

const hasFilterChanged = computed(() => {
  return true // 始终允许用户点击刷新按钮
})

const resetAndLoad = async () => {
  cards.value = []
  pagination.value.page = 1
  await loadCards()
}

const buildQueryParams = (page: number) => {
  const params: Record<string, any> = {
    page,
    page_size: pagination.value.page_size,
    order_by: orderBy.value,
    order: order.value
  }

  if (statusFilter.value.length > 0) {
    params.status = statusFilter.value
  }
  if (typeFilter.value.length > 0) {
    params.type = typeFilter.value
  }
  if (mineOnly.value) {
    params.mine = true
  }
  if (participatedOnly.value) {
    params.participated = true
  }
  if (publisherSearch.value.trim()) {
    params.publisher_search = publisherSearch.value.trim()
  }
  if (createdFrom.value) {
    params.created_from = createdFrom.value
  }
  if (createdTo.value) {
    params.created_to = createdTo.value
  }
  if (isAdmin.value && showHidden.value) {
    params.show_hidden = true
  }

  return params
}

const loadCards = async () => {
  if (loading.value || loadingMore.value) return
  const isFirstPage = pagination.value.page === 1 && cards.value.length === 0
  if (isFirstPage) {
    loading.value = true
  } else {
    loadingMore.value = true
  }
  try {
    const params = buildQueryParams(pagination.value.page)
    const res = await http.get('/message-board/cards', params)
    const data = await res.json()
    if (data.status !== 200) {
      ElMessage.error(data.message || '获取留言列表失败')
      return
    }
    const payload = data.data || {}
    const items: MessageCardItem[] = payload.items || []
    const pageInfo: Pagination = payload.pagination || pagination.value

    if (pagination.value.page === 1) {
      cards.value = items
    } else {
      cards.value = [...cards.value, ...items]
    }
    pagination.value = pageInfo
  } catch (err) {
    console.error(err)
    ElMessage.error('加载留言列表失败')
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

const loadMore = async () => {
  if (!pagination.value.has_next) return
  pagination.value.page += 1
  await loadCards()
}

const openCreateDialog = () => {
  createForm.value = {
    type: 'chat',
    title: '',
    content: ''
  }
  createDialogVisible.value = true
}

const submitCreate = async () => {
  if (createSubmitting.value) return
  if (!createForm.value.title.trim() || !createForm.value.content.trim()) {
    ElMessage.warning('请填写标题和内容')
    return
  }
  createSubmitting.value = true
  try {
    const res = await http.post('/message-board/cards', {
      type: createForm.value.type,
      title: createForm.value.title.trim(),
      content: createForm.value.content.trim()
    })
    const data = await res.json()
    if (data.status !== 200) {
      if (data.code === 'RATE_LIMIT') {
        ElMessage.error(data.message || '发送过于频繁，请稍后再试')
      } else {
        ElMessage.error(data.message || '创建留言失败')
      }
      return
    }
    ElMessage.success('创建留言成功')
    createDialogVisible.value = false
    // 重新加载第一页
    pagination.value.page = 1
    await resetAndLoad()
  } catch (err) {
    console.error(err)
    ElMessage.error('创建留言失败')
  } finally {
    createSubmitting.value = false
  }
}

const loadReplies = async (reset = false) => {
  if (!activeCard.value) return
  if (replyLoading.value || replyLoadingMore.value) return
  if (reset) {
    replyPagination.value.page = 1
    replies.value = []
  }
  const isFirstPage = replyPagination.value.page === 1 && replies.value.length === 0
  if (isFirstPage) {
    replyLoading.value = true
  } else {
    replyLoadingMore.value = true
  }
  try {
    const res = await http.get(`/message-board/cards/${activeCard.value.id}/replies`, {
      page: replyPagination.value.page,
      page_size: replyPagination.value.page_size
    })
    const data = await res.json()
    if (data.status !== 200) {
      ElMessage.error(data.message || '获取回复列表失败')
      return
    }
    const payload = data.data || {}
    const items: MessageReplyItem[] = payload.items || []
    const pageInfo: Pagination = payload.pagination || replyPagination.value

    if (replyPagination.value.page === 1) {
      replies.value = items
    } else {
      replies.value = [...replies.value, ...items]
    }
    replyPagination.value = pageInfo
  } catch (err) {
    console.error(err)
    ElMessage.error('加载回复列表失败')
  } finally {
    replyLoading.value = false
    replyLoadingMore.value = false
  }
}

const loadMoreReplies = async () => {
  if (!replyPagination.value.has_next) return
  replyPagination.value.page += 1
  await loadReplies()
}

const openCardDetail = async (card: MessageCardItem) => {
  detailLoading.value = true
  try {
    // 获取完整的card详情（包含content）
    const res = await http.get(`/message-board/cards/${card.id}`)
    const data = await res.json()
    if (data.status !== 200) {
      ElMessage.error(data.message || '获取留言详情失败')
      return
    }
    activeCard.value = data.data as MessageCardItem
  } catch (err) {
    console.error(err)
    ElMessage.error('加载留言详情失败')
    // 如果获取详情失败，至少显示列表中的基本信息
    activeCard.value = card
  } finally {
    detailLoading.value = false
  }

  replies.value = []
  replyPagination.value = {
    page: 1,
    page_size: 20,
    total: 0,
    has_next: false
  }
  replyContent.value = ''
  await loadReplies(true)
}

const closeDetail = () => {
  activeCard.value = null
  replies.value = []
}

const submitReply = async () => {
  if (!activeCard.value) return
  if (replySubmitting.value) return
  if (!replyContent.value.trim()) {
    ElMessage.warning('请输入回复内容')
    return
  }
  replySubmitting.value = true
  try {
    const res = await http.post(`/message-board/cards/${activeCard.value.id}/replies`, {
      content: replyContent.value.trim()
    })
    const data = await res.json()
    if (data.status !== 200) {
      if (data.code === 'RATE_LIMIT') {
        ElMessage.error(data.message || '发送过于频繁，请稍后再试')
      } else if (data.code === 'CARD_CLOSED') {
        ElMessage.error(data.message || '该留言已关闭，无法继续回复')
        // 更新本地状态
        activeCard.value.status = 'closed'
      } else {
        ElMessage.error(data.message || '发送回复失败')
      }
      return
    }
    ElMessage.success('发送回复成功')
    replyContent.value = ''
    // 重新加载回复列表第一页
    replyPagination.value.page = 1
    await loadReplies(true)
    // 同步更新卡片的回复数和最后回复时间（简单增加）
    const card = activeCard.value
    card.reply_count += 1
    const now = new Date().toISOString()
    card.last_reply_at = now
  } catch (err) {
    console.error(err)
    ElMessage.error('发送回复失败')
  } finally {
    replySubmitting.value = false
  }
}

const updateCardStatus = async (newStatus: 'created' | 'in_progress' | 'closed') => {
  if (!activeCard.value) return
  if (updatingStatus.value) return
  if (activeCard.value.status === newStatus) return

  updatingStatus.value = true
  try {
    const res = await (http as any).patch(`/message-board/cards/${activeCard.value.id}`, {
      status: newStatus
    })
    const data = await res.json()
    if (data.status !== 200) {
      ElMessage.error(data.message || '更新留言状态失败')
      return
    }

    const updated = data.data
    if (!updated) {
      ElMessage.error('更新留言状态失败')
      return
    }

    // 更新详情中的状态
    activeCard.value.status = updated.status
    activeCard.value.auto_closed = !!updated.auto_closed

    // 同步更新列表中的对应卡片
    const idx = cards.value.findIndex((c) => c.id === updated.id)
    if (idx !== -1) {
      cards.value[idx] = {
        ...cards.value[idx],
        status: updated.status,
        auto_closed: !!updated.auto_closed
      }
    }

    ElMessage.success('更新留言状态成功')
  } catch (err) {
    console.error(err)
    ElMessage.error('更新留言状态失败')
  } finally {
    updatingStatus.value = false
  }
}

const handleChangeStatus = async (newStatus: 'created' | 'in_progress' | 'closed') => {
  if (!activeCard.value) return

  // 关闭时给个确认提示
  if (newStatus === 'closed' && activeCard.value.status !== 'closed') {
    try {
      await ElMessageBox.confirm('确定要关闭该留言吗？关闭后普通用户将无法继续回复。', '确认关闭', {
        type: 'warning',
        confirmButtonText: '确定',
        cancelButtonText: '取消'
      })
    } catch {
      return
    }
  }

  await updateCardStatus(newStatus)
}

const refreshList = async () => {
  pagination.value.page = 1
  await resetAndLoad()
}

const toggleCardHidden = async () => {
  if (!activeCard.value) return
  if (togglingHidden.value) return

  try {
    await ElMessageBox.confirm('隐藏后不可恢复，确定要隐藏这条留言吗？', '确认隐藏', {
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消'
    })
  } catch {
    return
  }

  togglingHidden.value = true
  try {
    const res = await (http as any).patch(`/message-board/cards/${activeCard.value.id}/hide`)
    const data = await res.json()
    if (data.status !== 200) {
      ElMessage.error(data.message || '更新隐藏状态失败')
      return
    }

    const updated = data.data
    if (!updated) {
      ElMessage.error('更新隐藏状态失败')
      return
    }

    // 更新详情中的隐藏状态
    activeCard.value.is_hidden = updated.is_hidden

    // 同步更新列表中的对应卡片
    const idx = cards.value.findIndex((c) => c.id === updated.id)
    if (idx !== -1) {
      cards.value[idx] = {
        ...cards.value[idx],
        is_hidden: updated.is_hidden
      }
    }

    ElMessage.success('已隐藏卡片')
  } catch (err) {
    console.error(err)
    ElMessage.error('更新隐藏状态失败')
  } finally {
    togglingHidden.value = false
  }
}

const toggleReplyHidden = async (reply: MessageReplyItem) => {
  if (togglingHidden.value) return

  if (reply.is_hidden) {
    ElMessage.warning('该评论已被隐藏')
    return
  }

  try {
    await ElMessageBox.confirm('隐藏后不可恢复，确定要隐藏这条评论吗？', '确认隐藏', {
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消'
    })
  } catch {
    return
  }

  togglingHidden.value = true
  try {
    const res = await (http as any).patch(`/message-board/replies/${reply.id}/hide`)
    const data = await res.json()
    if (data.status !== 200) {
      ElMessage.error(data.message || '更新隐藏状态失败')
      return
    }

    // 更新回复列表中的隐藏状态
    const idx = replies.value.findIndex((r) => r.id === reply.id)
    if (idx !== -1) {
      replies.value[idx].is_hidden = data.data.is_hidden
    }

    ElMessage.success('已隐藏评论')
  } catch (err) {
    console.error(err)
    ElMessage.error('更新隐藏状态失败')
  } finally {
    togglingHidden.value = false
  }
}

onMounted(async () => {
  await loadCards()
})
</script>

<template>
  <div class="message-board-page">
    <div class="header-bar">
      <div class="title-area">
        <h2>留言交流板</h2>
        <p class="subtitle">提交 BUG / 新特性需求，或与开发者交流</p>
      </div>

      <div class="header-actions">
        <el-button type="primary" :icon="ChatLineRound" @click="openCreateDialog">
          新建留言
        </el-button>
        <el-button :icon="Refresh" @click="refreshList" :loading="loading">
          刷新
        </el-button>
      </div>
    </div>

    <div class="content-layout">
      <!-- 左侧筛选区 -->
      <aside class="filter-panel">
        <el-card shadow="hover" class="filter-card">
          <template #header>
            <div class="filter-header">
              <span>筛选条件</span>
            </div>
          </template>

          <div class="filter-section">
            <div class="filter-label">状态</div>
            <el-checkbox-group v-model="statusFilter" size="small">
              <el-checkbox v-for="opt in statusOptions" :key="opt.value" :label="opt.value">
                {{ opt.label }}
              </el-checkbox>
            </el-checkbox-group>
          </div>

          <div class="filter-section">
            <div class="filter-label">类型</div>
            <el-checkbox-group v-model="typeFilter" size="small">
              <el-checkbox v-for="opt in typeOptions" :key="opt.value" :label="opt.value">
                {{ opt.label }}
              </el-checkbox>
            </el-checkbox-group>
          </div>

          <div class="filter-section">
            <div class="filter-label">我的</div>
            <el-checkbox v-model="mineOnly" size="small">
              我创建的
            </el-checkbox>
            <el-checkbox v-model="participatedOnly" size="small">
              我回复过的
            </el-checkbox>
          </div>

          <div v-if="isAdmin" class="filter-section">
            <div class="filter-label">管理员选项</div>
            <el-checkbox v-model="showHidden" size="small">
              仅显示隐藏的卡片
            </el-checkbox>
          </div>

          <div class="filter-section">
            <div class="filter-label">发布人</div>
            <el-input v-model="publisherSearch" placeholder="按发布人搜索" size="small" clearable :prefix-icon="Search" />
          </div>

          <div class="filter-section">
            <div class="filter-label">创建时间</div>
            <el-date-picker v-model="createdFrom" type="datetime" placeholder="开始时间" size="small"
              value-format="YYYY-MM-DDTHH:mm:ss" style="width: 100%; margin-bottom: 8px" />
            <el-date-picker v-model="createdTo" type="datetime" placeholder="结束时间" size="small"
              value-format="YYYY-MM-DDTHH:mm:ss" style="width: 100%" />
          </div>

          <div class="filter-section">
            <div class="filter-label">排序</div>
            <div class="order-row">
              <el-select v-model="orderBy" size="small" style="flex: 1">
                <el-option v-for="opt in orderOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
              <el-button-group>
                <el-button size="small" :type="order === 'desc' ? 'primary' : 'default'" @click="order = 'desc'">
                  倒序
                </el-button>
                <el-button size="small" :type="order === 'asc' ? 'primary' : 'default'" @click="order = 'asc'">
                  正序
                </el-button>
              </el-button-group>
            </div>
          </div>

          <div class="filter-footer">
            <el-button type="primary" size="small" :disabled="loading" @click="resetAndLoad">
              应用筛选
            </el-button>
          </div>
        </el-card>
      </aside>

      <!-- 右侧列表 -->
      <section class="list-panel">
        <el-card shadow="never" class="list-card">
          <template #header>
            <div class="list-header">
              <div class="list-title">
                <span>留言列表</span>
                <el-tag type="info" size="small">
                  共 {{ pagination.total }} 条
                </el-tag>
              </div>
            </div>
          </template>

          <div class="list-body" v-loading="loading">
            <div v-if="cards.length === 0 && !loading" class="empty-state">
              <p>当前暂无留言。</p>
              <el-button type="primary" link @click="openCreateDialog">
                立即创建第一条留言
              </el-button>
            </div>

            <div v-else class="card-list">
              <el-card v-for="card in filteredCards" :key="card.id" class="message-card" shadow="hover"
                @click="openCardDetail(card)">
                <div class="card-main">
                  <div class="card-header-row">
                    <div class="card-tags">
                      <el-tag :class="getTypeTagConfig(card.type).type" class="message-tag message-tag-type"
                        size="default">
                        {{ getTypeTagConfig(card.type).label }}
                      </el-tag>
                      <el-tag :class="getStatusTagConfig(card.status).class" class="message-tag message-tag-status"
                        size="default">
                        {{ getStatusTagConfig(card.status).label }}
                      </el-tag>
                      <el-tag v-if="card.auto_closed" class="message-tag" size="default" type="info" effect="plain">
                        系统自动关闭
                      </el-tag>
                      <el-tag v-if="card.is_hidden === true" class="message-tag" size="default" type="warning"
                        effect="plain">
                        已隐藏
                      </el-tag>
                    </div>
                    <div class="card-reply-info">
                      <span class="reply-count">💬 {{ card.reply_count }}</span>
                    </div>
                  </div>

                  <div class="card-title">{{ card.title }}</div>

                  <!-- 内容摘要 -->
                  <div v-if="card.content || card.content_snippet" class="card-content-snippet">
                    {{ getContentSnippet(card.content || card.content_snippet, 100) }}
                  </div>

                  <div class="card-footer-row">
                    <div class="author-info">
                      <div class="avatar">
                        {{ card.author.name?.charAt(0)?.toUpperCase() }}
                      </div>
                      <div class="author-text">
                        <div class="name">{{ card.author.name }}</div>
                        <div class="time">
                          {{ formatTime(card.created_at) }}
                        </div>
                      </div>
                    </div>
                    <div class="last-reply">
                      <span>最后活动：{{ formatTime(card.last_reply_at) }}</span>
                    </div>
                  </div>
                </div>
              </el-card>
            </div>

            <div v-if="pagination.has_next" class="load-more">
              <el-button type="primary" text :loading="loadingMore" :icon="ArrowDown" @click="loadMore">
                {{ loadingMore ? '加载中...' : '加载更多' }}
              </el-button>
            </div>
          </div>
        </el-card>
      </section>
    </div>

    <!-- 右侧详情抽屉 -->
    <el-drawer v-model="activeCard" direction="rtl" size="1000px" :with-header="true" @close="closeDetail">
      <template #header>
        <div class="detail-header" v-if="activeCard">
          <div class="detail-title">
            <el-tag :class="getTypeTagConfig(activeCard.type).type" class="message-tag message-tag-type" size="default">
              {{ getTypeTagConfig(activeCard.type).label }}
            </el-tag>
            <span class="detail-title-text">{{ activeCard.title }}</span>
          </div>
        </div>
      </template>

      <div v-if="activeCard" class="detail-body">
        <div class="detail-meta">
          <div class="detail-author">
            <div class="avatar">
              {{ activeCard.author.name?.charAt(0)?.toUpperCase() }}
            </div>
            <div class="author-text">
              <div class="name">{{ activeCard.author.name }}</div>
              <div class="time">
                {{ formatTime(activeCard.created_at) }}
              </div>
            </div>
          </div>
          <div class="detail-status">
            <el-tag :class="getStatusTagConfig(activeCard.status).class" class="message-tag message-tag-status"
              size="default">
              {{ getStatusTagConfig(activeCard.status).label }}
            </el-tag>
            <el-tag v-if="activeCard.is_hidden === true" size="small" type="warning" effect="plain"
              style="margin-left: 8px;">
              已隐藏
            </el-tag>
            <el-dropdown v-if="isAdmin || activeCard.author.id === authStore.user?.username" trigger="click"
              @click.stop>
              <span class="status-action-text">
                状态操作
                <el-icon class="status-action-icon">
                  <ArrowDown />
                </el-icon>
              </span>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item v-if="activeCard.status !== 'in_progress'" :disabled="updatingStatus"
                    @click="handleChangeStatus('in_progress')">
                    标记为进行中
                  </el-dropdown-item>
                  <el-dropdown-item v-if="activeCard.status !== 'closed'" :disabled="updatingStatus"
                    @click="handleChangeStatus('closed')">
                    关闭留言
                  </el-dropdown-item>
                  <el-dropdown-item v-if="activeCard.status === 'closed'" :disabled="updatingStatus"
                    @click="handleChangeStatus('created')">
                    重新打开
                  </el-dropdown-item>
                  <el-dropdown-item
                    v-if="(isAdmin || activeCard.author.id === authStore.user?.username) && activeCard.is_hidden !== true"
                    :disabled="togglingHidden" @click="toggleCardHidden">
                    隐藏卡片
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>

        <el-divider>内容</el-divider>
        <div class="detail-content" v-loading="detailLoading">
          <div class="detail-content-text" v-html="renderMarkdown(activeCard.content || activeCard.title)"></div>
        </div>

        <div class="reply-section-divider">
          <div class="reply-section-header">
            <h3 class="reply-section-title">💬 评论</h3>
            <span class="reply-section-count">共 {{ replyPagination.total }} 条</span>
          </div>
        </div>
        <div class="reply-section" v-loading="replyLoading">
          <div v-if="replies.length === 0 && !replyLoading" class="reply-empty">
            暂无回复
          </div>
          <div v-else class="reply-list">
            <div v-for="reply in filteredReplies" :key="reply.id" class="reply-item">
              <div class="reply-avatar">
                {{ reply.author.name?.charAt(0)?.toUpperCase() }}
              </div>
              <div class="reply-main">
                <div class="reply-header">
                  <span class="reply-author">{{ reply.author.name }}</span>
                  <span class="reply-time">
                    {{ formatTime(reply.created_at) }}
                  </span>
                  <el-dropdown v-if="isAdmin || reply.author.id === authStore.user?.username" trigger="click"
                    @click.stop>
                    <el-icon class="reply-action-icon" style="cursor: pointer; margin-left: 8px;">
                      <ArrowDown />
                    </el-icon>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item v-if="reply.is_hidden !== true" :disabled="togglingHidden"
                          @click="toggleReplyHidden(reply)">
                          隐藏评论
                        </el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </div>
                <div v-if="reply.is_hidden === true && !isAdmin && reply.author.id !== authStore.user?.username"
                  class="reply-hidden-placeholder">
                  该评论已被管理员隐藏
                </div>
                <div v-else class="reply-content" v-html="renderMarkdown(reply.content)"></div>
              </div>
            </div>
          </div>
          <div v-if="replyPagination.has_next" class="load-more">
            <el-button type="primary" text :loading="replyLoadingMore" :icon="ArrowDown" @click="loadMoreReplies">
              {{ replyLoadingMore ? '加载中...' : '加载更多回复' }}
            </el-button>
          </div>
        </div>

        <div class="reply-input">
          <el-input v-model="replyContent" type="textarea" :rows="3" placeholder="写下你的回复..." />
          <div class="reply-actions">
            <span v-if="activeCard.status === 'closed'" class="reply-closed-tip">
              该留言已关闭，无法继续回复
            </span>
            <el-button type="primary" size="small" :disabled="activeCard.status === 'closed'" :loading="replySubmitting"
              @click="submitReply">
              发送回复
            </el-button>
          </div>
        </div>
      </div>
    </el-drawer>

    <!-- 新建留言弹窗 -->
    <el-dialog v-model="createDialogVisible" title="新建留言" width="560px" destroy-on-close>
      <el-form label-width="80px" class="create-form">
        <el-form-item label="类型">
          <el-radio-group v-model="createForm.type">
            <el-radio-button label="bug">漏洞提交</el-radio-button>
            <el-radio-button label="feat">新特性需求</el-radio-button>
            <el-radio-button label="chat">交流</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="标题">
          <el-input v-model="createForm.title" placeholder="一句话概括你的留言" maxlength="80" show-word-limit />
        </el-form-item>
        <el-form-item label="内容">
          <el-input v-model="createForm.content" type="textarea" :rows="6" placeholder="详细描述你的问题、需求或想法" />
        </el-form-item>
        <el-alert type="info" show-icon :closable="false" class="limit-alert">
          <template #title>
            非管理员用户每分钟仅允许发送一条留言或回复，请尽量一次说明清楚。
          </template>
        </el-alert>
      </el-form>

      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="createSubmitting" @click="submitCreate">
          提交
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.message-board-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
  padding: 4px 0 0;
}

.header-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 4px 4px;
}

.title-area h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  color: #1f2933;
}

.subtitle {
  margin: 4px 0 0;
  font-size: 13px;
  color: #6b7280;
}

.header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.content-layout {
  flex: 1;
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 20px;
  min-height: 0;
  align-items: flex-start;
}

.filter-panel {
  min-width: 0;
}

.filter-card {
  height: 100%;
  border-radius: 12px;
  border: 1px solid #e5e7eb;
}

.filter-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 500;
}

.filter-section {
  margin-bottom: 16px;
}

.filter-section+.filter-section {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #f3f4f6;
}

.filter-label {
  font-size: 13px;
  color: #4b5563;
  margin-bottom: 6px;
}

.order-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.filter-footer {
  display: flex;
  justify-content: flex-end;
}

.list-panel {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.list-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  border: 1px solid #e5e7eb;
}

.list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.list-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.list-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 8px 0;
}

.card-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.message-card {
  cursor: pointer;
  transition: all 0.3s ease;
  border-radius: 12px;
  border: 1px solid #e5e7eb;
  overflow: hidden;
}

.message-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.12);
  border-color: #d1d5db;
}

.card-main {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 4px;
}

.card-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

/* 现代化状态标签样式 */
.message-tag {
  padding: 6px 14px;
  border-radius: 999px;
  font-weight: 600;
  font-size: 13px;
  line-height: 1.4;
  border: none;
  transition: all 0.2s ease;
}

.message-tag-type {
  font-size: 13px;
}

.message-tag-status {
  font-size: 13px;
}

.status-tag-created {
  background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%);
  color: #fff;
}

.status-tag-in-progress {
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
  color: #fff;
}

.status-tag-closed {
  background: linear-gradient(135deg, #6b7280 0%, #4b5563 100%);
  color: #fff;
}

.card-reply-info {
  font-size: 13px;
  color: #6b7280;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 4px;
}

.reply-count {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
  color: #111827;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  line-clamp: 2;
  overflow: hidden;
  margin: 4px 0;
}

/* 内容摘要样式 */
.card-content-snippet {
  font-size: 14px;
  color: #6b7280;
  line-height: 1.6;
  margin: 8px 0;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
  max-height: 4.8em;
}

.card-footer-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}

.author-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.avatar {
  width: 32px;
  height: 32px;
  border-radius: 999px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
  color: #fff;
  flex-shrink: 0;
}

.author-text {
  display: flex;
  flex-direction: column;
}

.author-text .name {
  font-size: 14px;
  color: #111827;
  font-weight: 500;
}

.author-text .time {
  font-size: 12px;
  color: #9ca3af;
  margin-top: 2px;
}

.last-reply {
  font-size: 12px;
  color: #9ca3af;
  text-align: right;
}

.empty-state {
  padding: 40px 0;
  text-align: center;
  color: #6b7280;
}

.load-more {
  display: flex;
  justify-content: center;
  padding: 12px 0 4px;
}

.create-form {
  padding-top: 8px;
}

.limit-alert {
  margin-top: 8px;
}

.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 0;
}

.detail-title {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.detail-title-text {
  font-weight: 600;
  font-size: 18px;
  color: #111827;
}

.detail-body {
  display: flex;
  flex-direction: column;
  gap: 20px;
  height: 100%;
  padding-right: 8px;
}

.detail-meta {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid #f3f4f6;
}

.detail-content-text {
  font-size: 15px;
  color: #111827;
  line-height: 1.8;
  word-wrap: break-word;
}

.detail-content-text :deep(p) {
  margin: 0 0 12px 0;
}

.detail-content-text :deep(p:last-child) {
  margin-bottom: 0;
}

.detail-content-text :deep(code) {
  background: #f3f4f6;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.9em;
  font-family: 'Courier New', monospace;
}

.detail-content-text :deep(pre) {
  background: #f3f4f6;
  padding: 12px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 12px 0;
}

.detail-content-text :deep(pre code) {
  background: none;
  padding: 0;
}

.detail-content-text :deep(ul),
.detail-content-text :deep(ol) {
  margin: 12px 0;
  padding-left: 24px;
}

.detail-content-text :deep(li) {
  margin: 4px 0;
}

.detail-content-text :deep(blockquote) {
  border-left: 4px solid #e5e7eb;
  padding-left: 16px;
  margin: 12px 0;
  color: #6b7280;
  font-style: italic;
}

.detail-content-text :deep(a) {
  color: #3b82f6;
  text-decoration: none;
}

.detail-content-text :deep(a:hover) {
  text-decoration: underline;
}

/* 评论区域分隔 */
.reply-section-divider {
  margin: 24px 0 16px 0;
  padding-top: 20px;
  border-top: 2px solid #f3f4f6;
}

.reply-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.reply-section-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #111827;
}

.reply-section-count {
  font-size: 14px;
  color: #6b7280;
  font-weight: 500;
}

.reply-section {
  max-height: 45vh;
  overflow: auto;
  padding-right: 8px;
  margin-bottom: 16px;
}

.reply-section::-webkit-scrollbar {
  width: 6px;
}

.reply-section::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 3px;
}

.reply-section::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 3px;
}

.reply-section::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}

.reply-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.reply-item {
  display: flex;
  gap: 12px;
  padding: 16px;
  background: #f9fafb;
  border-radius: 12px;
  transition: all 0.2s ease;
}

.reply-item:hover {
  background: #f3f4f6;
  transform: translateX(2px);
}

.reply-avatar {
  width: 36px;
  height: 36px;
  border-radius: 999px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
  color: #fff;
  flex-shrink: 0;
}

.reply-main {
  flex: 1;
}

.reply-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  color: #6b7280;
  margin-bottom: 8px;
}

.reply-author {
  font-weight: 600;
  color: #111827;
  font-size: 14px;
}

.reply-time {
  margin-left: 12px;
  font-size: 12px;
  color: #9ca3af;
}

.reply-content {
  font-size: 14px;
  color: #374151;
  line-height: 1.7;
  word-wrap: break-word;
}

.reply-content :deep(p) {
  margin: 0 0 8px 0;
}

.reply-content :deep(p:last-child) {
  margin-bottom: 0;
}

.reply-content :deep(code) {
  background: #e5e7eb;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.9em;
  font-family: 'Courier New', monospace;
}

.reply-content :deep(pre) {
  background: #e5e7eb;
  padding: 8px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 8px 0;
}

.reply-content :deep(pre code) {
  background: none;
  padding: 0;
}

.reply-empty {
  font-size: 13px;
  color: #6b7280;
}

.reply-input {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #e5e7eb;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.reply-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.reply-closed-tip {
  font-size: 12px;
  color: #ef4444;
}

.reply-action-icon {
  font-size: 14px;
  color: #6b7280;
}

.reply-hidden-placeholder {
  font-size: 13px;
  color: #9ca3af;
  font-style: italic;
  padding: 8px 0;
  border: 1px dashed #d1d5db;
  border-radius: 4px;
  text-align: center;
  margin-top: 4px;
}

.status-action-text {
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #6b7280;
  font-size: 13px;
  padding: 6px 12px;
  border-radius: 6px;
  transition: all 0.2s ease;
  border: 1px solid #e5e7eb;
  background: #fff;
}

.status-action-text:hover {
  background: #f9fafb;
  color: #111827;
  border-color: #d1d5db;
}

.status-action-icon {
  font-size: 12px;
  transition: transform 0.2s ease;
}

.status-action-text:hover .status-action-icon {
  transform: rotate(180deg);
}

@media (max-width: 960px) {
  .content-layout {
    grid-template-columns: minmax(0, 1fr);
  }

  .filter-panel {
    order: 2;
  }

  .list-panel {
    order: 1;
  }
}
</style>
