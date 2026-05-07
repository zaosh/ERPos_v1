import { useState, useEffect, useRef, useCallback } from 'react'
import type React from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useCamera } from '../hooks/useCamera'
import { api, apiErrorMessage } from '../utils/api'
import { useTheme } from '../styles/theme'
import { Badge, Btn, Chip, ErrorAlert, SectionHeader, Spinner, Select } from '../components/ui'
import type { ItemFormData } from '../components/CVResultCard'
import { ITEM_CATEGORIES, ITEM_CONDITIONS, ITEM_TYPES } from '../utils/constants'
import { money } from '../utils/currency'

type Stage = 'camera' | 'confirm' | 'success'
type CaptureMode = 'auto' | 'rapid'

const MODE_KEY = 'intake_capture_mode'

interface CaptureResult {
  temp_image_id: string
  color: string | null
}

interface CreateResult {
  id: number
  barcode: string
  category: string
  color: string | null
  size: string | null
  price: string
  cv_job_id: number | null
  print_job_id: number | null
  barcode_image: string | null
  bulk_group_id?: string | null
}

interface BulkCreateResult {
  bulk_group_id: string
  total: number
  items: CreateResult[]
  print_job_ids: number[]
}

interface JobStatus {
  status: 'pending' | 'processing' | 'complete' | 'failed'
  result?: Record<string, unknown>
  error_message?: string | null
}

const SIZES = ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL', 'One Size']
const COLORS_QUICK = ['black', 'white', 'grey', 'navy', 'blue', 'red', 'green', 'brown', 'cream', 'pink', 'yellow', 'orange', 'purple']

const DEFAULT_FORM: ItemFormData = {
  temp_image_id: '', category: 'tshirt', color: '', secondary_color: '',
  type: 'unknown', label: '', size: '', condition: 'good', price: '', notes: '',
}

// ─── Job status poller ────────────────────────────────────────────────────────

function useJobPoll(jobId: number | null, stopOn: string[]) {
  const [stopped, setStopped] = useState(false)
  const result = useQuery<JobStatus>({
    queryKey: ['job', jobId],
    queryFn: async () => {
      const { data } = await api.get<JobStatus>(`/jobs/${jobId}/status`)
      return data
    },
    enabled: jobId !== null && !stopped,
    refetchInterval: (query) => {
      const st = query.state.data?.status
      if (st && stopOn.includes(st)) {
        setStopped(true)
        return false
      }
      return 500
    },
  })
  return result.data ?? null
}

// ─── Camera panel ─────────────────────────────────────────────────────────────

