import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

interface Props {
  data: number[]
  labels?: string[]
  color?: string
  fill?: string
  height?: number
  fillContainer?: boolean
  strokeWidth?: number
  showAxes?: boolean
  axisColor?: string
}

interface TooltipState {
  screenX: number
  screenY: number
  value: number
  label?: string
}

function fmtYTick(v: number): string {
  const abs = Math.abs(v)
  if (abs >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`
  if (abs >= 1_000) return `$${(v / 1_000).toFixed(0)}k`
  return `$${v.toFixed(0)}`
}

function fmtTooltipValue(v: number): string {
  return `$${v.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}

export default function Sparkline({
  data,
  labels,
  color = 'currentColor',
  fill,
  height = 36,
  fillContainer = false,
  strokeWidth = 1.8,
  showAxes = false,
  axisColor = 'rgba(255,255,255,0.55)',
}: Props) {
  const ref = useRef<HTMLCanvasElement>(null)
  const [tooltip, setTooltip] = useState<TooltipState | null>(null)

  useEffect(() => {
    const cvs = ref.current
    if (!cvs || !data.length) return
    const dpr = window.devicePixelRatio || 1
    const w = cvs.clientWidth
    const h = cvs.clientHeight
    cvs.width = w * dpr
    cvs.height = h * dpr
    const ctx = cvs.getContext('2d')
    if (!ctx) return
    ctx.scale(dpr, dpr)
    ctx.clearRect(0, 0, w, h)

    const padL = showAxes ? 52 : 0
    const padR = showAxes ? 8 : 0
    const padT = showAxes ? 16 : 0
    const padB = showAxes ? 24 : 0
    const plotW = w - padL - padR
    const plotH = h - padT - padB

    const min = Math.min(...data)
    const max = Math.max(...data)
    const range = max - min || 1

    const px = (i: number) => padL + (i / Math.max(data.length - 1, 1)) * plotW
    const py = (v: number) => padT + plotH - ((v - min) / range) * plotH

    if (showAxes) {
      ctx.font = `10px Inter, sans-serif`

      const yTicks = 4
      for (let i = 0; i <= yTicks; i++) {
        const v = min + (range / yTicks) * i
        const y = py(v)

        ctx.beginPath()
        ctx.strokeStyle = axisColor.replace(/[\d.]+\)$/, '0.12)')
        ctx.lineWidth = 0.75
        ctx.setLineDash([3, 4])
        ctx.moveTo(padL, y)
        ctx.lineTo(w - padR, y)
        ctx.stroke()
        ctx.setLineDash([])

        ctx.fillStyle = axisColor
        ctx.textAlign = 'right'
        ctx.textBaseline = 'middle'
        ctx.fillText(fmtYTick(v), padL - 5, y)
      }

      if (labels?.length) {
        ctx.textAlign = 'center'
        ctx.textBaseline = 'alphabetic'
        const maxLabels = Math.max(2, Math.floor(plotW / 56))
        const step = Math.ceil(labels.length / maxLabels)
        const shown = new Set<number>()
        for (let i = 0; i < labels.length; i += step) shown.add(i)
        shown.add(labels.length - 1)
        for (const i of shown) {
          ctx.fillStyle = axisColor
          ctx.textAlign = i === 0 ? 'left' : i === labels.length - 1 ? 'right' : 'center'
          ctx.fillText(labels[i], px(i), h - 5)
        }
      }
    }

    if (fill) {
      ctx.beginPath()
      ctx.moveTo(padL, padT + plotH)
      ctx.lineTo(px(0), py(data[0]))
      for (let i = 1; i < data.length; i++) ctx.lineTo(px(i), py(data[i]))
      ctx.lineTo(px(data.length - 1), padT + plotH)
      ctx.closePath()
      ctx.fillStyle = fill
      ctx.fill()
    }

    ctx.beginPath()
    ctx.moveTo(px(0), py(data[0]))
    for (let i = 1; i < data.length; i++) ctx.lineTo(px(i), py(data[i]))
    ctx.lineWidth = strokeWidth
    ctx.strokeStyle = color
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    ctx.stroke()

    for (let i = 0; i < data.length; i++) {
      ctx.beginPath()
      ctx.arc(px(i), py(data[i]), 3.5, 0, Math.PI * 2)
      ctx.fillStyle = color
      ctx.fill()
    }
  }, [data, labels, color, fill, strokeWidth, showAxes, axisColor])

  function handleMouseMove(e: React.MouseEvent<HTMLCanvasElement>) {
    const cvs = ref.current
    if (!cvs || !data.length) return
    const rect = cvs.getBoundingClientRect()
    const mouseX = e.clientX - rect.left

    const w = rect.width
    const h = rect.height
    const padL = showAxes ? 52 : 0
    const padR = showAxes ? 8 : 0
    const padT = showAxes ? 16 : 0
    const padB = showAxes ? 24 : 0
    const plotW = w - padL - padR
    const plotH = h - padT - padB

    const min = Math.min(...data)
    const max = Math.max(...data)
    const range = max - min || 1

    const px = (i: number) => padL + (i / Math.max(data.length - 1, 1)) * plotW
    const py = (v: number) => padT + plotH - ((v - min) / range) * plotH

    let closest = 0
    let closestDist = Infinity
    for (let i = 0; i < data.length; i++) {
      const dx = Math.abs(px(i) - mouseX)
      if (dx < closestDist) { closestDist = dx; closest = i }
    }

    const threshold = Math.max(20, plotW / data.length / 2)
    if (closestDist <= threshold) {
      setTooltip({
        screenX: rect.left + px(closest),
        screenY: rect.top + py(data[closest]),
        value: data[closest],
        label: labels?.[closest],
      })
    } else {
      setTooltip(null)
    }
  }

  const canvasStyle: React.CSSProperties = fillContainer
    ? { width: '100%', flex: 1, display: 'block', minHeight: 0 }
    : { width: '100%', height, display: 'block' }

  return (
    <div style={{ position: 'relative', ...(fillContainer ? { flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 } : {}) }}>
      <canvas ref={ref} style={canvasStyle} onMouseMove={handleMouseMove} onMouseLeave={() => setTooltip(null)} />
      {tooltip && createPortal(
        <div style={{
          position: 'fixed',
          left: tooltip.screenX,
          top: tooltip.screenY,
          transform: 'translate(-50%, calc(-100% - 10px))',
          background: 'rgba(10,18,35,0.88)',
          color: '#fff',
          borderRadius: 7,
          padding: '5px 10px',
          fontSize: 12,
          fontWeight: 600,
          whiteSpace: 'nowrap',
          pointerEvents: 'none',
          boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
          backdropFilter: 'blur(6px)',
          zIndex: 9999,
        }}>
          {tooltip.label && (
            <div style={{ fontSize: 10, fontWeight: 500, opacity: 0.65, marginBottom: 2 }}>{tooltip.label}</div>
          )}
          {fmtTooltipValue(tooltip.value)}
        </div>,
        document.body
      )}
    </div>
  )
}
