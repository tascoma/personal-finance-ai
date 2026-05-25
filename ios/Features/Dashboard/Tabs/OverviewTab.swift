import SwiftUI

struct OverviewTab: View {
    let data: DashboardResponse

    private var retirementPct: Double {
        let comp = data.compensationIncome.asDouble
        guard comp != 0 else { return 0 }
        return data.retirementContributions.asDouble / comp * 100
    }

    var body: some View {
        VStack(spacing: 16) {
            KPIGrid {
                KPICard(label: "Total Income",
                        value: Money.format(data.totalIncome),
                        valueColor: .appGreen)
                KPICard(label: "Total Expenses",
                        value: Money.format(data.totalExpenses),
                        valueColor: .appRed)
                KPICard(label: "Net Income",
                        value: Money.format(data.netIncome),
                        valueColor: data.netIncome >= 0 ? .appGreen : .appRed)
                KPICard(label: "Total Assets",
                        value: Money.format(data.totalAssets),
                        valueColor: .appAccent)
                KPICard(label: "Net Worth",
                        value: Money.format(data.netWorth),
                        valueColor: data.netWorth >= 0 ? .appAccent : .appRed)
                KPICard(label: "Retirement Savings",
                        value: String(format: "%.1f%%", retirementPct),
                        valueColor: retirementPct >= 0 ? .appGreen : .appRed,
                        sub: "of salary + bonus")
            }

            if !data.periodBars.isEmpty {
                DashboardCard("Income vs Expenses", subtitle: "by period") {
                    IncomeExpensesChart(bars: data.periodBars)
                }
            }

            if !data.netWorthSeries.isEmpty {
                DashboardCard("Net Worth Trend", subtitle: "cumulative, per period") {
                    NetWorthTrendChart(series: data.netWorthSeries)
                }
            }

            if !data.topExpenseCategories.isEmpty {
                DashboardCard("Expenses by Category", subtitle: "all time · top 8") {
                    ExpenseCategoryBar(categories: data.topExpenseCategories)
                }
            }

            if !data.recentEntries.isEmpty {
                DashboardCard("Recent Entries", subtitle: "latest 6 posted") {
                    VStack(spacing: 8) {
                        ForEach(data.recentEntries) { entry in
                            HStack(alignment: .top, spacing: 8) {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(entry.description)
                                        .font(.callout)
                                        .lineLimit(1)
                                    Text("\(entry.periodLabel) · \(entry.entryDate)")
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                Text(Money.format(entry.totalDebit))
                                    .font(.callout.monospacedDigit())
                                    .foregroundStyle(.secondary)
                            }
                            if entry.id != data.recentEntries.last?.id {
                                Divider()
                            }
                        }
                    }
                }
            }
        }
    }
}
