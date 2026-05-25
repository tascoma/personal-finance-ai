import SwiftUI
import Charts

struct AssetGrowthChart: View {
    let series: [AssetSeriesPoint]

    private struct PeriodTotal: Identifiable {
        let id: String
        let periodLabel: String
        let total: Double
    }

    private var periodTotals: [PeriodTotal] {
        var seen = [String: Double]()
        var order = [String]()
        for point in series {
            if seen[point.periodLabel] == nil { order.append(point.periodLabel) }
            seen[point.periodLabel, default: 0] += point.amount.asDouble
        }
        return order.map { PeriodTotal(id: $0, periodLabel: $0, total: seen[$0] ?? 0) }
    }

    private var yBounds: (min: Double, max: Double, bottom: Double) {
        let values = periodTotals.map(\.total)
        guard let minVal = values.min(), let maxVal = values.max(), minVal != maxVal else {
            return (0, 1, 0)
        }
        let padding = (maxVal - minVal) * 0.1
        return (minVal, maxVal, minVal - padding)
    }

    private var yDomain: ClosedRange<Double> {
        let b = yBounds
        let padding = (b.max - b.min) * 0.1
        return b.bottom...(b.max + padding)
    }

    var body: some View {
        let totals = periodTotals
        Chart {
            ForEach(totals) { point in
                AreaMark(
                    x: .value("Period", point.periodLabel),
                    yStart: .value("Base", yBounds.bottom),
                    yEnd: .value("Total Assets", point.total)
                )
                .interpolationMethod(.catmullRom)
                .foregroundStyle(
                    LinearGradient(
                        gradient: Gradient(stops: [
                            .init(color: Color.appAccent.opacity(0.35), location: 0),
                            .init(color: Color.appAccent.opacity(0), location: 1),
                        ]),
                        startPoint: .top, endPoint: .bottom
                    )
                )

                LineMark(
                    x: .value("Period", point.periodLabel),
                    y: .value("Total Assets", point.total)
                )
                .interpolationMethod(.catmullRom)
                .foregroundStyle(Color.appAccent)
                .lineStyle(StrokeStyle(lineWidth: 2))

                PointMark(
                    x: .value("Period", point.periodLabel),
                    y: .value("Total Assets", point.total)
                )
                .foregroundStyle(Color.appAccent)
                .symbolSize(40)
            }
        }
        .chartYScale(domain: yDomain)
        .chartXAxis {
            AxisMarks(values: .automatic(desiredCount: 4)) { value in
                AxisGridLine()
                AxisValueLabel {
                    if let label = value.as(String.self) {
                        Text(label).font(.caption2)
                    }
                }
            }
        }
        .chartYAxis {
            AxisMarks(position: .leading) { value in
                AxisGridLine()
                AxisValueLabel {
                    if let n = value.as(Double.self) {
                        Text(Money.compact(Decimal(n))).font(.caption2)
                    }
                }
            }
        }
        .frame(height: 200)
    }
}
