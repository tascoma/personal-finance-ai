import SwiftUI
import Charts

struct ExpenseMixDonut: View {
    let categories: [ExpenseCategoryPoint]

    private var total: Decimal {
        categories.reduce(Decimal(0)) { $0 + $1.amount }
    }

    private static let palette: [Color] = [.red, .orange, .blue, .green, .purple, .cyan, .pink, .mint]

    var body: some View {
        VStack(spacing: 12) {
            Chart(categories) { item in
                SectorMark(
                    angle: .value("Amount", item.amount.asDouble),
                    innerRadius: .ratio(0.55),
                    angularInset: 1.5
                )
                .foregroundStyle(by: .value("Category", item.category))
                .cornerRadius(2)
            }
            .chartForegroundStyleScale(domain: categories.map(\.category), range: Array(Self.palette.prefix(categories.count)))
            .chartLegend(.hidden)
            .frame(height: 220)

            // Custom compact legend so phone-sized donuts get readable labels
            // alongside dollar amount and percent.
            VStack(spacing: 6) {
                ForEach(Array(categories.enumerated()), id: \.offset) { idx, item in
                    HStack(spacing: 8) {
                        Circle()
                            .fill(Self.palette[idx % Self.palette.count])
                            .frame(width: 8, height: 8)
                        Text(item.category)
                            .font(.caption)
                            .lineLimit(1)
                        Spacer()
                        Text(Money.format(item.amount))
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(.secondary)
                        Text(percent(item.amount))
                            .font(.caption.weight(.semibold))
                            .frame(width: 44, alignment: .trailing)
                    }
                }
            }
        }
    }

    private func percent(_ amount: Decimal) -> String {
        guard total > 0 else { return "—" }
        let pct = NSDecimalNumber(decimal: amount).doubleValue / NSDecimalNumber(decimal: total).doubleValue * 100
        return String(format: "%.0f%%", pct)
    }
}
