import SwiftUI

/// Top expense categories as labelled progress bars (web overview "Top Categories").
struct TopCategoriesBars: View {
    let categories: [ExpenseCategoryPoint]

    private var top: [ExpenseCategoryPoint] { Array(categories.prefix(6)) }
    private var maxAmount: Double { top.first?.amount.asDouble ?? 0 }

    var body: some View {
        VStack(spacing: Space.md) {
            ForEach(top) { c in
                let pct = maxAmount > 0 ? c.amount.asDouble / maxAmount : 0
                VStack(spacing: 6) {
                    HStack {
                        Text(c.category)
                            .font(.subheadline)
                            .foregroundStyle(Color.appTextPrimary)
                            .lineLimit(1)
                        Spacer()
                        Text(Money.format(c.amount))
                            .font(.subheadline.weight(.semibold).monospacedDigit())
                            .foregroundStyle(Color.appTextPrimary)
                    }
                    GeometryReader { geo in
                        ZStack(alignment: .leading) {
                            RoundedRectangle(cornerRadius: 3).fill(Color.appSurface)
                            RoundedRectangle(cornerRadius: 3)
                                .fill(Color.appAccent)
                                .frame(width: geo.size.width * pct)
                        }
                    }
                    .frame(height: 5)
                }
            }
        }
    }
}

/// A label/value line for the Period tab's balance sheet and cash flow snapshot
/// cards. `IncomeStatementContent` keeps its own equivalent private because it also
/// handles parenthesised outflows; this is the plain variant.
struct SnapshotRow: View {
    let label: String
    let value: String
    var valueColor: Color = .appTextPrimary
    var bold: Bool = false
    var trailing: AnyView? = nil

    var body: some View {
        HStack {
            Text(label)
                .font(bold ? .subheadline.weight(.semibold) : .subheadline)
                .foregroundStyle(bold ? Color.appTextPrimary : Color.appTextSecondary)
            Spacer()
            if let trailing {
                trailing
            }
            Text(value)
                .font((bold ? Font.callout.weight(.semibold) : .subheadline.weight(.semibold)).monospacedDigit())
                .foregroundStyle(valueColor)
        }
    }
}

/// Revenue / Expenses / Net Income summary (web overview "Income Statement").
struct IncomeStatementContent: View {
    let totalIncome: Decimal
    let totalExpenses: Decimal
    let netIncome: Decimal
    let oci: Decimal

    private var comprehensiveIncome: Decimal { netIncome + oci }

    var body: some View {
        VStack(spacing: Space.md) {
            row("Revenue", totalIncome, color: .appGreen)
            row("Expenses", totalExpenses, color: .appRed, parenthesize: true)
            Rectangle().fill(Color.appLine).frame(height: 1)
            row("Net Income", netIncome, color: netIncome >= 0 ? .appGreen : .appRed, bold: true)
            if oci != 0 {
                row("OCI", oci, color: oci >= 0 ? .appGreen : .appRed)
                Rectangle().fill(Color.appLine).frame(height: 1)
                row("Comprehensive Income", comprehensiveIncome,
                    color: comprehensiveIncome >= 0 ? .appGreen : .appRed, bold: true)
            }
        }
    }

    /// `parenthesize` forces parens even for non-negative values (e.g. Expenses, which
    /// the API reports as a positive total but is always displayed as an outflow).
    /// Negative values are always parenthesized around their absolute value.
    private func row(_ label: String, _ value: Decimal, color: Color, bold: Bool = false, parenthesize: Bool = false) -> some View {
        let valueFont: Font = bold ? .callout.weight(.semibold) : .subheadline.weight(.semibold)
        let text = (parenthesize || value < 0) ? "(\(Money.format(Swift.abs(value))))" : Money.format(value)
        return HStack {
            Text(label)
                .font(bold ? .subheadline.weight(.semibold) : .subheadline)
                .foregroundStyle(bold ? Color.appTextPrimary : Color.appTextSecondary)
            Spacer()
            Text(text)
                .font(valueFont.monospacedDigit())
                .foregroundStyle(color)
        }
    }
}

