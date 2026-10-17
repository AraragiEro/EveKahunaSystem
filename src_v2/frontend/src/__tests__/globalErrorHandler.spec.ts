import { describe, it, expect, vi } from 'vitest'
import { createApp, defineComponent, h, nextTick } from 'vue'

describe('Global Vue Error Handler', () => {
  it('should register app.config.errorHandler and catch render errors', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    // 创建一个会抛出错误的组件
    const ErrorComponent = defineComponent({
      name: 'ErrorComponent',
      setup() {
        throw new Error('Test render error')
      },
    })

    // 创建一个不会抛出错误作为容器的包装组件
    const WrapperComponent = defineComponent({
      name: 'WrapperComponent',
      components: { ErrorComponent },
      setup() {
        return () => h('div', {}, [
          h(ErrorComponent),
        ])
      },
    })

    const app = createApp(WrapperComponent)

    let caughtError: unknown = null
    app.config.errorHandler = (err, _instance, _info) => {
      caughtError = err
    }

    // 挂载（会触发内部错误，但 errorHandler 会捕获）
    const container = document.createElement('div')
    app.mount(container)

    await nextTick()

    // 验证 error handler 被调用
    expect(caughtError).toBeDefined()
    expect(caughtError instanceof Error).toBe(true)
    expect((caughtError as Error).message).toBe('Test render error')

    errorSpy.mockRestore()
  })

  it('should log to console.error when errorHandler is configured to do so', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    const ErrorComponent = defineComponent({
      name: 'ErrorComponent',
      setup() {
        throw new Error('Logged error')
      },
    })

    const WrapperComponent = defineComponent({
      name: 'WrapperComponent',
      components: { ErrorComponent },
      setup() {
        return () => h('div', {}, [h(ErrorComponent)])
      },
    })

    const app = createApp(WrapperComponent)
    app.config.errorHandler = (err, instance, info) => {
      console.error('[Vue Error]', err, info)
    }

    const container = document.createElement('div')
    app.mount(container)

    await nextTick()

    expect(errorSpy).toHaveBeenCalledWith('[Vue Error]', expect.any(Error), expect.any(String))

    errorSpy.mockRestore()
  })
})
