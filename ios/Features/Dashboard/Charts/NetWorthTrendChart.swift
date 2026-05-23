import SwiftUI
import Charts

struct NetWorthTrendChart: View {
    let series: [NetWorthPoint]

    var body: some View {
        Chart {
            ForEach(series) { point in
                AreaMark(
                    x: .value("Period", point.periodLabel),
                    y: .value("Net Worth", point.netWorth.asDouble)
                )
                .interpolationMethod(.catmullRom)
                .foregroundStyle(
                    LinearGradient(
                        gradient: Gradient(stops: [
                            .init(color: Color.accentColor.opacity(0.35), location: 0),
                            .init(color: Color.accentColor.opacity(0), location: 1),
                        ]),
                        startPoint: .top, endPoint: .bottom
                    )
                )

                LineMark(
                    x: .value("Period", point.periodLabel),
                    y: .value("Net Worth", point.netWorth.asDouble)
                )
                .interpolationMethod(.catmullRom)
                .foregroundStyle(Color.accentColor)
                .lineStyle(StrokeStyle(lineWidth: 2))

                PointMark(
                    x: .value("Period", point.periodLabel),
                    y: .value("Net Worth", point.netWorth.asDouble)
                )
                .foregroundStyle(Color.accentColor)
                .symbolSize(40)
            }
        }
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
