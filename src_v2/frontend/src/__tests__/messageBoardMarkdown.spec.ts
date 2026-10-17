import { describe, it, expect } from 'vitest'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

// 与 messageBoardView.vue renderMarkdown 使用相同的 sanitization pipeline
const sanitizeMarkdown = (content: string): string => {
  const rawHtml = marked(content, { breaks: true }) as string
  return DOMPurify.sanitize(rawHtml)
}

describe('messageBoard renderMarkdown XSS sanitization', () => {
  it('should strip <script> tags', () => {
    const result = sanitizeMarkdown("<script>alert('xss')</script>")
    expect(result).not.toContain('<script>')
    expect(result).not.toContain('alert')
  })

  it('should strip img onerror event handlers', () => {
    const result = sanitizeMarkdown('<img onerror="alert(1)" src=x>')
    expect(result).not.toContain('onerror')
  })

  it('should allow safe inline elements: <b>, <em>, <code>', () => {
    const result = sanitizeMarkdown('<b>bold</b> <em>italic</em> <code>code</code>')
    expect(result).toContain('<b>bold</b>')
    expect(result).toContain('<em>italic</em>')
    expect(result).toContain('<code>code</code>')
  })

  it('should render markdown headings, lists, and links', () => {
    const result = sanitizeMarkdown('# Heading\n\n- item 1\n- item 2\n\n[link](https://example.com)')
    expect(result).toContain('<h1')
    expect(result).toContain('Heading')
    expect(result).toContain('<ul>')
    expect(result).toContain('<li>item 1</li>')
    expect(result).toContain('<li>item 2</li>')
    expect(result).toContain('<a href="https://example.com"')
  })

  it('should strip javascript: protocol from links', () => {
    const result = sanitizeMarkdown('[click me](javascript:alert(1))')
    expect(result).not.toContain('javascript:')
  })

  it('should return empty string for empty content', () => {
    expect(sanitizeMarkdown('')).toBe('')
  })

  it('should render markdown bold and italic', () => {
    const result = sanitizeMarkdown('**bold** and *italic*')
    expect(result).toContain('<strong>bold</strong>')
    expect(result).toContain('<em>italic</em>')
  })

  it('should render inline code', () => {
    const result = sanitizeMarkdown('use `const x = 1` here')
    expect(result).toContain('<code>const x = 1</code>')
  })
})
