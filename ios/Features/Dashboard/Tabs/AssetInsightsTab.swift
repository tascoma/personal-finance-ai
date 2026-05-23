import SwiftUI

struct AssetInsightsTab: View {
    let data: DashboardResponse

    // Account-code → IRS contribution limit and short label, mirroring the web.
    private static let limits: [Int: Decimal] = [
        111101: 7500,    // Roth IRA
        111102: 24500,   // 401(k)
        111103: 4400,    // HSA
    ]
    private static let shortName: [Int: String] = [
        111101: "Roth IRA",
        111102: "401(k)",
        111103: "HSA",
    ]

    private var totalAssetsDelta: Decimal { data.totalAssets - data.totalAssetsPrev }
    private var liquidDelta: Decimal { data.liquidAssets - data.liquidAssetsPrev }
    private var taxAdvDelta: Decimal { data.taxAdvantaged - data.taxAdvantagedPrev }

    private var elapsedFraction: Double {
        guard let ytdYear = data.ytdYear else { return 1 }
        let cal = Calendar(identifier: .gregorian)
        let now = Date()
        let currentYear = cal.component(.year, from: now)
        if ytdYear < currentYear { return 1 }
        guard ytdYear == currentYear,
              let yearStart = cal.date(from: DateComponents(year: ytdYear, month: 1, day: 1)),
              let yearEnd = cal.date(from: DateComponents(year: ytdYear + 1, month: 1, day: 1))
        else { return 1 }
        let total = yearEnd.timeIntervalSince(yearStart)
        let elapsed = now.timeIntervalSince(yearStart)
        return min(max(elapsed / total, 0), 1)
    }

    var body: some View {
        VStack(spacing: 16) {
            KPIGrid {
                KPICard(label: "Total Assets",
                        value: Money.format(data.totalAssets),
                        valueColor: .accentColor,
                        sub: data.totalAssetsPrev != 0
                            ? "\(Money.delta(totalAssetsDelta)) vs prior"
                            : nil)
                KPICard(label: "Liquid Assets",
                        value: Money.format(data.liquidAssets),
                        valueColor: .accentColor,
                        sub: data.liquidAssetsPrev != 0
                            ? "\(Money.delta(liquidDelta)) vs prior"
                            : "cash + investments")
                KPICard(label: "Tax Advantaged",
                        value: Money.format(data.taxAdvantaged),
                        valueColor: .accentColor,
                        sub: data.taxAdvantagedPrev != 0
                            ? "\(Money.delta(taxAdvDelta)) vs prior"
                            : "retirement accts")
                KPICard(label: "Total Liabilities",
                        value: Money.format(data.totalLiabilities),
                        valueColor: data.totalLiabilities > 0 ? .red : .secondary)
            }

            if !data.ytdRetirementContributions.isEmpty {
                DashboardCard(
                    "Retirement Contributions",
                    subtitle: "YTD · \(data.ytdYear.map(String.init) ?? "—") · \(Int(elapsedFraction * 100))% of year elapsed"
                ) {
                    VStack(spacing: 14) {
                        ForEach(data.ytdRetirementContributions) { c in
                            retirementRow(c)
                        }
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func retirementRow(_ c: RetirementContributionPoint) -> some View {
        let limit = Self.limits[c.accountCode] ?? 0
        let contributed = max(c.amount, 0)
        let pct = limit > 0
            ? min(100, contributed.asDouble / limit.asDouble * 100)
            : 0
        let remaining = max(limit - contributed, 0)
        let pace = limit > 0
            ? (contributed.asDouble / limit.asDouble) / max(elapsedFraction, 0.001)
            : 1
        let fillColor: Color = {
            if contributed >= limit || pace >= 0.95 { return .green }
            if pace >= 0.7 { return .orange }
            return .red
        }()
        let label = Self.shortName[c.accountCode] ?? c.accountName

        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text(label).font(.subheadline.weight(.semibold))
                Text("\(Money.format(contributed)) / \(Money.format(limit))")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Spacer()
                Text(String(format: "%.1f%%", pct))
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(fillColor)
            }

            GeometryReader { geom in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 5).fill(Color.gray.opacity(0.18))
                    RoundedRectangle(cornerRadius: 5)
                        .fill(fillColor)
                        .frame(width: geom.size.width * pct / 100)
                    if elapsedFraction > 0 && elapsedFraction < 1 {
                        Rectangle()
                            .fill(Color.secondary.opacity(0.6))
                            .frame(width: 2, height: 14)
                            .offset(x: geom.size.width * elapsedFraction - 1, y: 0)
                    }
                }
            }
            .frame(height: 10)

            Text(remaining > 0
                 ? "\(Money.format(remaining)) left to hit the limit"
                 : "Limit reached")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }
}
