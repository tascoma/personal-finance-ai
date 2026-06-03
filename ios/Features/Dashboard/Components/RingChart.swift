import SwiftUI
import Charts

/// Shared categorical palettes, mirroring the colour orders used in
/// frontend/src/pages/DashboardPage.tsx so iOS and web pick the same hues.
enum ChartPalette {
    static let asset: [Color] = [
        .appAccent, .appGreen, .appAmber, .appPurple,
        Color(hex: "38bdf8"), Color(hex: "f472b6"), Color(hex: "fb923c"), Color(hex: "34d399"),
    ]
    static let expense: [Color] = [
        .appRed, .appAmber, .appAccent, .appGreen,
        .appPurple, Color(hex: "f472b6"), Color(hex: "38bdf8"), Color(hex: "fb923c"),
    ]
}

struct RingSegment: Identifiable {
    let id = UUID()
    let name: String
    let amount: Double
    let color: Color
}

/// Donut with a value/label in the centre and an optional amber goal tick —
/// the native equivalent of the web `RingChart` component.
struct RingChart: View {
    let segments: [RingSegment]
    var size: CGFloat = 184
    var ratio: CGFloat = 0.68
    let centerValue: String
    var centerLabel: String = ""
    var goalPct: Double? = nil

    var body: some View {
        let bandCenterR = size / 2 * (1 + ratio) / 2
        let band = size / 2 * (1 - ratio)

        ZStack {
            Chart(segments) { seg in
                SectorMark(
                    angle: .value("Amount", max(seg.amount, 0)),
                    innerRadius: .ratio(ratio),
                    angularInset: 1.5
                )
                .foregroundStyle(seg.color)
                .cornerRadius(2)
            }
            .chartLegend(.hidden)
            .frame(width: size, height: size)

            if let goalPct {
                Capsule()
                    .fill(Color.appAmber)
                    .frame(width: 3, height: band + 8)
                    .offset(y: -bandCenterR)
                    .rotationEffect(.degrees(goalPct / 100 * 360))
            }

            VStack(spacing: 3) {
                Text(centerValue)
                    .font(.title3.weight(.semibold).monospacedDigit())
                    .foregroundStyle(Color.appTextPrimary)
                    .minimumScaleFactor(0.6)
                    .lineLimit(1)
                if !centerLabel.isEmpty {
                    Text(centerLabel).eyebrow()
                }
            }
            .frame(width: size * ratio * 0.9)
        }
        .frame(width: size, height: size)
        .frame(maxWidth: .infinity)
    }
}

/// Donut over a swatch/name/amount/percent legend — the phone-friendly stack of
/// the web's side-by-side `.ring-wrap`.
struct RingWithLegend: View {
    let segments: [RingSegment]
    let centerValue: String
    var centerLabel: String = "Total"
    var goalPct: Double? = nil

    private var total: Double { segments.reduce(0) { $0 + $1.amount } }

    var body: some View {
        VStack(spacing: Space.lg) {
            RingChart(segments: segments, centerValue: centerValue, centerLabel: centerLabel, goalPct: goalPct)

            VStack(spacing: 6) {
                ForEach(segments) { seg in
                    HStack(spacing: 8) {
                        RoundedRectangle(cornerRadius: 2)
                            .fill(seg.color)
                            .frame(width: 10, height: 10)
                        Text(seg.name)
                            .font(.caption)
                            .foregroundStyle(Color.appTextSecondary)
                            .lineLimit(1)
                        Spacer()
                        Text(Money.format(Decimal(seg.amount)))
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(Color.appTextTertiary)
                        Text(total > 0 ? String(format: "%.0f%%", seg.amount / total * 100) : "—")
                            .font(.caption.weight(.semibold).monospacedDigit())
                            .foregroundStyle(Color.appTextPrimary)
                            .frame(width: 40, alignment: .trailing)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity)
    }
}
