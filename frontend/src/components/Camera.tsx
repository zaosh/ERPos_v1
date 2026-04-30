import { useRef } from 'react'
import { useCamera } from '../hooks/useCamera'

interface Props {
  onCapture: (blob: Blob) => void
  disabled?: boolean
}

export default function Camera({ onCapture, disabled }: Props) {
  const { videoRef, ready, error, capture, restart } = useCamera()
  const btnRef = useRef<HTMLButtonElement>(null)

  const handleCapture = async () => {
    const blob = await capture()
    if (blob) onCapture(blob)
  }

  return (
    <div className="flex flex-col items-center gap-3">
      {error ? (
        <div className="w-full aspect-video bg-red-50 border border-red-200 rounded-lg flex flex-col items-center justify-center gap-2 text-red-600">
          <p className="text-sm font-medium">Camera error: {error}</p>
          <button onClick={restart} className="text-xs underline">Try again</button>
        </div>
      ) : (
        <div className="relative w-full aspect-video bg-black rounded-lg overflow-hidden">
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className="w-full h-full object-cover"
          />
          {!ready && (
            <div className="absolute inset-0 flex items-center justify-center text-white text-sm">
              Starting camera…
            </div>
          )}
          <div className="absolute inset-0 border-2 border-brand-500 rounded-lg pointer-events-none opacity-40" />
        </div>
      )}
      <button
        ref={btnRef}
        onClick={handleCapture}
        disabled={!ready || disabled}
        className="w-full max-w-xs py-3 bg-brand-600 text-white rounded-full font-semibold text-lg shadow hover:bg-brand-700 disabled:opacity-40 transition-colors active:scale-95"
      >
        📸 Capture
      </button>
    </div>
  )
}
