import SwiftUI
import Charts

/// Stacked area of asset sub-categories per period (web assets "Composition Over Time").
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

    private var periodLabels: [String] {
        var seen = Set<String>()
        return series.compactMap { seen.insert($0.periodLabel).inserted ? $0.periodLabel : nil }
    }

    /// Categorical string axes aren't thinned by `.automatic(desiredCount:)`, so with
    /// 6+ periods every label renders and gets clipped. Pick a subset up front instead.
    private var xAxisLabelValues: [String] {
        let labels = periodLabels
        guard labels.count > 4 else { return labels }
        let step = Int(ceil(Double(labels.count) / 4.0))
        return stride(from: 0, to: labels.count, by: step).map { labels[$0] }
    }

    /// One sub-category's band in one period, `bottom` being everything stacked beneath.
    private struct Point: Identifiable {
        let period: String
        let subCategory: String
        let bottom: Double
        let top: Double
        var id: String { "\(period)|\(subCategory)" }
    }

    /// Cumulative band edges, zero-filled across every period.
    ///
    /// The API only emits a row when a sub-category has a non-zero balance
    /// (`dashboard.py`: `if amt > _ZERO`), so the series is sparse. Left sparse, a
    /// sub-category missing from one period drops everything above it in the stack
    /// and jumps it back the next, which reads as bands weaving through each other.
    /// `domain` is a fixed order, so the stack doesn't reshuffle between periods.
    private var stackedPoints: [Point] {
        let order = domain
        var byKey = [String: Double]()
        for row in series {
            byKey["\(row.periodLabel)|\(row.subCategory)"] = row.amount.asDouble
        }
        return periodLabels.flatMap { period -> [Point] in
            var running = 0.0
            return order.map { subCategory in
                let bottom = running
                running += byKey["\(period)|\(subCategory)"] ?? 0
                return Point(period: period, subCategory: subCategory, bottom: bottom, top: running)
            }
        }
    }

    /// Filled band, stroked top edge, and a dot at each vertex — the web chart's look.
    /// All three marks share `.monotone` so the stroke tracks the fill it belongs to.
    @ChartContentBuilder
    private func mark(for point: Point) -> some ChartContent {
        AreaMark(
            x: .value("Period", point.period),
            yStart: .value("From", point.bottom),
            yEnd: .value("To", point.top)
        )
        .foregroundStyle(by: .value("Type", point.subCategory))
        .interpolationMethod(.monotone)
        .opacity(0.75)

        LineMark(
            x: .value("Period", point.period),
            y: .value("Amount", point.top)
        )
        .foregroundStyle(by: .value("Type", point.subCategory))
        .interpolationMethod(.monotone)
        .lineStyle(StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))

        PointMark(
            x: .value("Period", point.period),
            y: .value("Amount", point.top)
        )
        .foregroundStyle(by: .value("Type", point.subCategory))
        .symbolSize(36)
    }

    var body: some View {
        Chart {
            ForEach(stackedPoints) { point in
                mark(for: point)
            }
        }
        .chartForegroundStyleScale(domain: domain, range: range)
        .chartXAxis {
            AxisMarks(values: xAxisLabelValues) { value in
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
