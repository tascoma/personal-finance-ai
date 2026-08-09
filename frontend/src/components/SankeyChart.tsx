import { fmtMoney } from '../utils/format'
import type { SankeyModel, SankeyNode } from '../pages/dashboard/sankeyData'

const NODE_W = 14
const GAP = 12
// Wide enough for the longest label plus its amount on one line — "Equity / RSU
// $38,000.00" is the tightest case at ~190px.
const PAD_L = 200
const PAD_R = 190
const PAD_Y = 22
/** Below this height a node has no room for its amount alongside the label. */
const VALUE_MIN_H = 13
/**
 * Below this height a node gets no label at all. This is what keeps labels from
 * colliding — a rounding-artifact node (a folded remainder of a few dollars)
 * still draws its ribbon and reports its value on hover, but stays silent rather
 * than crowding its neighbour. With it, no collision solver is needed.
 */
const LABEL_MIN_H = 9
const LABEL_MAX = 22
/** A hub caption needs this much clear space above its node, or it's dropped. */
const CAPTION_ROOM = 20

interface Props {
  model: SankeyModel
  width?: number
  height?: number
}

interface Placed extends SankeyNode {
  x: number
  y: number
  h: number
  hasIn: boolean
  hasOut: boolean
}

const truncate = (s: string) => (s.length > LABEL_MAX ? `${s.slice(0, LABEL_MAX - 1)}…` : s)

function ribbon(x0: number, x1: number, sy: number, ty: number, h: number): string {
  const xm = (x0 + x1) / 2
  return (
    `M${x0},${sy} C${xm},${sy} ${xm},${ty} ${x1},${ty} ` +
    `L${x1},${ty + h} C${xm},${ty + h} ${xm},${sy + h} ${x0},${sy + h} Z`
  )
}

