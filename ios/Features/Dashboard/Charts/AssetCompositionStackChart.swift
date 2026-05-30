import SwiftUI
import Charts

/// Stacked bar of asset sub-categories per period (web assets "Composition Over Time").
struct AssetCompositionStackChart: View {
    let series: [AssetSeriesPoint]
    let composition: [AssetCompositionPoint]

    /// Sub-category → colour, keyed by the asset-composition order so the stacked
    /// bar agrees with the ring's colours.
    private var domain: [String] {
        var seen = Set<String>()
        var order = composition.map(\.subCategory)
        for c in order { seen.insert(c) }
        for row in series where !seen.contains(row.subCategory) {
            seen.insert(row.subCategory)
            order.append(row.subCategory)
        }
        return order.filter { sc in series.contains { $0.subCategory == sc } }
    }

    private var range: [Color] {
        domain.enumerated().map { ChartPalette.asset[$0.offset % ChartPalette.asset.count] }
    }

    var body: some View {
        Chart {
            ForEach(Array(series.enumerated()), id: \.offset) { _, row in
                BarMark(
                    x: .value("Period", row.periodLabel),
                    y: .value("Amount", row.amount.asDouble)
                )
                .foregroundStyle(by: .value("Type", row.subCategory))
            }
        }
        .chartForegroundStyleScale(domain: domain, range: range)
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
        .chartLegend(position: .bottom, alignment: .center, spacing: 8)
        .frame(height: 260)
    }
}