function CameraPanel({ onCapture, capturing, videoRef, ready, error, restart, mode, onModeToggle }: {
  onCapture: () => void; capturing: boolean
  videoRef: React.RefObject<HTMLVideoElement>; ready: boolean
  error: string | null; restart: () => void
  mode: CaptureMode; onModeToggle: () => void
}) {
  const t = useTheme()
  const [hovering, setHovering] = useState(false)

  // ─ Motion detection state
  const [motionState, setMotionState] = useState<'watching' | 'still' | 'capturing'>('watching')
  const prevPixelsRef = useRef<number[] | null>(null)
  const stillSinceRef = useRef<number | null>(null)
  const rafRef = useRef<number | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const captureCalledRef = useRef(false)

  // Motion detection thresholds (match backend defaults)
  const MOTION_THRESHOLD_PCT = 15
  const STILLNESS_MS = 800

  const stopMotion = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
    prevPixelsRef.current = null
    stillSinceRef.current = null
    captureCalledRef.current = false
    setMotionState('watching')
  }, [])

  useEffect(() => {
    if (mode !== 'auto' || !ready || capturing) {
      stopMotion()
      return
    }

    const GRID = 10
    const canvas = document.createElement('canvas')
    canvas.width = GRID
    canvas.height = GRID
    canvasRef.current = canvas
    const ctx = canvas.getContext('2d')!

    const tick = (now: number) => {
      const video = videoRef.current
      if (!video || video.readyState < 2) {
        rafRef.current = requestAnimationFrame(tick)
        return
      }

      ctx.drawImage(video, 0, 0, GRID, GRID)
      const data = ctx.getImageData(0, 0, GRID, GRID).data
      const pixels: number[] = []
      for (let i = 0; i < data.length; i += 4) {
        // Luminance approximation
        pixels.push(0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2])
      }

      const prev = prevPixelsRef.current
      prevPixelsRef.current = pixels

      if (prev) {
        let diff = 0
        for (let i = 0; i < pixels.length; i++) diff += Math.abs(pixels[i] - prev[i])
        const avgDiff = diff / pixels.length
        const pct = (avgDiff / 255) * 100

        if (pct > MOTION_THRESHOLD_PCT) {
          // Motion — reset stillness timer
          stillSinceRef.current = null
          captureCalledRef.current = false
          setMotionState('watching')
        } else {
          // Below threshold — start/continue stillness countdown
          if (!stillSinceRef.current) stillSinceRef.current = now
          const elapsed = now - stillSinceRef.current

          if (elapsed >= STILLNESS_MS && !captureCalledRef.current) {
            captureCalledRef.current = true
            setMotionState('capturing')
            onCapture()
          } else if (elapsed > 0) {
            setMotionState('still')
          }
        }
      }

      if (!captureCalledRef.current) {
        rafRef.current = requestAnimationFrame(tick)
      }
    }

    rafRef.current = requestAnimationFrame(tick)
    return stopMotion
  }, [mode, ready, capturing, onCapture, stopMotion])

  // Reset motion state when a new capture completes
  useEffect(() => {
    if (!capturing && mode === 'auto') {
      captureCalledRef.current = false
      setMotionState('watching')
    }
  }, [capturing, mode])

  if (error) {
    return (
      <div style={{ width: '100%', aspectRatio: '4/3', background: t.dangerDim, border: `1px solid ${t.danger}`, borderRadius: 16, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12 }}>
        <span style={{ color: t.danger, fontSize: 14 }}>Camera error: {error}</span>
        <Btn variant="ghost" onClick={restart} size="sm">Try again</Btn>
      </div>
    )
  }

  const isAuto = mode === 'auto'
  const borderColor = isAuto
    ? (motionState === 'capturing' ? t.success : motionState === 'still' ? t.accent : `${t.accent}55`)
    : (hovering && ready ? t.accent : t.border)
  const borderStyle = isAuto || (hovering && ready) ? 'solid' : 'dashed'
  const pulseAnim = isAuto && motionState === 'watching' && ready && !capturing

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {/* Mode toggle */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 11, color: t.textMuted, fontFamily: t.mono, textTransform: 'uppercase', letterSpacing: '0.06em' }}>capture mode</span>
        <div style={{ display: 'flex', background: t.surface2, border: `1px solid ${t.border}`, borderRadius: 8, overflow: 'hidden' }}>
          {(['auto', 'rapid'] as CaptureMode[]).map(m => (
            <button key={m} onClick={() => { if (mode !== m) onModeToggle() }}
              style={{
                padding: '5px 14px', fontSize: 11, fontWeight: 600, cursor: 'pointer', border: 'none',
                background: mode === m ? t.accent : 'transparent',
                color: mode === m ? t.bg : t.textMuted,
                fontFamily: 'inherit', transition: 'all 0.15s',
              }}>{m === 'auto' ? 'Auto' : 'Rapid'}</button>
          ))}
        </div>
      </div>

      {/* Camera viewport */}
      <div
        onMouseEnter={() => setHovering(true)}
        onMouseLeave={() => setHovering(false)}
        onClick={() => mode === 'rapid' && !capturing && ready && onCapture()}
        style={{
          width: '100%', aspectRatio: '4/3',
          background: '#000',
          border: `2px ${borderStyle} ${borderColor}`,
          borderRadius: 16,
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          cursor: mode === 'rapid' && !capturing && ready ? 'pointer' : 'default',
          transition: 'border-color 0.3s',
          position: 'relative', overflow: 'hidden',
          animation: pulseAnim ? 'borderPulse 2s ease-in-out infinite' : 'none',
        }}
      >
        <video ref={videoRef} autoPlay playsInline muted
          style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: ready ? 1 : 0 }} />

        {/* Scan line — rapid mode only */}
        {mode === 'rapid' && !capturing && ready && (
          <div style={{
            position: 'absolute', left: 0, right: 0, height: 2,
            background: `linear-gradient(90deg, transparent, ${t.accent}, transparent)`,
            animation: 'scanline 2s linear infinite',
            opacity: hovering ? 0.8 : 0.3, pointerEvents: 'none',
          }} />
        )}

        {/* Corner brackets */}
        {(['tl', 'tr', 'bl', 'br'] as const).map(pos => (
          <div key={pos} style={{
            position: 'absolute', width: 20, height: 20, borderColor: t.accent, borderStyle: 'solid', borderWidth: 0,
            ...(pos === 'tl' ? { top: 12, left: 12, borderTopWidth: 2, borderLeftWidth: 2 } :
                pos === 'tr' ? { top: 12, right: 12, borderTopWidth: 2, borderRightWidth: 2 } :
                pos === 'bl' ? { bottom: 12, left: 12, borderBottomWidth: 2, borderLeftWidth: 2 } :
                { bottom: 12, right: 12, borderBottomWidth: 2, borderRightWidth: 2 }),
            opacity: 0.6, zIndex: 2,
          }} />
        ))}

        {/* Status overlay */}
        <div style={{ position: 'relative', zIndex: 3 }}>
          {capturing ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
              <Spinner size={32} />
              <span style={{ color: t.accent, fontSize: 13, fontFamily: t.mono }}>uploading…</span>
            </div>
          ) : !ready ? (
            <span style={{ color: t.textMuted, fontSize: 13 }}>Starting camera…</span>
          ) : null}
        </div>

        {/* Auto mode status indicator */}
        {isAuto && ready && !capturing && (
          <div style={{ position: 'absolute', bottom: 16, left: 0, right: 0, display: 'flex', justifyContent: 'center', zIndex: 3 }}>
            <div style={{
              background: 'rgba(0,0,0,0.7)', borderRadius: 8, padding: '5px 14px',
              fontSize: 11, fontFamily: t.mono, letterSpacing: '0.08em',
              color: motionState === 'capturing' ? t.success : motionState === 'still' ? t.accent : t.textMuted,
              textTransform: 'uppercase',
            }}>
              {motionState === 'capturing' ? '● capturing' : motionState === 'still' ? '◉ still' : '○ watching'}
            </div>
          </div>
        )}

        {/* Rapid mode hint */}
        {mode === 'rapid' && !capturing && ready && (
          <div style={{ position: 'absolute', bottom: 16, left: 0, right: 0, display: 'flex', justifyContent: 'center', zIndex: 3 }}>
            <div style={{ background: 'rgba(0,0,0,0.6)', borderRadius: 8, padding: '6px 14px', fontSize: 12, color: t.accent, fontWeight: 600 }}>
              Click to capture
            </div>
          </div>
        )}
      </div>

      {/* Rapid mode: large explicit button */}
      {mode === 'rapid' && (
        <Btn variant="primary" onClick={onCapture} disabled={capturing || !ready} full>
          {capturing ? 'Uploading…' : '📸 Capture'}
        </Btn>
      )}
    </div>
  )
}

