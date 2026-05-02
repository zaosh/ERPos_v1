import { useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { useTheme } from '../../styles/theme'

// Badge / pill
type BadgeColor = 'default' | 'accent' | 'danger' | 'warning' | 'success'

export function Badge({ children, color = 'default' }: { children: ReactNode; color?: BadgeColor }) {
  const t = useTheme()
  const colors: Record<BadgeColor, { bg: string; text: string }> = {
    default: { bg: t.surface3, text: t.textMuted },
    accent: { bg: t.accentDim, text: t.accentText },
    danger: { bg: t.dangerDim, text: t.danger },
    warning: { bg: t.warningDim, text: t.warning },
    success: { bg: t.successDim, text: t.success },
  }
  const c = colors[color]
  return (
    <span style={{
      background: c.bg, color: c.text,
      padding: '2px 8px', borderRadius: 99,
      fontSize: 11, fontWeight: 600, letterSpacing: '0.02em', whiteSpace: 'nowrap',
    }}>
      {children}
    </span>
  )
}

// Status badge
const STATUS_MAP: Record<string, [BadgeColor, string]> = {
  in_stock: ['success', 'In Stock'],
  sold: ['default', 'Sold'],
  reserved: ['warning', 'Reserved'],
  archived: ['default', 'Archived'],
}

export function StatusBadge({ status }: { status: string }) {
  const [color, label] = STATUS_MAP[status] ?? ['default', status]
  return <Badge color={color}>{label}</Badge>
}

// Card
export function Card({ children, style = {}, onClick }: { children: ReactNode; style?: CSSProperties; onClick?: () => void }) {
  const t = useTheme()
  const [hovered, setHovered] = useState(false)
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: t.surface,
        border: `1px solid ${hovered && onClick ? t.accent : t.border}`,
        borderRadius: 12,
        boxShadow: t.shadow,
        transition: 'border-color 0.15s, box-shadow 0.15s',
        cursor: onClick ? 'pointer' : 'default',
        ...style,
      }}
    >
      {children}
    </div>
  )
}

// Input
export function Input({
  label, value, onChange, placeholder, type = 'text', style = {},
}: {
  label?: string; value: string; onChange: (v: string) => void
  placeholder?: string; type?: string; style?: CSSProperties
}) {
  const t = useTheme()
  const [focused, setFocused] = useState(false)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, ...style }}>
      {label && (
        <label style={{ fontSize: 11, fontWeight: 600, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          {label}
        </label>
      )}
      <input
        type={type} value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        style={{
          background: t.surface2,
          border: `1px solid ${focused ? t.accent : t.border}`,
          borderRadius: 8, padding: '8px 12px',
          color: t.text, fontSize: 14, outline: 'none',
          fontFamily: t.font, transition: 'border-color 0.15s',
          boxShadow: focused ? `0 0 0 3px ${t.accentDim}` : 'none',
        }}
      />
    </div>
  )
}

