import { ref, computed, type Ref, type ComputedRef } from 'vue'

/**
 * Type-safe fields parsed from announcement markdown frontmatter.
 */
export interface AnnouncementMeta {
  title: string
  published_at: string
  updated_at?: string
  author?: string
  summary?: string
  tags?: string[]
}

/**
 * Complete announcement data returned by useAnnouncements().
 */
export interface Announcement extends AnnouncementMeta {
  content: string
  filename: string
}

type RawMeta = Record<string, string>

const removeQuotes = (value: string): string =>
  value.replace(/^["']|["']$/g, '').trim()

const parseFrontMatter = (
  rawText: string,
): { meta: RawMeta; content: string } => {
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

function parseAnnouncementFromModule(
  rawText: string,
  filename: string,
): Announcement {
  const { meta, content } = parseFrontMatter(rawText)
  return {
    title: meta.title || filename.replace(/\.md$/, ''),
    published_at: meta.published_at || '',
    updated_at: meta.updated_at || undefined,
    author: meta.author || undefined,
    summary: meta.summary || undefined,
    tags: parseTags(meta.tags),
    content,
    filename,
  }
}

/**
 * Loads all announcement markdown files via import.meta.glob,
 * parses their frontmatter, and returns them sorted by published_at descending.
 */
export function useAnnouncements(): {
  announcements: Ref<Announcement[]>
  latest: ComputedRef<Announcement[]>
  loading: Ref<boolean>
} {
  const announcements = ref<Announcement[]>([])
  const loading = ref(true)

  // Same glob pattern used by the original AnnouncementView
  const modules = import.meta.glob('/src/announcements/**/*.md', {
    eager: true,
    query: '?raw',
    import: 'default',
  }) as Record<string, string>

  const parsed: Announcement[] = []
  for (const [path, raw] of Object.entries(modules)) {
    const filename = path.split('/').pop() || ''
    const item = parseAnnouncementFromModule(raw as string, filename)
    parsed.push(item)
  }

  // Sort by published_at descending (newest first)
  parsed.sort(
    (a, b) =>
      new Date(b.published_at).getTime() - new Date(a.published_at).getTime(),
  )
  announcements.value = parsed
  loading.value = false

  const latest = computed(() => announcements.value.slice(0, 3))

  return { announcements, latest, loading }
}
