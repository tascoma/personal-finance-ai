import SwiftUI

struct OverviewTab: View {
    let data: DashboardResponse
    let scopeLabel: String

    // MARK: Hero figures

    private var retirementPct: Double {
        let comp = data.compensationIncome.asDouble
        guard comp != 0 else { return 0 }
        return data.retirementContributions.asDouble / comp * 100
    }

    private var nwSeries: [Double] { data.netWorthSeries.map { $0.netWorth.asDouble } }

    private var ytdDelta: Decimal? {
        guard let first = data.netWorthSeries.first, data.netWorthSeries.count > 1 else { return nil }
        return data.netWorth - first.netWorth
    }

    private var lastMonthDelta: Decimal? {
        let s = data.netWorthSeries
        guard s.count >= 2 else { return nil }
        return s[s.count - 1].netWorth - s[s.count - 2].netWorth
    }

    private var debtToEquity: Double? {
        guard data.netWorth != 0 else { return nil }
        return data.totalLiabilities.asDouble / data.netWorth.asDouble
    }

    private var hero: HeroCard {
        var delta: HeroDelta?
        if let d = ytdDelta {
            let base = data.netWorthSeries.first?.netWorth ?? 0
            let pct = base != 0 ? (d.asDouble / base.asDouble) * 100 : 0
            delta = HeroDelta(
                text: "\(Money.delta(d)) (\(pct >= 0 ? "+" : "")\(String(format: "%.1f", pct))%) · YTD",
                trend: d >= 0 ? .up : .down
            )
        }
        return HeroCard(
            style: .netWorth,
            eyebrow: "Net Worth",
            value: Money.format(data.netWorth, fractionDigits: 0),
            delta: delta,
            stats: [
                HeroStat(label: "This Month", value: lastMonthDelta.map { Money.delta($0) } ?? "—"),
                HeroStat(label: "Debt / Equity", value: debtToEquity.map { String(format: "%.2f", $0) } ?? "—"),
                HeroStat(label: "Savings Rate", value: String(format: "%.1f%%", retirementPct)),
            ],
            sparkline: nwSeries
        )
    }

    // MARK: Asset composition ring

    private var assetSegments: [RingSegment] {
        data.assetComposition.prefix(6).enumerated().map { idx, c in
            RingSegment(name: c.subCategory, amount: c.amount.asDouble,
                        color: ChartPalette.asset[idx % ChartPalette.asset.count])
        }
    }

    var body: some View {
        VStack(spacing: 16) {
            if !nwSeries.isEmpty { hero }

            if !data.assetComposition.isEmpty {
                DashboardCard("Asset Composition",
                              subtitle: "\(Money.format(data.totalAssets, fractionDigits: 0)) across \(data.assetComposition.count) buckets") {
                    RingWithLegend(segments: assetSegments,
                                   centerValue: Money.compact(data.totalAssets),
                                   centerLabel: "Total")
                }
            }

            if data.ytdRetirementContributions.contains(where: { $0.amount > 0 }) {
                DashboardCard("Retirement Progress",
                              subtitle: "\(data.ytdYear.map(String.init) ?? "") contribution limits") {
                    RetirementProgress(contributions: data.ytdRetirementContributions)
                }
            }

            if !data.periodBars.isEmpty {
                DashboardCard("Income vs Expenses", subtitle: "by period") {
                    IncomeExpensesChart(bars: data.periodBars)
                }
            }

            DashboardCard("Income Statement", subtitle: scopeLabel) {
                IncomeStatementContent(totalIncome: data.totalIncome,
                                       totalExpenses: data.totalExpenses,
                                       netIncome: data.netIncome,
                                       oci: data.oci)
            }

            if !data.topExpenseCategories.isEmpty {
                DashboardCard("Top Categories", subtitle: "by spend") {
                    TopCategoriesBars(categories: data.topExpenseCategories)
                }
            }

            if !data.recentEntries.isEmpty {
                DashboardCard("Recent Activity", subtitle: "latest 6 posted entries") {
                    RecentActivityList(entries: data.recentEntries)
                }
            }
        }
    }
}
