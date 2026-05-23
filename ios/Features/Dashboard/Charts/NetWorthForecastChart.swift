import SwiftUI
import Charts

struct NetWorthForecastChart: View {
    let forecast: Forecast

    /// Chronologically-ordered, deduped X-axis labels — used to thin out tick marks
    /// so a 13-month series doesn't overlap on a phone-sized chart.
    private var orderedLabels: [String] {
        var seen = Set<String>()
        return forecast.points.compactMap { point in
            seen.insert(point.label).inserted ? point.label : nil
        }
    }

    private var visibleLabels: [String] {
        let labels = orderedLabels
        let stride = max(1, labels.count / 4)
        return labels.enumerated().compactMap { idx, label in
            idx % stride == 0 || idx == labels.count - 1 ? label : nil
        }
    }

    var body: some View {
        Chart(forecast.points) { point in
            if let value = point.value {
                LineMark(
                    x: .value("Period", point.label),
                    y: .value("Net Worth", value)
                )
                .foregroundStyle(by: .value("Series", point.series.rawValue))
                .lineStyle(strokeStyle(for: point.series))
                .interpolationMethod(.monotone)
            }
        }
        .chartForegroundStyleScale([
            Forecast.Series.historical.rawValue: Color.accentColor,
            Forecast.Series.trailing.rawValue: forecast.avgMonthlyNet >= 0 ? Color.green : Color.red,
            Forecast.Series.regression.rawValue: Color.gray,
        ])
        .chartXAxis {
            AxisMarks(values: visibleLabels) { value in
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
        .chartLegend(position: .bottom, alignment: .center, spacing: 8)
        .frame(height: 260)
    }

    private func strokeStyle(for series: Forecast.Series) -> StrokeStyle {
        switch series {
        case .historical:
            return StrokeStyle(lineWidth: 2)
        case .trailing:
            return StrokeStyle(lineWidth: 2, dash: [6, 4])
        case .regression:
            return StrokeStyle(lineWidth: 1.5, dash: [3, 4])
        }
    }
}
