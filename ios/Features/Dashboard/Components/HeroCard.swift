import SwiftUI
import Charts

/// A small label/value pair shown in the hero's bottom strip.
struct HeroStat: Identifiable {
    let id = UUID()
    let label: String
    let value: String
}

/// The "+$1,234 (+5.2%) · YTD" pill under the hero number.
struct HeroDelta {
    enum Trend { case up, down, flat }
    let text: String
    let trend: Trend

    var systemImage: String {
        switch trend {
        case .up:   return "arrow.up.right"
        case .down: return "arrow.down.right"
        case .flat: return "arrow.right"
        }
    }
}

/// Per-tab gradient identity, mirroring the web `.hero` variants.
enum HeroStyle {
    case netWorth, expenses, assets, period, forecast

    var gradient: [Color] {
        switch self {
        case .netWorth: return [Self.dyn("56c8f0", "0284c7"), Self.dyn("2596c4", "38bdf8")]
        case .expenses: return [Self.dyn("fb7185", "dc2626"), Self.dyn("b45309", "b45309")]
        case .assets:   return [Self.dyn("22c55e", "16a34a"), Self.dyn("15803d", "14532d")]
        case .period:   return [Self.dyn("475569", "334155"), Self.dyn("1e293b", "0f172a")]
        case .forecast: return [Self.dyn("7c3aed", "6d28d9"), Self.dyn("4338ca", "3730a3")]
        }
    }

    private static func dyn(_ dark: String, _ light: String) -> Color {
        Color(UIColor { $0.userInterfaceStyle == .dark ? UIColor(hex: dark) : UIColor(hex: light) })
    }
}

/// Gradient "hero" panel matching the web frontend's dashboard hero
/// (frontend/src/styles/style.css `.hero`). Single-column, native-friendly
/// layout — the web itself collapses the hero to one column on narrow screens.
struct HeroCard: View {
    let style: HeroStyle
    let eyebrow: String
    let value: String
    var delta: HeroDelta? = nil
    var stats: [HeroStat] = []
    var sparkline: [Double] = []

    var body: some View {
        VStack(alignment: .leading, spacing: Space.lg) {
            VStack(alignment: .leading, spacing: 10) {
                Text(eyebrow)
                    .font(.system(size: 11, weight: .bold))
                    .textCase(.uppercase)
                    .kerning(1.2)
                    .opacity(0.7)
                Text(value)
                    .font(.system(size: 44, weight: .semibold).monospacedDigit())
                    .lineLimit(1)
                    .minimumScaleFactor(0.5)
                if let delta {
                    HStack(spacing: 6) {
                        Image(systemName: delta.systemImage)
                            .font(.system(size: 11, weight: .semibold))
                        Text(delta.text)
                            .font(.system(size: 12.5, weight: .semibold))
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(.white.opacity(0.18), in: Capsule())
                }
            }

            if sparkline.count >= 2 {
                HeroSparkline(values: sparkline)
                    .frame(height: 64)
            }

            if !stats.isEmpty {
                HStack(spacing: 1) {
                    ForEach(stats) { stat in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(stat.label)
                                .font(.system(size: 10, weight: .bold))
                                .textCase(.uppercase)
                                .kerning(0.8)
                                .opacity(0.7)
                                .lineLimit(1)
                                .minimumScaleFactor(0.6)
                            Text(stat.value)
                                .font(.system(size: 16, weight: .semibold).monospacedDigit())
                                .lineLimit(1)
                                .minimumScaleFactor(0.6)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 10)
                        .background(Color.black.opacity(0.10))
                    }
                }
                // 1px gaps reveal this strip, mimicking the web's hairline dividers.
                .background(Color.white.opacity(0.20))
                .clipShape(RoundedRectangle(cornerRadius: Radius.sm))
            }
        }
        .foregroundStyle(.white)
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            LinearGradient(colors: style.gradient, startPoint: .topLeading, endPoint: .bottomTrailing),
            in: RoundedRectangle(cornerRadius: Radius.lg)
        )
        .overlay(
            RoundedRectangle(cornerRadius: Radius.lg)
                .fill(
                    RadialGradient(
                        colors: [.white.opacity(0.14), .clear],
                        center: .bottomLeading,
                        startRadius: 0,
                        endRadius: 340
                    )
                )
                .allowsHitTesting(false)
        )
    }
}

/// Minimal white sparkline used inside the hero — no axes, soft fill.
private struct HeroSparkline: View {
    let values: [Double]

    var body: some View {
        let indexed = Array(values.enumerated())
        let minV = values.min() ?? 0
        let maxV = values.max() ?? 1
        let pad = max((maxV - minV) * 0.1, 1)

        Chart {
            ForEach(indexed, id: \.offset) { idx, v in
                AreaMark(
                    x: .value("i", idx),
                    yStart: .value("base", minV - pad),
                    yEnd: .value("v", v)
                )
                .interpolationMethod(.catmullRom)
                .foregroundStyle(
                    LinearGradient(
                        colors: [.white.opacity(0.30), .white.opacity(0)],
                        startPoint: .top, endPoint: .bottom
                    )
                )

                LineMark(x: .value("i", idx), y: .value("v", v))
                    .interpolationMethod(.catmullRom)
                    .foregroundStyle(.white)
                    .lineStyle(StrokeStyle(lineWidth: 2.2))
            }
        }
        .chartYScale(domain: (minV - pad)...(maxV + pad))
        .chartXAxis(.hidden)
        .chartYAxis(.hidden)
    }
}
