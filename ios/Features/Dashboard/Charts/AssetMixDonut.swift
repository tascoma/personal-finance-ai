import SwiftUI
import Charts

struct AssetMixDonut: View {
    let composition: [AssetCompositionPoint]

    private var total: Decimal {
        composition.reduce(Decimal(0)) { $0 + $1.amount }
    }

    private static let palette: [Color] = [
        .appAccent,
        .appGreen,
        .appAmber,
        Color(hex: "a78bfa"),   // purple
        Color(hex: "38bdf8"),   // sky blue
        Color(hex: "fb923c"),   // orange
        Color(hex: "34d399"),   // emerald
        .appRed,
    ]

    var body: some View {
        VStack(spacing: 12) {
            Chart(composition) { item in
                SectorMark(
                    angle: .value("Amount", item.amount.asDouble),
                    innerRadius: .ratio(0.55),
                    angularInset: 1.5
                )
                .foregroundStyle(by: .value("Category", item.subCategory))
                .cornerRadius(2)
            }
            .chartForegroundStyleScale(
                domain: composition.map(\.subCategory),
                range: Array(Self.palette.prefix(composition.count))
            )
            .chartLegend(.hidden)
            .frame(height: 220)

            VStack(spacing: 6) {
                ForEach(Array(composition.enumerated()), id: \.offset) { idx, item in
                    HStack(spacing: 8) {
                        Circle()
                            .fill(Self.palette[idx % Self.palette.count])
                            .frame(width: 8, height: 8)
                        Text(item.subCategory)
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
        let pct = amount.asDouble / total.asDouble * 100
        return String(format: "%.0f%%", pct)
    }
}
