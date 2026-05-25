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

    private static let growthExcluded: Set<String> = [
        "Real Estate", "Cash & Cash Equivalents", "Restricted Cash"
    ]

    private var totalAssetsDelta: Decimal { data.totalAssets - data.totalAssetsPrev }
    private var liquidDelta: Decimal { data.liquidAssets - data.liquidAssetsPrev }
    private var taxAdvDelta: Decimal { data.taxAdvantaged - data.taxAdvantagedPrev }

    private var periodLabels: [String] {
        var seen = Set<String>()
        return data.assetSeries.compactMap { seen.insert($0.periodLabel).inserted ? $0.periodLabel : nil }
    }

    private var growthTotals: [Double] {
        periodLabels.map { pl in
            data.assetSeries
                .filter { $0.periodLabel == pl && !Self.growthExcluded.contains($0.subCategory) }
                .reduce(0.0) { $0 + $1.amount.asDouble }
        }
    }

    private var periodGrowth: (pct: Double, delta: Double, prev: String, curr: String)? {
        let labels = periodLabels
        let totals = growthTotals
        guard totals.count >= 2 else { return nil }
        let last = totals[totals.count - 1]
        let prev = totals[totals.count - 2]
        guard prev != 0 else { return nil }
        return ((last - prev) / prev * 100, last - prev, labels[labels.count - 2], labels[labels.count - 1])
    }

    private var ytdGrowth: (pct: Double, delta: Double, baseline: String, latest: String)? {
        let labels = periodLabels
        let totals = growthTotals
        guard let latestLabel = labels.last else { return nil }
        let latestYear = yearOf(latestLabel)
        var baselineIdx = -1
        for i in stride(from: labels.count - 1, through: 0, by: -1) {
            if yearOf(labels[i]) < latestYear { baselineIdx = i; break }
        }
        guard baselineIdx >= 0 else { return nil }
        let baseline = totals[baselineIdx]
        guard baseline != 0 else { return nil }
        let last = totals[totals.count - 1]
        return ((last - baseline) / baseline * 100, last - baseline, labels[baselineIdx], latestLabel)
    }

    private func yearOf(_ label: String) -> Int {
        Int(label.split(separator: " ").last.map(String.init) ?? "") ?? 0
    }

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
                KPICard(
                    label: "Total Assets",
                    value: Money.format(data.totalAssets),
                    valueColor: .appAccent,
                    sub: data.totalAssetsPrev != 0
                        ? "\(Money.delta(totalAssetsDelta)) vs prior period"
                        : nil,
                    subColor: data.totalAssetsPrev != 0
                        ? (totalAssetsDelta >= 0 ? .appGreen : .appRed)
                        : nil
                )
                KPICard(
                    label: "Liquid Assets · inc. cash and investments",
                    value: Money.format(data.liquidAssets),
                    valueColor: .appAccent,
                    sub: data.liquidAssetsPrev != 0
                        ? "\(Money.delta(liquidDelta)) vs prior period"
                        : nil,
                    subColor: data.liquidAssetsPrev != 0
                        ? (liquidDelta >= 0 ? .appGreen : .appRed)
                        : nil
                )
                KPICard(
                    label: "Tax Advantaged · inc. Roth IRA, 401k, HSA",
                    value: Money.format(data.taxAdvantaged),
                    valueColor: .appAccent,
                    sub: data.taxAdvantagedPrev != 0
                        ? "\(Money.delta(taxAdvDelta)) vs prior period"
                        : "retirement accounts",
                    subColor: data.taxAdvantagedPrev != 0
                        ? (taxAdvDelta >= 0 ? .appGreen : .appRed)
                        : nil
                )
                KPICard(
                    label: "Period Growth · ex. house & cash",
                    value: periodGrowth.map { g in
                        "\(g.pct >= 0 ? "+" : "")\(String(format: "%.1f", g.pct))%"
                    } ?? "—",
                    valueColor: periodGrowth.map { $0.pct >= 0 ? Color.appGreen : Color.appRed } ?? .secondary,
                    sub: periodGrowth.map { g in
                        "\(Money.delta(Decimal(g.delta))) · \(g.prev) → \(g.curr)"
                    } ?? "needs 2 periods",
                    subColor: periodGrowth.map { $0.pct >= 0 ? Color.appGreen : Color.appRed }
                )
                KPICard(
                    label: "YTD Growth · ex. house & cash",
                    value: ytdGrowth.map { g in
                        "\(g.pct >= 0 ? "+" : "")\(String(format: "%.1f", g.pct))%"
                    } ?? "—",
                    valueColor: ytdGrowth.map { $0.pct >= 0 ? Color.appGreen : Color.appRed } ?? .secondary,
                    sub: ytdGrowth.map { g in
                        "\(Money.delta(Decimal(g.delta))) · \(g.baseline) → \(g.latest)"
                    } ?? "needs prior year",
                    subColor: ytdGrowth.map { $0.pct >= 0 ? Color.appGreen : Color.appRed }
                )
            }

            if !data.assetSeries.isEmpty {
                DashboardCard("Asset Growth", subtitle: "total assets per closed period") {
                    AssetGrowthChart(series: data.assetSeries)
                }
            }

            if !data.assetComposition.isEmpty {
                DashboardCard("Asset Mix", subtitle: "current snapshot") {
                    AssetMixDonut(composition: data.assetComposition)
                }
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
            if contributed >= limit || pace >= 0.95 { return .appGreen }
            if pace >= 0.7 { return .appAmber }
            return .appRed
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
                    RoundedRectangle(cornerRadius: 5).fill(Color.appSurface)
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