export default function SankeyChart({ model, width = 940, height = 480 }: Props) {
  const { nodes, links, total } = model
  if (!nodes.length || total <= 0) return null

  // Columns present, left to right. Any integer column index is allowed.
  const columnIds = [...new Set(nodes.map((n) => n.column))].sort((a, b) => a - b)
  const byColumn = new Map(columnIds.map((c) => [c, nodes.filter((n) => n.column === c)]))
  const colSum = (col: SankeyNode[]) => col.reduce((s, n) => s + n.value, 0)

  const usable = height - 2 * PAD_Y
  // One scale across every column: the tightest column (most pixels once its gaps
  // are spent) sets it, so no column can overflow and ribbons meet nodes exactly.
  const scale = Math.min(
    ...columnIds.map((c) => {
      const col = byColumn.get(c)!
      return (usable - (col.length - 1) * GAP) / colSum(col)
    }),
  )

  const span = width - PAD_L - PAD_R - NODE_W
  const xOf = (c: number) => {
    const i = columnIds.indexOf(c)
    return columnIds.length === 1 ? PAD_L : PAD_L + span * (i / (columnIds.length - 1))
  }

  const hasIn = new Set(links.map((l) => l.target))
  const hasOut = new Set(links.map((l) => l.source))

  const placed = new Map<string, Placed>()
  for (const c of columnIds) {
    const col = byColumn.get(c)!
    const colH = colSum(col) * scale + (col.length - 1) * GAP
    let y = PAD_Y + (usable - colH) / 2
    for (const n of col) {
      const h = n.value * scale
      placed.set(n.id, { ...n, x: xOf(c), y, h, hasIn: hasIn.has(n.id), hasOut: hasOut.has(n.id) })
      y += h + GAP
    }
  }

  const centerOf = (id: string) => {
    const p = placed.get(id)!
    return p.y + p.h / 2
  }

  // Ribbon endpoints tile each node's rect. Source offsets and target offsets are
  // computed independently: a node's outgoing ribbons stack by target height, its
  // incoming ribbons by source height, so crossings stay local.
  const sy = new Array<number>(links.length)
  const ty = new Array<number>(links.length)
  const order = (key: 'source' | 'target', by: 'source' | 'target', out: number[]) => {
    const groups = new Map<string, number[]>()
    links.forEach((l, i) => {
      const g = groups.get(l[key]) ?? []
      g.push(i)
      groups.set(l[key], g)
    })
    for (const [nodeId, idxs] of groups) {
      let y = placed.get(nodeId)!.y
      idxs.sort((a, b) => centerOf(links[a][by]) - centerOf(links[b][by]))
      for (const i of idxs) {
        out[i] = y
        y += links[i].value * scale
      }
    }
  }
  order('source', 'target', sy)
  order('target', 'source', ty)

  const paths = links.map((l, i) => {
    const from = placed.get(l.source)!
    const to = placed.get(l.target)!
    return {
      key: `${l.source}->${l.target}:${i}`,
      d: ribbon(from.x + NODE_W, to.x, sy[i], ty[i], l.value * scale),
      color: l.color,
      title: `${from.label} → ${to.label}: ${fmtMoney(l.value)}`,
    }
  })

  const sideLabel = (n: Placed) => {
    // Sources label left, sinks label right. (Hubs get a caption instead.)
    const left = !n.hasIn
    const x = left ? n.x - 8 : n.x + NODE_W + 8
    return (
      <text
        key={`t:${n.id}`}
        x={x}
        y={n.y + n.h / 2}
        textAnchor={left ? 'end' : 'start'}
        dominantBaseline="middle"
        fontSize={11.5}
        fill="var(--text-2)"
      >
        {truncate(n.label)}
        {n.h >= VALUE_MIN_H && <tspan dx="6" fill="var(--text-3)">{fmtMoney(n.value)}</tspan>}
      </text>
    )
  }

  const leaves = [...placed.values()].filter((n) => (!n.hasIn || !n.hasOut) && n.h >= LABEL_MIN_H)
  const hubs = [...placed.values()].filter((n) => n.hasIn && n.hasOut && n.y >= CAPTION_ROOM)

  return (
    <svg
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label={`Money flow: ${fmtMoney(total)} of income across expenses and investments`}
    >
      <defs>
        {/* Secondary encoding on drawdown marks: green and red are a known
            deuteranope collision, so cash drawn down is hatched as well as red. */}
        <pattern id="sankey-hatch" width={5} height={5} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1={0} y1={0} x2={0} y2={5} stroke="var(--bg-1)" strokeWidth={2} opacity={0.65} />
        </pattern>
      </defs>

      {paths.map((p) => (
        <g key={p.key} className="sankey-flow">
          <title>{p.title}</title>
          <path d={p.d} fill={p.color} fillOpacity={0.3} />
        </g>
      ))}

      {[...placed.values()].map((n) => (
        <g key={n.id} className="sankey-node">
          <title>{`${n.label}: ${fmtMoney(n.value)}`}</title>
          <rect
            data-node={n.id}
            x={n.x}
            y={n.y}
            width={NODE_W}
            height={n.h}
            rx={2}
            fill={n.color}
            stroke="var(--bg-1)"
            strokeWidth={1}
          />
          {n.hatched && (
            <rect
              x={n.x}
              y={n.y}
              width={NODE_W}
              height={n.h}
              rx={2}
              fill="url(#sankey-hatch)"
              pointerEvents="none"
            />
          )}
        </g>
      ))}

      {leaves.map(sideLabel)}

      {/* Hub captions sit above the spine nodes (Total Income / Take Home). */}
      {hubs.map((n) => (
        <g key={`c:${n.id}`}>
          <text
            x={n.x + NODE_W / 2}
            y={n.y - 12}
            textAnchor="middle"
            fontSize={10}
            fill="var(--text-3)"
            letterSpacing="0.06em"
          >
            {n.label.toUpperCase()}
          </text>
          <text
            x={n.x + NODE_W / 2}
            y={n.y - 1}
            textAnchor="middle"
            fontSize={12}
            fontWeight={600}
            fill="var(--text)"
          >
            {fmtMoney(n.value)}
          </text>
        </g>
      ))}
    </svg>
  )
}
