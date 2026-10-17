import { describe, it, expect } from 'vitest'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const sanitizeMarkdown = (content: string): string => {
  return DOMPurify.sanitize(marked(content, { breaks: true }) as string)
}

describe('announcement HTML sanitization', () => {
  it('should strip <script> tags', () => {
    const result = sanitizeMarkdown('<script>alert("xss")</script>')
    expect(result).not.toContain('<script>')
    expect(result).not.toContain('alert(')
  })

  it('should strip <img onerror> event handlers', () => {
    const result = sanitizeMarkdown('<img src=x onerror="alert(\'xss\')">')
    expect(result).not.toContain('onerror')
    expect(result).not.toContain('alert(')
  })

  it('should allow safe markdown headings', () => {
    const result = sanitizeMarkdown('# Heading 1\n\n## Heading 2')
    expect(result).toContain('<h1')
    expect(result).toContain('Heading 1')
    expect(result).toContain('<h2')
    expect(result).toContain('Heading 2')
  })

  it('should allow bold text', () => {
    const result = sanitizeMarkdown('**bold text**')
    expect(result).toContain('<strong>')
    expect(result).toContain('bold text')
    expect(result).toContain('</strong>')
  })

  it('should allow unordered lists', () => {
    const result = sanitizeMarkdown('- item 1\n- item 2\n- item 3')
    expect(result).toContain('<ul>')
    expect(result).toContain('<li>')
    expect(result).toContain('item 1')
    expect(result).toContain('item 2')
    expect(result).toContain('item 3')
  })

  it('should allow safe links with http/https protocol', () => {
    const result = sanitizeMarkdown('[EVE Online](https://www.eveonline.com/)')
    expect(result).toContain('<a')
    expect(result).toContain('href="https://www.eveonline.com/"')
    expect(result).toContain('EVE Online')
  })

  it('should strip javascript: protocol links', () => {
    const result = sanitizeMarkdown('[click me](javascript:alert("xss"))')
    expect(result).not.toContain('javascript:')
  })


})
