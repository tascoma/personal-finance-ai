import SwiftUI

struct ExpenseInsightsTab: View {
    let data: DashboardResponse

    private var lifestylePct: Double {
        let comp = data.compensationIncome.asDouble
        guard comp != 0 else { return 0 }
        return data.lifestyleExpenses.asDouble / comp * 100
    }

    private var avgExpPerPeriod: Decimal {
        guard data.periodCount > 0 else { return 0 }
        return data.totalExpenses / Decimal(data.periodCount)
    }

    private var expToIncomePct: Double {
        let inc = data.totalIncome.asDouble
        guard inc > 0 else { return 0 }
        return data.totalExpenses.asDouble / inc * 100
    }

    private var periodDeltaPct: Double? {
        guard data.periodBars.count >= 2 else { return nil }
        let last = data.periodBars[data.periodBars.count - 1].expenses.asDouble
        let prev = data.periodBars[data.periodBars.count - 2].expenses.asDouble
        guard prev != 0 else { return nil }
        return (last - prev) / prev * 100
    }

    private var expenseSeries: [Double] { data.periodBars.map { $0.expenses.asDouble } }

    private var hero: HeroCard {
        var delta: HeroDelta?
        if let pct = periodDeltaPct {
            delta = HeroDelta(
                text: "\(pct >= 0 ? "+" : "")\(String(format: "%.1f", pct))% vs prior period",
                trend: pct >= 0 ? .up : .down
            )
        }
        return HeroCard(
            style: .expenses,
            eyebrow: "Total Expenses",
            value: Money.format(data.totalExpenses, fractionDigits: 0),
            delta: delta,
            stats: [
                HeroStat(label: "Lifestyle Rate", value: String(format: "%.1f%%", lifestylePct)),
                HeroStat(label: "Exp / Income", value: String(format: "%.1f%%", expToIncomePct)),
                HeroStat(label: "Avg / Period", value: Money.format(avgExpPerPeriod, fractionDigits: 0)),
            ],
            sparkline: expenseSeries
        )
    }

    private var expenseSegments: [RingSegment] {
        data.topExpenseCategories.prefix(8).enumerated().map { idx, c in
            RingSegment(name: c.category, amount: c.amount.asDouble,
                        color: ChartPalette.expense[idx % ChartPalette.expense.count])
        }
    }

    var body: some View {
        VStack(spacing: 16) {
            hero

            if !data.topExpenseCategories.isEmpty {
                DashboardCard("Expense Mix",
                              subtitle: "\(Money.format(data.totalExpenses, fractionDigits: 0)) across \(data.topExpenseCategories.count) categories") {
                    RingWithLegend(segments: expenseSegments,
                                   centerValue: Money.compact(data.totalExpenses),
                                   centerLabel: "Total")
                }
            }

            if !data.expenseCategorySeries.isEmpty {
                DashboardCard("Expense Trendlines", subtitle: "by sub-category") {
                    ExpenseTrendlinesChart(series: data.expenseCategorySeries,
                                           topCategories: data.topExpenseCategories)
                }
            }

            if !data.topExpenseCategories.isEmpty && data.compensationIncome > 0 {
                DashboardCard("Category Spend vs Compensation", subtitle: "each category as % of salary + bonus") {
                    CategoryVsCompChart(categories: data.topExpenseCategories,
                                        compensation: data.compensationIncome)
                }
            }
        }
    }
}
