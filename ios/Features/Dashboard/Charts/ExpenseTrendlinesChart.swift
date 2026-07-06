import SwiftUI
import Charts

/// Per-sub-category expense lines over time with an All / Under-$1k toggle
/// (web expenses "Expense Trendlines").
struct ExpenseTrendlinesChart: View {
    let series: [ExpenseCategorySeriesPoint]
    let topCategories: [ExpenseCategoryPoint]

    @State private var scale: Scale = .all

    enum Scale: String, CaseIterable, Identifiable {
        case all = "All"
        case under1k = "Under $1k"
        var id: String { rawValue }
    }

    private var periodLabels: [String] {
        var seen = Set<String>()
        return series.compactMap { seen.insert($0.periodLabel).inserted ? $0.periodLabel : nil }
    }

    private var allSeriesCategories: [String] {
        var seen = Set<String>()
        return series.compactMap { seen.insert($0.category).inserted ? $0.category : nil }
    }

    /// Stable category → colour map. `topCategories` (the Expense Mix donut's ranking)
    /// only covers its top N, but the trendline series can include additional
    /// lower-spend categories — those still need a colour, so assignment continues
    /// from a single running index rather than a separate offset that could wrap
    /// back onto an already-used slot.
    private var colorOf: [String: Color] {
        var m = [String: Color]()
        var nextIndex = 0
        for c in topCategories where m[c.category] == nil {
            m[c.category] = ChartPalette.expense[nextIndex % ChartPalette.expense.count]
            nextIndex += 1
        }
        for cat in allSeriesCategories where m[cat] == nil {
            m[cat] = ChartPalette.expense[nextIndex % ChartPalette.expense.count]
            nextIndex += 1
        }
        return m
    }

    private var categories: [String] {
        let all = allSeriesCategories
        guard scale == .under1k else { return all }
        return all.filter { cat in
            let maxVal = series.filter { $0.category == cat }.map { $0.amount.asDouble }.max() ?? 0
            return maxVal < 1000
        }
    }

    private var range: [Color] {
        categories.map { colorOf[$0] ?? .appTextTertiary }
    }

    /// Categorical string axes aren't thinned by `.automatic(desiredCount:)`, so with
    /// 6+ periods every label renders and gets clipped. Pick a subset up front instead.
    private var xAxisLabelValues: [String] {
        let labels = periodLabels
        guard labels.count > 4 else { return labels }
        let step = Int(ceil(Double(labels.count) / 4.0))
        return stride(from: 0, to: labels.count, by: step).map { labels[$0] }
    }

    var body: some View {
        VStack(spacing: Space.md) {
            Picker("Scale", selection: $scale) {
                ForEach(Scale.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)

            Chart {
                ForEach(Array(series.enumerated()), id: \.offset) { _, row in
                    if categories.contains(row.category) {
                        LineMark(
                            x: .value("Period", row.periodLabel),
                            y: .value("Amount", row.amount.asDouble)
                        )
                        .foregroundStyle(by: .value("Category", row.category))
                        .interpolationMethod(.catmullRom)
                        .lineStyle(StrokeStyle(lineWidth: 1.5))
                    }
                }
            }
            .chartForegroundStyleScale(domain: categories, range: range)
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
            .chartLegend(.hidden)
            .frame(height: 240)

            legend
        }
    }

    private static let legendColumns = [GridItem(.flexible(), alignment: .leading), GridItem(.flexible(), alignment: .leading)]

    /// Two-column grid of swatch + label entries, sized to fit long names like
    /// "Employee Benefits" without truncating.
    private var legend: some View {
        LazyVGrid(columns: Self.legendColumns, alignment: .leading, spacing: 8) {
            ForEach(Array(zip(categories, range)), id: \.0) { category, color in
                HStack(spacing: 8) {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(color)
                        .frame(width: 10, height: 10)
                    Text(category)
                        .font(.caption)
                        .foregroundStyle(Color.appTextSecondary)
                        .lineLimit(1)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
