import { useEffect, useRef } from 'react'

interface SingleBar { label: string; value: number }
interface DualBar   { label: string; income: number; expenses: number }

interface Props {
  data: SingleBar[] | DualBar[]
  height?: number
  dual?: boolean
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  if (h < r * 2) r = h / 2
  if (h <= 0) return
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.lineTo(x + w - r, y)
  ctx.quadraticCurveTo(x + w, y, x + w, y + r)
  ctx.lineTo(x + w, y + h)
  ctx.lineTo(x, y + h)
  ctx.lineTo(x, y + r)
  ctx.quadraticCurveTo(x, y, x + r, y)
  ctx.closePath()
}

export default function BarChart({ data, height = 200, dual = false }: Props) {
  const ref = useRef<HTMLCanvasElement>(null)

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

    const padTop = 14, padBot = 24, padL = 36
    const innerW = w - padL - 8
    const innerH = h - padTop - padBot

    let max: number
    if (dual) {
      max = Math.max(...(data as DualBar[]).map(d => Math.max(d.income, d.expenses)))
    } else {
      max = Math.max(...(data as SingleBar[]).map(d => d.value))
    }
    max = Math.ceil(max / 2000) * 2000 || 1000
    const yScale = (v: number) => padTop + innerH - (v / max) * innerH

    const css = getComputedStyle(document.documentElement)
    const gridColor = css.getPropertyValue('--line').trim() || 'rgba(255,255,255,.06)'
    const text3 = css.getPropertyValue('--text-3').trim() || '#6a7a90'
    ctx.strokeStyle = gridColor
    ctx.fillStyle = text3
    ctx.font = '10px JetBrains Mono, monospace'
    ctx.lineWidth = 1
    for (let i = 0; i <= 4; i++) {
      const v = (max / 4) * i
      const y = yScale(v)
      ctx.beginPath()
      ctx.moveTo(padL, y)
      ctx.lineTo(w - 8, y)
      ctx.stroke()
      ctx.fillText(`$${(v / 1000).toFixed(0)}k`, 4, y + 3)
    }

    const groupW = innerW / data.length
    const accent = css.getPropertyValue('--accent').trim() || '#56c8f0'
    const green = css.getPropertyValue('--green').trim() || '#4ade80'
    const red = css.getPropertyValue('--red').trim() || '#fb7185'

    data.forEach((d, i) => {
      const cx = padL + groupW * i + groupW / 2
      if (dual) {
        const dd = d as DualBar
        const bw = Math.min(16, groupW / 2 - 4)
        const yi = yScale(dd.income)
        ctx.fillStyle = green
        roundRect(ctx, cx - bw - 2, yi, bw, padTop + innerH - yi, 3)
        ctx.fill()
        const ye = yScale(dd.expenses)
        ctx.fillStyle = red
        roundRect(ctx, cx + 2, ye, bw, padTop + innerH - ye, 3)
        ctx.fill()
      } else {
        const sd = d as SingleBar
        const bw = Math.min(28, groupW * 0.55)
        const y = yScale(sd.value)
        ctx.fillStyle = accent
        roundRect(ctx, cx - bw / 2, y, bw, padTop + innerH - y, 4)
        ctx.fill()
      }
      ctx.fillStyle = text3
      ctx.textAlign = 'center'
      ctx.fillText(d.label.slice(0, 3), cx, h - 8)
      ctx.textAlign = 'left'
    })
  }, [data, dual])

  return <canvas ref={ref} style={{ width: '100%', height, display: 'block' }} />
}