// ─── Thumbnail placeholder ────────────────────────────────────────────────────

function ThumbnailPreview({ color }: { color: string }) {
  const t = useTheme()
  const colorHex: Record<string, string> = {
    black: '#222', white: '#eee', grey: '#888', navy: '#1a3a6b', blue: '#3b7dd8',
    red: '#e53e3e', green: '#38a169', brown: '#7b5230', cream: '#f5ead6',
    pink: '#ed64a6', purple: '#805ad5', yellow: '#ecc94b', orange: '#ed8936',
  }
  const hex = colorHex[color] || t.surface3
  return (
    <div style={{ width: '100%', aspectRatio: '1/1', background: t.surface2, borderRadius: 12, border: `1px solid ${t.border}`, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8, position: 'relative' }}>
      <div style={{ width: 60, height: 72, background: hex, borderRadius: 8, boxShadow: '0 4px 16px rgba(0,0,0,0.3)', opacity: 0.85 }} />
      <span style={{ color: t.textMuted, fontSize: 10, fontFamily: t.mono, letterSpacing: '0.05em' }}>captured</span>
      <div style={{ position: 'absolute', top: 8, right: 8 }}><Badge color="success">saved</Badge></div>
    </div>
  )
}

// ─── Intake form ──────────────────────────────────────────────────────────────