/// Latest posted entries (web overview "Recent Activity").
struct RecentActivityList: View {
    let entries: [RecentEntryPoint]

    var body: some View {
        VStack(spacing: Space.md) {
            // Index-keyed: two entries can share period/date/description
            // (e.g. duplicate market-gain adjustments), which collides on `id`.
            ForEach(Array(entries.enumerated()), id: \.offset) { index, entry in
                HStack(alignment: .top, spacing: Space.md) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(entry.description)
                            .font(.callout)
                            .foregroundStyle(Color.appTextPrimary)
                            .lineLimit(1)
                        HStack(spacing: 6) {
                            Text("\(entry.periodLabel) · \(entry.entryDate)")
                                .font(.caption2)
                                .foregroundStyle(Color.appTextTertiary)
                            Text(entry.sourceType)
                                .font(.system(size: 10, weight: .semibold))
                                .foregroundStyle(Color.appTextSecondary)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 1)
                                .background(Color.appSurface, in: Capsule())
                        }
                    }
                    Spacer()
                    Text(Money.format(entry.totalDebit))
                        .font(.callout.weight(.semibold).monospacedDigit())
                        .foregroundStyle(Color.appTextPrimary)
                }
                if index != entries.count - 1 {
                    Rectangle().fill(Color.appLine).frame(height: 1)
                }
            }
        }
    }
}

/// Retirement-contribution ring + per-account progress bars
/// (web overview "Retirement Progress"). 2026 IRS contribution limits.
struct RetirementProgress: View {
    let contributions: [RetirementContributionPoint]

    private static let limit401k: Decimal = 24_500
    private static let limitIRA: Decimal = 7_500
    private static let limitHSA: Decimal = 4_400
    private static let limitTotal: Decimal = 36_400

    private func limit(for name: String) -> Decimal {
        let n = name.lowercased()
        if n.contains("401") { return Self.limit401k }
        if n.contains("ira") { return Self.limitIRA }
        if n.contains("hsa") { return Self.limitHSA }
        return 0
    }

    private var total: Decimal {
        contributions.reduce(Decimal(0)) { $0 + max(0, $1.amount) }
    }

    private var pct: Double {
        Self.limitTotal > 0 ? total.asDouble / Self.limitTotal.asDouble * 100 : 0
    }

    var body: some View {
        VStack(spacing: Space.lg) {
            RingChart(
                segments: [
                    RingSegment(name: "Contributed", amount: total.asDouble, color: .appAccent),
                    RingSegment(name: "Remaining",
                                amount: max(0, (Self.limitTotal - total).asDouble),
                                color: .appLineStrong),
                ],
                centerValue: String(format: "%.1f%%", pct),
                centerLabel: "of limit",
                goalPct: 80
            )

            VStack(spacing: Space.md) {
                ForEach(contributions) { c in
                    let lim = limit(for: c.accountName)
                    let p = lim > 0 ? min(1, max(0, c.amount).asDouble / lim.asDouble) : 0
                    VStack(spacing: 6) {
                        HStack {
                            Text(c.accountName)
                                .font(.caption)
                                .foregroundStyle(Color.appTextPrimary)
                            Spacer()
                            Text(lim > 0
                                 ? "\(Money.format(c.amount)) / \(Money.format(lim))"
                                 : Money.format(c.amount))
                                .font(.caption.weight(.semibold).monospacedDigit())
                                .foregroundStyle(Color.appTextSecondary)
                        }
                        if lim > 0 {
                            GeometryReader { geo in
                                ZStack(alignment: .leading) {
                                    RoundedRectangle(cornerRadius: 2).fill(Color.appSurface)
                                    RoundedRectangle(cornerRadius: 2)
                                        .fill(Color.appAccent)
                                        .frame(width: geo.size.width * p)
                                }
                            }
                            .frame(height: 4)
                        }
                    }
                }
            }
        }
    }
}
