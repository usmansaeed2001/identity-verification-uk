import { useEffect, useMemo, useRef, useState } from 'react'

import { canvasToJpeg } from '../lib/image'
import { Alert, Button, cx } from './ui'

const PROMPTS = ['Look straight at the camera', 'Slowly turn your head to the left', 'Now turn your head to the right']
const COUNTDOWN_SECONDS = 3
const MAX_SIDE = 1280

type Phase = 'idle' | 'starting' | 'scanning' | 'review'

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

function cameraError(error: unknown): string {
  if (!window.isSecureContext) return 'The camera only works on a secure (https) page. Open the link you were sent.'
  const name = error instanceof DOMException ? error.name : ''
  if (name === 'NotAllowedError') return 'Allow camera access in your browser settings, then try again.'
  if (name === 'NotFoundError' || name === 'OverconstrainedError') return "We couldn't find a front camera on this device."
  if (name === 'NotReadableError') return 'Another app is using the camera. Close it and try again.'
  return "We couldn't start the camera. Try again, or use another device."
}

/** Live face scan: three prompted frames from the front camera. No uploads from the gallery. */
export function FaceScan({ onComplete, busy }: { onComplete: (frames: Blob[]) => void; busy?: boolean }) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const cancelled = useRef(false)
  const [phase, setPhase] = useState<Phase>('idle')
  const [prompt, setPrompt] = useState(0)
  const [countdown, setCountdown] = useState(0)
  const [flash, setFlash] = useState(false)
  const [frames, setFrames] = useState<Blob[]>([])
  const previews = useMemo(() => frames.map((f) => URL.createObjectURL(f)), [frames])
  const [error, setError] = useState<string>()

  const stopCamera = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
  }

  useEffect(() => {
    cancelled.current = false
    return () => {
      cancelled.current = true
      stopCamera()
    }
  }, [])

  useEffect(() => () => previews.forEach((u) => URL.revokeObjectURL(u)), [previews])

  async function capture(video: HTMLVideoElement): Promise<Blob> {
    const scale = Math.min(1, MAX_SIDE / Math.max(video.videoWidth, video.videoHeight))
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(video.videoWidth * scale)
    canvas.height = Math.round(video.videoHeight * scale)
    canvas.getContext('2d')!.drawImage(video, 0, 0, canvas.width, canvas.height)
    return canvasToJpeg(canvas, 0.9)
  }

  async function start() {
    setError(undefined)
    setFrames([])
    if (!navigator.mediaDevices?.getUserMedia) {
      setError(cameraError(null))
      return
    }
    setPhase('starting')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 960 } },
        audio: false,
      })
      streamRef.current = stream
      const video = videoRef.current!
      video.srcObject = stream
      await video.play()
      setPhase('scanning')

      const captured: Blob[] = []
      for (let i = 0; i < PROMPTS.length; i++) {
        setPrompt(i)
        for (let c = COUNTDOWN_SECONDS; c > 0; c--) {
          setCountdown(c)
          await sleep(1000)
          if (cancelled.current) return
        }
        captured.push(await capture(video))
        setFlash(true)
        await sleep(250)
        setFlash(false)
      }
      stopCamera()
      setFrames(captured)
      setPhase('review')
    } catch (err) {
      stopCamera()
      setError(cameraError(err))
      setPhase('idle')
    }
  }

  const live = phase === 'starting' || phase === 'scanning'
  return (
    <div className="space-y-4">
      <div className={cx('relative mx-auto aspect-[3/4] w-full max-w-sm overflow-hidden rounded-2xl bg-slate-900', !live && 'hidden')}>
        <video ref={videoRef} playsInline muted className="h-full w-full -scale-x-100 object-cover" />
        <svg viewBox="0 0 300 400" className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden="true">
          <defs>
            <mask id="face-hole">
              <rect width="300" height="400" fill="white" />
              <ellipse cx="150" cy="185" rx="95" ry="125" fill="black" />
            </mask>
          </defs>
          <rect width="300" height="400" fill="rgb(15 23 42 / 0.55)" mask="url(#face-hole)" />
          <ellipse
            cx="150"
            cy="185"
            rx="95"
            ry="125"
            fill="none"
            stroke={flash ? '#34d399' : 'white'}
            strokeWidth="4"
            strokeDasharray={flash ? undefined : '10 8'}
          />
        </svg>
        {phase === 'scanning' && (
          <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-slate-950/90 to-transparent p-4 pt-10 text-center text-white">
            <p aria-live="assertive" className="text-lg font-semibold">
              {PROMPTS[prompt]}
            </p>
            <p className="mt-1 text-3xl font-bold tabular-nums" aria-hidden="true">
              {countdown}
            </p>
            <p className="mt-1 text-xs text-slate-300">
              Photo {prompt + 1} of {PROMPTS.length}
            </p>
          </div>
        )}
      </div>

      {phase === 'idle' && (
        <>
          <ul className="space-y-2 text-sm text-slate-700">
            <li>• Find good light and take off glasses, hats or masks.</li>
            <li>• Hold your phone at eye level and fit your face in the oval.</li>
            <li>• We'll take 3 photos while you follow the prompts.</li>
          </ul>
          {error && <Alert tone="error">{error}</Alert>}
          <Button block onClick={start}>
            Start face scan
          </Button>
        </>
      )}

      {phase === 'review' && (
        <>
          <div className="grid grid-cols-3 gap-2">
            {previews.map((src, i) => (
              <img key={src} src={src} alt={`Face scan photo ${i + 1}`} className="aspect-[3/4] w-full -scale-x-100 rounded-xl object-cover" />
            ))}
          </div>
          <p className="text-sm text-slate-700">Is your face clear and in focus in each photo?</p>
          <div className="flex flex-col gap-2 sm:flex-row-reverse">
            <Button block loading={busy} onClick={() => onComplete(frames)}>
              Use these photos
            </Button>
            <Button block variant="secondary" disabled={busy} onClick={start}>
              Scan again
            </Button>
          </div>
        </>
      )}
    </div>
  )
}