function IntakeForm({ detectedColor, form, setForm, onSubmit, onReset, submitting, quantity, setQuantity }: {
  detectedColor: string | null
  form: ItemFormData
  setForm: React.Dispatch<React.SetStateAction<ItemFormData>>
  onSubmit: () => void
  onReset: () => void
  submitting: boolean
  quantity: number
  setQuantity: (n: number) => void
}) {
  const t = useTheme()
  const set = (field: keyof ItemFormData, val: string) => setForm(f => ({ ...f, [field]: val }))

  return (
    <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      {/* Thumbnail + color hint */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16 }}>
        <div style={{ width: 100, flexShrink: 0 }}>
          <ThumbnailPreview color={form.color} />
        </div>
        <div style={{ flex: 1 }}>
          {detectedColor && (
            <div style={{ background: t.accentDim, border: `1px solid ${t.accent}33`, borderRadius: 10, padding: '10px 14px', display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <span style={{ fontSize: 11, color: t.textMuted }}>K-means detected:</span>
              <Badge color="accent">color: {detectedColor}</Badge>
            </div>
          )}
          <div style={{ marginTop: 12, padding: '10px 14px', background: t.surface2, borderRadius: 10, border: `1px solid ${t.border}` }}>
            <div style={{ fontSize: 11, color: t.textMuted, fontFamily: t.mono }}>type: analyzing…</div>
            <div style={{ fontSize: 10, color: t.textDim, marginTop: 3 }}>Worker will fill in type after save</div>
          </div>
        </div>
      </div>

      {/* Category chips */}
      <div>
        <label style={{ fontSize: 11, fontWeight: 600, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 6 }}>Category</label>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {ITEM_CATEGORIES.map(c => <Chip key={c} label={c} active={form.category === c} onClick={() => set('category', c)} />)}
        </div>
      </div>

      {/* Color chips */}
      <div>
        <label style={{ fontSize: 11, fontWeight: 600, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 6 }}>Primary Color</label>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {COLORS_QUICK.map(c => <Chip key={c} label={c} active={form.color === c} onClick={() => set('color', c)} />)}
        </div>
      </div>

      {/* Size chips */}
      <div>
        <label style={{ fontSize: 11, fontWeight: 600, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 6 }}>Size</label>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {SIZES.map(s => <Chip key={s} label={s} active={form.size === s} onClick={() => set('size', s)} />)}
        </div>
      </div>

      {/* Type + Condition */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <Select label="Type" value={form.type} onChange={v => set('type', v)}
          options={ITEM_TYPES.map(t => ({ value: t, label: t.replace('_', ' ') }))} />
        <Select label="Condition" value={form.condition} onChange={v => set('condition', v)}
          options={ITEM_CONDITIONS.map(c => ({ value: c, label: c }))} />
      </div>

      {/* Label + Price */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <label style={{ fontSize: 11, fontWeight: 600, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Label / Brand</label>
          <input type="text" value={form.label} onChange={e => set('label', e.target.value)}
            placeholder="e.g. Nike, AC/DC, plain"
            style={{ background: t.surface2, border: `1px solid ${t.border}`, borderRadius: 8, padding: '8px 12px', color: t.text, fontSize: 14, outline: 'none', fontFamily: 'inherit' }} />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <label style={{ fontSize: 11, fontWeight: 600, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Price (₹)</label>
          <input type="number" step="0.01" min="0.01" value={form.price} onChange={e => set('price', e.target.value)}
            placeholder="5.00"
            style={{ background: t.surface2, border: `1px solid ${t.border}`, borderRadius: 8, padding: '8px 12px', color: t.text, fontSize: 14, outline: 'none', fontFamily: 'inherit' }} />
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <label style={{ fontSize: 11, fontWeight: 600, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Notes (optional)</label>
        <input type="text" value={form.notes} onChange={e => set('notes', e.target.value)}
          placeholder="any additional notes…"
          style={{ background: t.surface2, border: `1px solid ${t.border}`, borderRadius: 8, padding: '8px 12px', color: t.text, fontSize: 14, outline: 'none', fontFamily: 'inherit' }} />
      </div>

      {/* Quantity selector — subtle, default 1 so single-item flow is unaffected */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, background: t.surface2, border: `1px solid ${t.border}`, borderRadius: 10, padding: '10px 14px' }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em', flex: 1 }}>Quantity</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button onClick={() => setQuantity(Math.max(1, quantity - 1))} disabled={quantity <= 1}
            style={{ width: 28, height: 28, borderRadius: 6, border: `1px solid ${t.border}`, background: t.surface3, color: t.text, fontSize: 16, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>−</button>
          <span style={{ fontFamily: t.mono, fontWeight: 700, fontSize: 16, color: quantity > 1 ? t.accent : t.text, minWidth: 28, textAlign: 'center' }}>{quantity}</span>
          <button onClick={() => setQuantity(Math.min(50, quantity + 1))} disabled={quantity >= 50}
            style={{ width: 28, height: 28, borderRadius: 6, border: `1px solid ${t.border}`, background: t.surface3, color: t.text, fontSize: 16, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>+</button>
        </div>
        {quantity > 1 && (
          <span style={{ fontSize: 12, color: t.textMuted }}>Will create {quantity} items · print {quantity} labels</span>
        )}
      </div>

      <div style={{ display: 'flex', gap: 10, paddingTop: 4 }}>
        <Btn variant="ghost" onClick={onReset} style={{ flex: 1 }}>Retake</Btn>
        <Btn variant="primary" onClick={onSubmit} disabled={submitting || !form.price} style={{ flex: 2 }}>
          {submitting ? 'Saving…' : quantity > 1 ? `Confirm & Print ${quantity} Labels` : 'Confirm & Print Label'}
        </Btn>
      </div>
    </div>
  )
}

// ─── Success screen ───────────────────────────────────────────────────────────

function IntakeSuccess({ item, onNext }: { item: CreateResult; onNext: () => void }) {
  const t = useTheme()
  const printJob = useJobPoll(item.print_job_id, ['complete', 'failed'])
  const cvJob = useJobPoll(item.cv_job_id, ['complete', 'failed'])

  const printStatus = printJob?.status ?? 'pending'
  const cvStatus = cvJob?.status ?? 'pending'
  const cvType = (cvJob?.result as any)?.type

  const printLabel = printStatus === 'complete' ? 'Printed ✓' : printStatus === 'failed' ? 'Print failed' : 'Printing…'
  const printColor = printStatus === 'complete' ? t.success : printStatus === 'failed' ? t.danger : t.warning

  return (
    <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 20, padding: '40px 20px', textAlign: 'center' }}>
      <div style={{ width: 64, height: 64, borderRadius: '50%', background: t.successDim, border: `2px solid ${t.success}`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <svg width={28} height={28} viewBox="0 0 24 24" fill="none" stroke={t.success} strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </div>
      <div>
        <div style={{ fontSize: 20, fontWeight: 700, color: t.text, marginBottom: 4 }}>Item Saved</div>
        <div style={{ color: t.textMuted, fontSize: 14 }}>Jobs queued for worker</div>
      </div>

      <div style={{ background: t.surface2, border: `1px solid ${t.border}`, borderRadius: 12, padding: '16px 24px', width: '100%', display: 'flex', flexDirection: 'column', gap: 10 }}>
        {/* Barcode image */}
        {item.barcode_image && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, paddingBottom: 8, borderBottom: `1px solid ${t.border}` }}>
            <img
              src={`data:image/png;base64,${item.barcode_image}`}
              alt={item.barcode}
              style={{ maxWidth: '100%', height: 'auto', borderRadius: 4, background: '#fff', padding: '4px 8px' }}
            />
            <span style={{ color: t.textMuted, fontSize: 11, fontFamily: t.mono }}>{item.barcode}</span>
          </div>
        )}
        {/* Barcode string fallback when image unavailable */}
        {!item.barcode_image && (
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}>
            <span style={{ color: t.textMuted }}>Barcode</span>
            <span style={{ color: t.accent, fontWeight: 600, fontFamily: t.mono }}>{item.barcode}</span>
          </div>
        )}
        {/* Price */}
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}>
          <span style={{ color: t.textMuted }}>Price</span>
          <span style={{ color: t.text, fontWeight: 600 }}>{money(item.price)}</span>
        </div>
        {/* Print status */}
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}>
          <span style={{ color: t.textMuted }}>Label</span>
          <span style={{ color: printColor, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
            {printStatus === 'pending' || printStatus === 'processing' ? <Spinner size={12} /> : null}
            {printLabel}
          </span>
        </div>
        {/* CV type status */}
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}>
          <span style={{ color: t.textMuted }}>Type (CV)</span>
          <span style={{ color: cvStatus === 'complete' ? t.success : t.textMuted, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
            {cvStatus === 'pending' || cvStatus === 'processing' ? <Spinner size={12} /> : null}
            {cvStatus === 'complete' && cvType ? cvType : cvStatus === 'failed' ? 'CV failed' : 'analyzing…'}
          </span>
        </div>
      </div>

      <Btn variant="primary" onClick={onNext} full>Next Item →</Btn>
    </div>
  )
}

// ─── Bulk success screen ──────────────────────────────────────────────────────

function BulkSuccess({ result, onNext }: { result: BulkCreateResult; onNext: () => void }) {
  const t = useTheme()
  const [groupItems, setGroupItems] = useState(result.items)

  // Poll bulk group status every 2s until all print jobs complete
  useEffect(() => {
    if (!result.bulk_group_id) return
    let active = true
    const poll = async () => {
      try {
        const { data } = await api.get<CreateResult[]>(`/items/bulk/${result.bulk_group_id}`)
        if (active) setGroupItems(data as any)
      } catch { /* ignore */ }
    }
    const interval = setInterval(poll, 2000)
    return () => { active = false; clearInterval(interval) }
  }, [result.bulk_group_id])

  return (
    <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 16, padding: '24px 0' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ width: 48, height: 48, borderRadius: '50%', background: t.successDim, border: `2px solid ${t.success}`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          <svg width={22} height={22} viewBox="0 0 24 24" fill="none" stroke={t.success} strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        </div>
        <div>
          <div style={{ fontSize: 18, fontWeight: 700, color: t.text }}>{result.total} Items Created</div>
          <div style={{ fontSize: 13, color: t.textMuted }}>Printing {result.total} labels…</div>
        </div>
      </div>

      <div style={{ background: t.surface2, border: `1px solid ${t.border}`, borderRadius: 12, padding: '12px 0', maxHeight: 320, overflowY: 'auto' }}>
        {result.items.map((item, i) => (
          <div key={item.barcode} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 16px', borderBottom: i < result.items.length - 1 ? `1px solid ${t.border}` : 'none' }}>
            <span style={{ fontSize: 12, color: t.textMuted, minWidth: 20 }}>{i + 1}</span>
            <span style={{ fontFamily: t.mono, fontSize: 13, color: t.accent, flex: 1 }}>{item.barcode}</span>
            <span style={{ fontSize: 12, color: t.textMuted }}>{money(item.price)}</span>
          </div>
        ))}
      </div>

      <Btn variant="primary" onClick={onNext} full size="lg">Next Item →</Btn>
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function Intake() {
  const t = useTheme()
  const [stage, setStage] = useState<Stage>('camera')
  const [captureResult, setCaptureResult] = useState<CaptureResult | null>(null)
  const [form, setForm] = useState<ItemFormData>({ ...DEFAULT_FORM })
  const [lastItem, setLastItem] = useState<CreateResult | null>(null)
  const [lastBulk, setLastBulk] = useState<BulkCreateResult | null>(null)
  const [quantity, setQuantity] = useState(1)
  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState<CaptureMode>(() =>
    (localStorage.getItem(MODE_KEY) as CaptureMode) ?? 'auto'
  )

  const toggleMode = () => {
    const next: CaptureMode = mode === 'auto' ? 'rapid' : 'auto'
    setMode(next)
    localStorage.setItem(MODE_KEY, next)
  }

  const captureMutation = useMutation({
    mutationFn: async (blob: Blob) => {
      const fd = new FormData()
      fd.append('image', blob, 'capture.jpg')
      const { data } = await api.post<CaptureResult>('/items/capture', fd)
      return data
    },
    onSuccess: (data) => {
      setCaptureResult(data)
      setForm({
        temp_image_id: data.temp_image_id,
        category: 'tshirt',
        color: data.color ?? '',
        secondary_color: '',
        type: 'unknown',
        label: '', size: '', condition: 'good', price: '', notes: '',
      })
      setStage('confirm')
      setError(null)
    },
    onError: (err) => setError(apiErrorMessage(err)),
  })

  const createMutation = useMutation({
    mutationFn: async (formData: ItemFormData) => {
      const { data } = await api.post('/items/', {
        temp_image_id: formData.temp_image_id,
        category: formData.category,
        color: formData.color || null,
        secondary_color: formData.secondary_color || null,
        type: formData.type,
        label: formData.label || null,
        size: formData.size || null,
        condition: formData.condition,
        price: parseFloat(formData.price),
        notes: formData.notes || null,
        quantity,
      })
      return data
    },
    onSuccess: (data) => {
      if (quantity > 1 && data.bulk_group_id) {
        setLastBulk(data as BulkCreateResult)
      } else {
        setLastItem(data as CreateResult)
      }
      setStage('success')
      setError(null)
    },
    onError: (err) => setError(apiErrorMessage(err)),
  })

  const { videoRef, ready, error: cameraError, restart, capture } = useCamera()

  const handleCapture = useCallback(async () => {
    if (captureMutation.isPending) return
    setError(null)
    const blob = await capture()
    if (blob) captureMutation.mutate(blob)
  }, [capture, captureMutation])

  const handleReset = () => { setStage('camera'); setCaptureResult(null); setError(null) }
  const handleNext = () => {
    setStage('camera'); setCaptureResult(null); setLastItem(null); setLastBulk(null)
    setForm({ ...DEFAULT_FORM }); setQuantity(1); setError(null)
  }

  const stages = ['camera', 'confirm', 'success']

  return (
    <div style={{ maxWidth: 680, margin: '0 auto', padding: '24px 16px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <SectionHeader>Item Intake</SectionHeader>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {stages.map((s, i) => (
            <span key={s} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{
                width: 8, height: 8, borderRadius: '50%',
                background: stage === s ? t.accent : i < stages.indexOf(stage) ? t.success : t.border,
                transition: 'background 0.3s',
              }} />
              {i < 2 && <div style={{ width: 20, height: 1, background: t.border }} />}
            </span>
          ))}
          <span style={{ marginLeft: 8, fontSize: 11, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            {stage === 'camera' ? 'Capture' : stage === 'confirm' ? 'Confirm' : 'Done'}
          </span>
        </div>
      </div>

      <ErrorAlert message={error} onDismiss={() => setError(null)} />

      {stage === 'camera' && (
        <CameraPanel
          onCapture={handleCapture}
          capturing={captureMutation.isPending}
          videoRef={videoRef}
          ready={ready}
          error={cameraError}
          restart={restart}
          mode={mode}
          onModeToggle={toggleMode}
        />
      )}

      {stage === 'confirm' && captureResult && (
        <IntakeForm
          detectedColor={captureResult.color}
          form={form} setForm={setForm}
          onSubmit={() => createMutation.mutate(form)}
          onReset={handleReset}
          submitting={createMutation.isPending}
          quantity={quantity}
          setQuantity={setQuantity}
        />
      )}

      {stage === 'success' && lastBulk && (
        <BulkSuccess result={lastBulk} onNext={handleNext} />
      )}

      {stage === 'success' && lastItem && !lastBulk && (
        <IntakeSuccess item={lastItem} onNext={handleNext} />
      )}
    </div>
  )
}
