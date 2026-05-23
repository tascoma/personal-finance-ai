import SwiftUI
import Charts

struct ExpenseCategoryBar: View {
    let categories: [ExpenseCategoryPoint]

    var body: some View {
        Chart(categories) { item in
            BarMark(
                x: .value("Amount", item.amount.asDouble),
                y: .value("Category", item.category)
            )
            .foregroundStyle(color(for: item))
            .annotation(position: .trailing, alignment: .leading, spacing: 4) {
                Text(Money.compact(item.amount))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
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
                        Text(Money.compact(Decimal(n))).font(.caption2)
                    }
                }
            }
        }
        .frame(height: CGFloat(max(160, categories.count * 28 + 24)))
    }

    private func color(for item: ExpenseCategoryPoint) -> Color {
        let palette: [Color] = [.red, .orange, .blue, .green, .purple, .cyan, .pink, .mint]
        let idx = categories.firstIndex(of: item) ?? 0
        return palette[idx % palette.count]
    }
}
