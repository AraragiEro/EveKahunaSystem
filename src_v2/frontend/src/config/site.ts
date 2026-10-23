/**
 * 站点级常量：品牌名、版本号、外链。
 * 组件里不要再硬编码这些值，避免页头 / 页脚 / 关于页各写一份而后互相对不上。
 */

export const SITE_NAME = 'Kahuna System'
export const SITE_NAME_EN = 'Kahuna-System'

/** 对外展示的版本号（与 package.json / 发布标签保持同步） */
export const APP_VERSION = 'V1.6.3'

export const GITHUB_REPO_URL = 'https://github.com/AraragiEro/EveKahunaSystem.git'

export const OPEN_SOURCE_LICENSE = 'AGPL-3.0'

/** 版权起始年份，展示时取 max(当前年, 该年份) */
export const COPYRIGHT_SINCE = 2026

/** 页脚右侧版权文本用到的年份 */
export const copyrightYear = (): number => Math.max(COPYRIGHT_SINCE, new Date().getFullYear())
