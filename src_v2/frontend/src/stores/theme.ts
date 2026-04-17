import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'

export type ThemeMode = 'light' | 'dark' | 'system'

const THEME_KEY = 'kahuna_theme_mode'

export const useThemeStore = defineStore('theme', () => {
  const mode = ref<ThemeMode>('system')
  const systemPrefersDark = ref(false)

  const resolvedTheme = computed<'light' | 'dark'>(() => {
    if (mode.value === 'system') {
      return systemPrefersDark.value ? 'dark' : 'light'
    }
    return mode.value
  })

  const applyTheme = (theme: 'light' | 'dark') => {
    document.documentElement.setAttribute('data-theme', theme)
  }

  const setMode = (nextMode: ThemeMode) => {
    mode.value = nextMode
  }

  const initTheme = () => {
    const stored = localStorage.getItem(THEME_KEY)
    if (stored === 'light' || stored === 'dark' || stored === 'system') {
      mode.value = stored
    }

    const media = window.matchMedia('(prefers-color-scheme: dark)')
    systemPrefersDark.value = media.matches
    media.addEventListener('change', event => {
      systemPrefersDark.value = event.matches
    })

    applyTheme(resolvedTheme.value)
  }

  watch(mode, value => {
    localStorage.setItem(THEME_KEY, value)
    applyTheme(resolvedTheme.value)
  })

  watch(resolvedTheme, value => {
    applyTheme(value)
  })

  return {
    mode,
    resolvedTheme,
    initTheme,
    setMode,
  }
})
