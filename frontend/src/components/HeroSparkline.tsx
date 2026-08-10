import Sparkline from './Sparkline'

interface Props {
  data: number[]
  labels?: string[]
}

/**
 * The Sparkline as it appears inside a dashboard `.hero` card.
 *
 * Hero cards paint their own dark gradient in both light and dark theme, so
 * these keep white strokes and axes rather than the theme text tokens the bare
 * Sparkline now defaults to. Four tabs previously repeated this exact prop
 * bundle verbatim.
 */
export default function HeroSparkline({ data, labels }: Props) {
  return (
    <Sparkline
      data={data}
      labels={labels}
      showAxes
      fillContainer
      color="white"
      fill="rgba(255,255,255,0.22)"
      strokeWidth={2.2}
      axisColor="rgba(255,255,255,0.55)"
      gridColor="rgba(255,255,255,0.12)"
    />
  )
}
