import { describe, it, expect } from 'vitest'
import DOMPurify from 'dompurify'
import { marked } from 'marked'

describe('HelpDrawer HTML sanitization', () => {
  const sanitizeAndRender = (md: string): string => {
    const html = marked(md, { breaks: true }) as string
    return DOMPurify.sanitize(html)
  }

  it('should strip <script> tags from rendered markdown', () => {
    const md = '# Hello\n<script>alert("xss")</script>'
    const result = sanitizeAndRender(md)
    expect(result).not.toContain('<script>')
    expect(result).not.toContain('alert("xss")')
    expect(result).toContain('<h1')
  })

  it('should strip img onerror event handlers from inline HTML', () => {
    const md = '<img src=x onerror="alert(1)">'
    const result = sanitizeAndRender(md)
    expect(result).not.toContain('onerror')
    expect(result).not.toContain('alert(1)')
  })

  it('should allow safe markdown headings', () => {
    const md = '# Title\n## Subtitle\n### Deep'
    const result = sanitizeAndRender(md)
    expect(result).toContain('<h1')
    expect(result).toContain('<h2')
    expect(result).toContain('<h3')
  })

  it('should allow safe inline code', () => {
    const md = 'Use `const x = 1` for assignment'
    const result = sanitizeAndRender(md)
    expect(result).toContain('<code>const x = 1</code>')
  })

  it('should allow ordered lists', () => {
    const md = '1. First\n2. Second\n3. Third'
    const result = sanitizeAndRender(md)
    expect(result).toContain('<ol>')
    expect(result).toContain('<li>')
  })

  it('should allow safe links', () => {
    const md = '[Google](https://google.com)'
    const result = sanitizeAndRender(md)
    expect(result).toContain('<a href="https://google.com"')
  })

  it('should strip javascript: protocol links', () => {
    const md = '[click](javascript:alert(1))'
    const result = sanitizeAndRender(md)
    expect(result).not.toContain('javascript:')
  })

  it('should strip iframe tags', () => {
    const md = 'Look: <iframe src="https://evil.com"></iframe>'
    const result = sanitizeAndRender(md)
    expect(result).not.toContain('<iframe')
  })
})
