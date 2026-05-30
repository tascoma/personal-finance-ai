import SwiftUI

struct AssetInsightsTab: View {
    let data: DashboardResponse

    private static let growthExcluded: Set<String> = [
        "Real Estate", "Cash & Cash Equivalents", "Restricted Cash"
    ]

    private var totalAssetsDelta: Decimal { data.totalAssets - data.totalAssetsPrev }

    private var periodLabels: [String] {
        var seen = Set<String>()
        return data.assetSeries.compactMap { seen.insert($0.periodLabel).inserted ? $0.periodLabel : nil }
    }

    private var assetTotals: [Double] {
        periodLabels.map { pl in
            data.assetSeries.filter { $0.periodLabel == pl }.reduce(0.0) { $0 + $1.amount.asDouble }
        }
    }

    /// Growth excluding house & cash, mirroring the web's YTD asset delta.
    private var growthTotals: [Double] {
        periodLabels.map { pl in
            data.assetSeries
                .filter { $0.periodLabel == pl && !Self.growthExcluded.contains($0.subCategory) }
                .reduce(0.0) { $0 + $1.amount.asDouble }
        }
    }

    private var ytdGrowth: (pct: Double, delta: Double)? {
        let labels = periodLabels
        let totals = growthTotals
        guard let latestLabel = labels.last else { return nil }
        let latestYear = yearOf(latestLabel)
        var baselineIdx = -1
        for i in stride(from: labels.count - 1, through: 0, by: -1) where yearOf(labels[i]) < latestYear {
            baselineIdx = i; break
        }
        guard baselineIdx >= 0 else { return nil }
        let baseline = totals[baselineIdx]
        guard baseline != 0 else { return nil }
        let last = totals[totals.count - 1]
        return ((last - baseline) / baseline * 100, last - baseline)
    }

    private func yearOf(_ label: String) -> Int {
        Int(label.split(separator: " ").last.map(String.init) ?? "") ?? 0
    }

    private var hero: HeroCard {
        var delta: HeroDelta?
        if let g = ytdGrowth {
            delta = HeroDelta(
                text: "\(Money.delta(Decimal(g.delta))) (\(g.pct >= 0 ? "+" : "")\(String(format: "%.1f", g.pct))%) · YTD",
                trend: g.delta >= 0 ? .up : .down
            )
        }
        return HeroCard(
            style: .assets,
            eyebrow: "Total Assets",
            value: Money.format(data.totalAssets, fractionDigits: 0),
            delta: delta,
            stats: [
                HeroStat(label: "This Month",
                         value: data.totalAssetsPrev != 0 ? Money.delta(totalAssetsDelta) : "—"),
                HeroStat(label: "Tax Advantaged", value: Money.format(data.taxAdvantaged, fractionDigits: 0)),
                HeroStat(label: "Liquid", value: Money.format(data.liquidAssets, fractionDigits: 0)),
            ],
            sparkline: assetTotals
        )
    }

    private var assetSegments: [RingSegment] {
        data.assetComposition.prefix(6).enumerated().map { idx, c in
            RingSegment(name: c.subCategory, amount: c.amount.asDouble,
                        color: ChartPalette.asset[idx % ChartPalette.asset.count])
        }
    }

    var body: some View {
        VStack(spacing: 16) {
            hero

            if !data.assetComposition.isEmpty {
                DashboardCard("Asset Mix",
                              subtitle: "\(Money.format(data.totalAssets, fractionDigits: 0)) across \(data.assetComposition.count) buckets") {
                    RingWithLegend(segments: assetSegments,
                                   centerValue: Money.compact(data.totalAssets),
                                   centerLabel: "Total")
                }
            }

            if !data.assetSeries.isEmpty {
                DashboardCard("Composition Over Time", subtitle: "by sub-category") {
                    AssetCompositionStackChart(series: data.assetSeries,
                                               composition: data.assetComposition)
                }
            }
        }
    }
}
