import SwiftUI
import Charts

/// Per-sub-category expense lines over time with an All / Under-$1k toggle
/// (web expenses "Expense Trendlines").
struct ExpenseTrendlinesChart: View {
    let series: [ExpenseCategorySeriesPoint]
    let topCategories: [ExpenseCategoryPoint]

    @State private var scale: Scale = .all
    /// Categories switched off via the legend. Persists across a scale change, so a
    /// category hidden under "All" stays hidden under "Under $1k".
    @State private var hidden: Set<String> = []

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

    /// Everything the scale filter admits — what the legend lists, including entries
    /// currently switched off (otherwise there'd be no way to switch them back on).
    private var scaleCategories: [String] {
        let all = allSeriesCategories
        guard scale == .under1k else { return all }
        return all.filter { cat in
            let maxVal = series.filter { $0.category == cat }.map { $0.amount.asDouble }.max() ?? 0
            return maxVal < 1000
        }
    }

    /// What the chart actually draws.
    private var categories: [String] {
        scaleCategories.filter { !hidden.contains($0) }
    }

    private var range: [Color] {
        categories.map { colorOf[$0] ?? .appTextTertiary }
    }

    /// One category's band in one period. `bottom` is the running total of everything
    /// stacked beneath it, `top` that total plus this category's own spend.
    private struct Point: Identifiable {
        let period: String
        let category: String
        let bottom: Double
        let top: Double
        var id: String { "\(period)|\(category)" }
    }

    /// Each category plotted at its cumulative height, so the lines stack: they never
    /// cross, the gap between neighbours is that category's spend, and the topmost line
    /// is total spend.
    ///
    /// The running total is computed here rather than via `stacking: .standard` because
    /// only `AreaMark`/`BarMark` accept that — `LineMark` has no stacking parameter.
    ///
    /// Two things this has to get right:
    /// 1. Zero-fill. The API only emits a row when a category had spend that period
    ///    (`dashboard.py`: `if amt > _ZERO`), so the series is sparse. Without filling,
    ///    a category missing one month drops everything above it in the stack and jumps
    ///    it back the next — which reads as lines weaving through each other.
    /// 2. A stable stack order across every period, so bands don't reshuffle month to
    ///    month. `categories` is ranked by overall spend and is the same for all x.
    private var stackedPoints: [Point] {
        let visible = categories
        var byKey = [String: Double]()
        for row in series where visible.contains(row.category) {
            byKey["\(row.periodLabel)|\(row.category)"] = row.amount.asDouble
        }
        return periodLabels.flatMap { period -> [Point] in
            var running = 0.0
            return visible.map { category in
                let bottom = running
                running += byKey["\(period)|\(category)"] ?? 0
                return Point(period: period, category: category, bottom: bottom, top: running)
            }
        }
    }

    /// Categorical string axes aren't thinned by `.automatic(desiredCount:)`, so with
    /// 6+ periods every label renders and gets clipped. Pick a subset up front instead.
    private var xAxisLabelValues: [String] {
        let labels = periodLabels
        guard labels.count > 4 else { return labels }
        let step = Int(ceil(Double(labels.count) / 4.0))
        return stride(from: 0, to: labels.count, by: step).map { labels[$0] }
    }

    /// Filled band, stroked top edge, and a dot at each vertex — the web chart's look.
    ///
    /// `.monotone` rather than `.catmullRom`: shape-preserving, so a band can't overshoot
    /// into the one below it. All three marks must use the same interpolation or the
    /// stroke will drift off the fill it belongs to.
    ///
    /// Extracted from the `Chart` builder — inline, the chained modifiers blow the
    /// type-checker's time budget.
    @ChartContentBuilder
    private func mark(for point: Point) -> some ChartContent {
        AreaMark(
            x: .value("Period", point.period),
            yStart: .value("From", point.bottom),
            yEnd: .value("To", point.top)
        )
        .foregroundStyle(by: .value("Category", point.category))
        .interpolationMethod(.monotone)
        .opacity(0.75)

        LineMark(
            x: .value("Period", point.period),
            y: .value("Amount", point.top)
        )
        .foregroundStyle(by: .value("Category", point.category))
        .interpolationMethod(.monotone)
        .lineStyle(StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))

        PointMark(
            x: .value("Period", point.period),
            y: .value("Amount", point.top)
        )
        .foregroundStyle(by: .value("Category", point.category))
        .symbolSize(36)
    }

    var body: some View {
        VStack(spacing: Space.md) {
            Picker("Scale", selection: $scale) {
                ForEach(Scale.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)

            Chart {
                ForEach(stackedPoints) { point in
                    mark(for: point)
                }
            }
            .chartForegroundStyleScale(domain: categories, range: range)
            .chartXAxis {
                AxisMarks(values: xAxisLabelValues) { value in
                    AxisGridLine()
                    AxisValueLabel {
                        if let label = value.as(String.self) {
                            // `.fixedSize()` or the label is clipped to its category
                            // slot's width ("Jan 20…").
                            Text(label).font(.caption2).fixedSize()
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
            .animation(.easeInOut(duration: 0.25), value: hidden)

            legend
        }
    }

    private static let legendColumns = [GridItem(.flexible(), alignment: .leading), GridItem(.flexible(), alignment: .leading)]

    /// Two-column grid of swatch + label entries, sized to fit long names like
    /// "Employee Benefits" without truncating. Tapping an entry shows or hides that
    /// category; since the chart is stacked, hiding one restacks the rest.
    ///
    /// Iterates `scaleCategories`, not `categories` — a hidden entry has to stay in the
    /// legend to be tappable again. Swatch colours come from `colorOf` rather than
    /// `range` for the same reason, and so a colour never shifts as siblings are toggled.
    private var legend: some View {
        LazyVGrid(columns: Self.legendColumns, alignment: .leading, spacing: 8) {
            ForEach(scaleCategories, id: \.self) { category in
                let isHidden = hidden.contains(category)
                Button {
                    withAnimation(.easeInOut(duration: 0.25)) {
                        if isHidden { hidden.remove(category) } else { hidden.insert(category) }
                    }
                } label: {
                    HStack(spacing: 8) {
                        RoundedRectangle(cornerRadius: 2)
                            .fill(isHidden ? Color.clear : (colorOf[category] ?? .appTextTertiary))
                            .frame(width: 10, height: 10)
                            .overlay(
                                RoundedRectangle(cornerRadius: 2)
                                    .strokeBorder(colorOf[category] ?? .appTextTertiary, lineWidth: 1.5)
                            )
                        Text(category)
                            .font(.caption)
                            .foregroundStyle(isHidden ? Color.appTextTertiary : Color.appTextSecondary)
                            .strikethrough(isHidden, color: Color.appTextTertiary)
                            .lineLimit(1)
                    }
                    .contentShape(Rectangle())
                    .opacity(isHidden ? 0.5 : 1)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(category)
                .accessibilityValue(isHidden ? "Hidden" : "Shown")
                .accessibilityHint("Double tap to \(isHidden ? "show" : "hide") this category")
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
