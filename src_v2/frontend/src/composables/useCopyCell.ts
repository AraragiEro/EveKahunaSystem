/**
 * 「点击复制」单元格的通用行为。
 *
 * 两个坑（都在流程图表格里踩过）：
 * 1. 复制成功的高亮**不能**靠 `:cell-class-name` 返回响应式状态 —— EP 不会因为
 *    那个响应式值变化而重新渲染已渲染的单元格，class 会一直停在初始值。
 *    所以这里直接在点击时给 td 加/删 class。
 * 2. `event.currentTarget` 在事件派发结束后会被浏览器置为 null，
 *    而复制是异步的（await navigator.clipboard.writeText），
 *    必须在 await 之前**同步**取出 td。
 */

const COPIED_CLASS = 'is-copied'
const COPIED_DURATION = 1200

/** 给被点击的单元格加「已复制」高亮，duration 毫秒后移除 */
export function flashCopied(ev: MouseEvent | undefined, duration = COPIED_DURATION) {
    // 同步取 td：await 之后 currentTarget 会变 null
    const el = (ev?.currentTarget || ev?.target) as HTMLElement | null
    const td = el?.closest?.('td') as HTMLElement | null
    if (!td) return
    td.classList.add(COPIED_CLASS)
    window.setTimeout(() => td.classList.remove(COPIED_CLASS), duration)
}

/**
 * 生成 el-table 的 `:cell-class-name`。
 * 只负责给「可复制列」打静态 class（copy-col），不参与复制状态。
 */
export function createCopyCellClassName(copyableProps: string[]) {
    return ({ column }: { column?: { property?: string } }) => {
        const prop = column?.property
        return prop && copyableProps.includes(prop) ? 'copy-col' : ''
    }
}
