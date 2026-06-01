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

    /// Stable category → colour map, keyed by the top-categories order.
    private var colorOf: [String: Color] {
        var m = [String: Color]()
        for (i, c) in topCategories.enumerated() {
            m[c.category] = ChartPalette.expense[i % ChartPalette.expense.count]
        }
        return m
    }

    private var categories: [String] {
        var seen = Set<String>()
        let all = series.compactMap { seen.insert($0.category).inserted ? $0.category : nil }
        guard scale == .under1k else { return all }
        return all.filter { cat in
            let maxVal = series.filter { $0.category == cat }.map { $0.amount.asDouble }.max() ?? 0
            return maxVal < 1000
        }
    }

    private var range: [Color] {
        categories.enumerated().map { idx, cat in
            colorOf[cat] ?? ChartPalette.expense[(topCategories.count + idx) % ChartPalette.expense.count]
        }
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
            .chartLegend(position: .bottom, alignment: .center, spacing: 6)
            .frame(height: 240)
        }
    }
}
