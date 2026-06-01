import SwiftUI
import Charts

/// Each top expense category as a percentage of salary + bonus
/// (web expenses "Category Spend vs Compensation").
struct CategoryVsCompChart: View {
    let categories: [ExpenseCategoryPoint]
    let compensation: Decimal

    private var comp: Double { compensation.asDouble }

    var body: some View {
        // Horizontal bars: long category names sit on the y-axis (one per row)
        // so they never overlap the way a crowded x-axis does on a phone.
        Chart {
            ForEach(Array(categories.enumerated()), id: \.offset) { idx, c in
                let pct = comp > 0 ? c.amount.asDouble / comp * 100 : 0
                BarMark(
                    x: .value("Percent", pct),
                    y: .value("Category", c.category)
                )
                .foregroundStyle(ChartPalette.expense[idx % ChartPalette.expense.count])
                .cornerRadius(3)
                .annotation(position: .trailing, alignment: .leading, spacing: 4) {
                    Text(String(format: "%.1f%%", pct))
                        .font(.caption2)
                        .foregroundStyle(Color.appTextTertiary)
                }
            }
        }
        .chartYAxis {
            AxisMarks(position: .leading) { value in
                AxisValueLabel {
                    if let label = value.as(String.self) {
                        Text(label).font(.caption2).lineLimit(1)
                    }
                }
            }
        }
        .chartXAxis {
            AxisMarks { value in
                AxisGridLine()
                AxisValueLabel {
                    if let n = value.as(Double.self) {
                        Text(String(format: "%.0f%%", n)).font(.caption2)
                    }
                }
            }
        }
        .frame(height: CGFloat(max(160, categories.count * 30 + 24)))
    }
}
