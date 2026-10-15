import { useEffect, useState } from 'react'

export type ThemeChoice = 'system' | 'light' | 'dark'
const KEY = 'workbench.theme'
const media = () => window.matchMedia('(prefers-color-scheme: dark)')

export function storedTheme(): ThemeChoice {
  const value = localStorage.getItem(KEY)
  return value === 'light' || value === 'dark' ? value : 'system'
}

export function resolveTheme(choice: ThemeChoice): 'light' | 'dark' {
  return choice === 'system' ? (media().matches ? 'dark' : 'light') : choice
}

/** Current resolved theme, read from <html data-theme> (set before first paint by index.html). */
export function currentTheme(): 'light' | 'dark' {
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'
}

export function useTheme(): [ThemeChoice, (choice: ThemeChoice) => void, 'light' | 'dark'] {
  const [choice, setChoice] = useState<ThemeChoice>(storedTheme)
  const [resolved, setResolved] = useState(() => resolveTheme(storedTheme()))
  useEffect(() => {
    const apply = () => {
      const next = resolveTheme(choice)
      document.documentElement.dataset.theme = next
      setResolved(next)
    }
    apply()
    if (choice === 'system') localStorage.removeItem(KEY)
    else localStorage.setItem(KEY, choice)
    const query = media()
    query.addEventListener('change', apply)
    return () => query.removeEventListener('change', apply)
  }, [choice])
  return [choice, setChoice, resolved]
}