// Select
export function Select<T extends string>({
  label, value, onChange, options, style = {},
}: {
  label?: string; value: T; onChange: (v: T) => void
  options: Array<{ value: T; label: string }>; style?: CSSProperties
}) {
  const t = useTheme()
  const [focused, setFocused] = useState(false)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, ...style }}>
      {label && (
        <label style={{ fontSize: 11, fontWeight: 600, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          {label}
        </label>
      )}
      <select
        value={value}
        onChange={e => onChange(e.target.value as T)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        style={{
          background: t.surface2,
          border: `1px solid ${focused ? t.accent : t.border}`,
          borderRadius: 8, padding: '8px 12px',
          color: t.text, fontSize: 14, outline: 'none',
          fontFamily: t.font, transition: 'border-color 0.15s',
          cursor: 'pointer', appearance: 'none',
          backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23666' d='M6 8L1 3h10z'/%3E%3C/svg%3E")`,
          backgroundRepeat: 'no-repeat', backgroundPosition: 'right 10px center', paddingRight: 30,
        }}
      >
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  )
}

// Button
type BtnVariant = 'primary' | 'secondary' | 'danger' | 'ghost'
type BtnSize = 'sm' | 'md' | 'lg'

export function Btn({
  children, onClick, variant = 'primary', disabled, full, size = 'md', style = {}, type = 'button',
}: {
  children: ReactNode; onClick?: () => void; variant?: BtnVariant
  disabled?: boolean; full?: boolean; size?: BtnSize; style?: CSSProperties; type?: 'button' | 'submit'
}) {
  const t = useTheme()
  const [hovered, setHovered] = useState(false)
  const sizes: Record<BtnSize, CSSProperties> = {
    sm: { padding: '5px 12px', fontSize: 12 },
    md: { padding: '9px 18px', fontSize: 14 },
    lg: { padding: '13px 24px', fontSize: 15 },
  }
  const variants: Record<BtnVariant, CSSProperties> = {
    primary: { background: t.accent, color: t.bg, border: 'none' },
    secondary: { background: t.surface2, color: t.text, border: `1px solid ${t.border}` },
    danger: { background: t.dangerDim, color: t.danger, border: `1px solid ${t.danger}` },
    ghost: { background: 'transparent', color: t.textMuted, border: `1px solid ${t.border}` },
  }
  return (
    <button
      type={type} onClick={onClick} disabled={disabled}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        ...variants[variant], ...sizes[size],
        borderRadius: 8, fontWeight: 600,
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.45 : 1,
        width: full ? '100%' : undefined,
        transition: 'opacity 0.15s, transform 0.1s, filter 0.15s',
        transform: hovered && !disabled ? 'translateY(-1px)' : 'none',
        filter: hovered && !disabled ? 'brightness(1.08)' : 'none',
        fontFamily: 'inherit', ...style,
      }}
    >
      {children}
    </button>
  )
}

// Chip / quick-tag
export function Chip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  const t = useTheme()
  return (
    <button
      onClick={onClick}
      style={{
        padding: '5px 11px', borderRadius: 99, fontSize: 12, fontWeight: 500,
        cursor: 'pointer', fontFamily: 'inherit',
        background: active ? t.accent : t.surface2,
        color: active ? t.bg : t.textMuted,
        border: `1px solid ${active ? t.accent : t.border}`,
        transition: 'all 0.12s', whiteSpace: 'nowrap',
      }}
    >
      {label}
    </button>
  )
}

// StatCard
export function StatCard({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  const t = useTheme()
  return (
    <Card style={{ padding: '18px 20px' }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 700, color: color || t.text, letterSpacing: '-0.02em', lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: t.textMuted, marginTop: 4 }}>{sub}</div>}
    </Card>
  )
}

// Spinner
export function Spinner({ size = 20 }: { size?: number }) {
  const t = useTheme()
  return (
    <div style={{
      width: size, height: size,
      border: `2px solid ${t.border}`, borderTopColor: t.accent,
      borderRadius: '50%', animation: 'spin 0.7s linear infinite',
    }} />
  )
}

// Empty state
export function Empty({ message }: { message: string }) {
  const t = useTheme()
  return <div style={{ textAlign: 'center', color: t.textMuted, padding: '40px 0', fontSize: 14 }}>{message}</div>
}

// Error alert
export function ErrorAlert({ message, onDismiss }: { message: string | null; onDismiss?: () => void }) {
  const t = useTheme()
  if (!message) return null
  return (
    <div style={{
      background: t.dangerDim, border: `1px solid ${t.danger}`,
      borderRadius: 8, padding: '10px 14px', color: t.danger,
      fontSize: 13, display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    }}>
      {message}
      {onDismiss && (
        <button onClick={onDismiss} style={{ background: 'none', border: 'none', color: t.danger, cursor: 'pointer', fontSize: 16, lineHeight: 1 }}>×</button>
      )}
    </div>
  )
}

// Section header
export function SectionHeader({ children }: { children: ReactNode }) {
  const t = useTheme()
  return <h2 style={{ fontSize: 18, fontWeight: 700, color: t.text, margin: 0 }}>{children}</h2>
}

// Panel (card with title header)
export function Panel({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  const t = useTheme()
  return (
    <Card style={{ overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '14px 18px', borderBottom: `1px solid ${t.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontWeight: 700, fontSize: 14, color: t.text }}>{title}</span>
        {action}
      </div>
      <div style={{ padding: '16px 18px', flex: 1 }}>{children}</div>
    </Card>
  )
}
