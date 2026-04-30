import { useEffect, useRef, useState, useCallback } from 'react'

export function useCamera() {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [stream, setStream] = useState<MediaStream | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [ready, setReady] = useState(false)

  const start = useCallback(async () => {
    try {
      setError(null)
      const mediaStream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'environment' },
      })
      setStream(mediaStream)
      if (videoRef.current) {
        videoRef.current.srcObject = mediaStream
        videoRef.current.onloadedmetadata = () => setReady(true)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Camera access denied')
    }
  }, [])

  const stop = useCallback(() => {
    stream?.getTracks().forEach((t) => t.stop())
    setStream(null)
    setReady(false)
  }, [stream])

  const capture = useCallback((): Promise<Blob | null> => {
    return new Promise((resolve) => {
      const video = videoRef.current
      if (!video || !ready) return resolve(null)
      const canvas = document.createElement('canvas')
      canvas.width = video.videoWidth
      canvas.height = video.videoHeight
      const ctx = canvas.getContext('2d')
      if (!ctx) return resolve(null)
      ctx.drawImage(video, 0, 0)
      canvas.toBlob((b) => resolve(b), 'image/jpeg', 0.92)
    })
  }, [ready])

  useEffect(() => {
    start()
    return () => stop()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return { videoRef, ready, error, capture, restart: start }
}
