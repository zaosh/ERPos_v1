import { useEffect, useRef, useState } from 'react'
import { BrowserMultiFormatReader } from '@zxing/library'

interface Props {
  onScan: (barcode: string) => void
  active: boolean
}

export default function BarcodeScanner({ onScan, active }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const readerRef = useRef<BrowserMultiFormatReader | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!active) {
      readerRef.current?.reset()
      return
    }

    const reader = new BrowserMultiFormatReader()
    readerRef.current = reader

    reader
      .decodeFromVideoDevice(undefined, videoRef.current!, (result, err) => {
        if (result) {
          onScan(result.getText())
          reader.reset()
        }
        if (err && !(err.message?.includes('No MultiFormat'))) {
          // suppress continuous "no barcode found" errors
        }
      })
      .catch((e) => setError(e.message ?? 'Scanner error'))

    return () => {
      reader.reset()
    }
  }, [active, onScan])

  if (error) {
    return (
      <div className="text-red-600 text-sm text-center py-4">
        Scanner error: {error}
      </div>
    )
  }

  return (
    <div className="relative w-full aspect-video bg-black rounded-lg overflow-hidden">
      <video ref={videoRef} className="w-full h-full object-cover" muted />
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <div className="w-64 h-20 border-2 border-brand-400 rounded opacity-70" />
      </div>
      {!active && (
        <div className="absolute inset-0 bg-black/60 flex items-center justify-center text-white text-sm">
          Scanner paused
        </div>
      )}
    </div>
  )
}
