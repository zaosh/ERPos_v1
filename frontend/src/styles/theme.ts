export interface Theme {
  name: string
  bg: string
  surface: string
  surface2: string
  surface3: string
  border: string
  text: string
  textMuted: string
  textDim: string
  accent: string
  accentDim: string
  accentText: string
  danger: string
  dangerDim: string
  warning: string
  warningDim: string
  success: string
  successDim: string
  shadow: string
  shadowLg: string
  navBg: string
  font: string
  mono: string
}

export const THEMES: Record<string, Theme> = {
  dark: {
    name: 'Dark Terminal',
    bg: '#0a0a0a',
    surface: '#141414',
    surface2: '#1e1e1e',
    surface3: '#252525',
    border: '#2a2a2a',
    text: '#e8e8e2',
    textMuted: '#666',
    textDim: '#444',
    accent: '#00e5a0',
    accentDim: 'rgba(0,229,160,0.12)',
    accentText: '#00c98a',
    danger: '#ff5252',
    dangerDim: 'rgba(255,82,82,0.1)',
    warning: '#ffb74d',
    warningDim: 'rgba(255,183,77,0.1)',
    success: '#69f0ae',
    successDim: 'rgba(105,240,174,0.1)',
    shadow: '0 2px 12px rgba(0,0,0,0.4)',
    shadowLg: '0 8px 32px rgba(0,0,0,0.6)',
    navBg: '#0d0d0d',
    font: '"IBM Plex Sans", system-ui, sans-serif',
    mono: '"IBM Plex Mono", monospace',
  },
  stone: {
    name: 'Warm Stone',
    bg: '#f7f4f0',
    surface: '#ffffff',
    surface2: '#f0ece6',
    surface3: '#e8e2d9',
    border: '#ddd6cb',
    text: '#1a1614',
    textMuted: '#8a7d72',
    textDim: '#c2b8ae',
    accent: '#c2410c',
    accentDim: 'rgba(194,65,12,0.08)',
    accentText: '#9a3412',
    danger: '#dc2626',
    dangerDim: 'rgba(220,38,38,0.08)',
    warning: '#d97706',
    warningDim: 'rgba(217,119,6,0.08)',
    success: '#16a34a',
    successDim: 'rgba(22,163,74,0.08)',
    shadow: '0 2px 8px rgba(0,0,0,0.06)',
    shadowLg: '0 8px 24px rgba(0,0,0,0.1)',
    navBg: '#1a1614',
    font: '"IBM Plex Sans", system-ui, sans-serif',
    mono: '"IBM Plex Mono", monospace',
  },
  indigo: {
    name: 'Indigo',
    bg: '#f0f4ff',
    surface: '#ffffff',
    surface2: '#eef2ff',
    surface3: '#e0e7ff',
    border: '#c7d2fe',
    text: '#1e1b4b',
    textMuted: '#6366f1',
    textDim: '#a5b4fc',
    accent: '#4f46e5',
    accentDim: 'rgba(79,70,229,0.08)',
    accentText: '#3730a3',
    danger: '#dc2626',
    dangerDim: 'rgba(220,38,38,0.08)',
    warning: '#d97706',
    warningDim: 'rgba(217,119,6,0.08)',
    success: '#16a34a',
    successDim: 'rgba(22,163,74,0.08)',
    shadow: '0 2px 8px rgba(79,70,229,0.08)',
    shadowLg: '0 8px 24px rgba(79,70,229,0.12)',
    navBg: '#1e1b4b',
    font: '"IBM Plex Sans", system-ui, sans-serif',
    mono: '"IBM Plex Mono", monospace',
  },
}

import { createContext, useContext } from 'react'

export const ThemeContext = createContext<Theme>(THEMES.dark)
export const useTheme = () => useContext(ThemeContext)
