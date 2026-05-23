import SwiftUI

struct ExpenseInsightsTab: View {
    let data: DashboardResponse

    private var lifestylePct: Double {
        let comp = data.compensationIncome.asDouble
        guard comp != 0 else { return 0 }
        return data.lifestyleExpenses.asDouble / comp * 100
    }

    private var lifestyleColor: Color {
        if lifestylePct > 30 { return .red }
        if lifestylePct > 20 { return .orange }
        return .green
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

    private var expIncomeColor: Color {
        if expToIncomePct > 100 { return .red }
        if expToIncomePct > 80 { return .orange }
        return .green
    }

    private var periodDeltaPct: Double? {
        guard data.periodBars.count >= 2 else { return nil }
        let last = data.periodBars[data.periodBars.count - 1].expenses.asDouble
        let prev = data.periodBars[data.periodBars.count - 2].expenses.asDouble
        guard prev != 0 else { return nil }
        return (last - prev) / prev * 100
    }

    var body: some View {
        VStack(spacing: 16) {
            KPIGrid {
                KPICard(label: "Lifestyle Rate",
                        value: String(format: "%.1f%%", lifestylePct),
                        valueColor: lifestyleColor,
                        sub: "of salary + bonus")
                KPICard(label: "Lifestyle Spend",
                        value: Money.format(data.lifestyleExpenses),
                        valueColor: .red)
                KPICard(label: "Avg / Period",
                        value: Money.format(avgExpPerPeriod),
                        valueColor: .red,
                        sub: "\(data.periodCount) periods")
                KPICard(label: "Expense / Income",
                        value: String(format: "%.1f%%", expToIncomePct),
                        valueColor: expIncomeColor,
                        sub: "spent vs earned")
                if let top = data.topExpenseCategories.first {
                    let pct = data.totalExpenses > 0
                        ? top.amount.asDouble / data.totalExpenses.asDouble * 100
                        : 0
                    KPICard(label: "Top Category",
                            value: top.category,
                            valueColor: .accentColor,
                            sub: String(format: "%.0f%% of expenses", pct))
                }
                if let delta = periodDeltaPct {
                    KPICard(label: "Δ vs Prior",
                            value: String(format: "%@%.1f%%", delta >= 0 ? "+" : "", delta),
                            valueColor: delta > 0 ? .red : .green,
                            sub: "period over period")
                }
            }

            if !data.topExpenseCategories.isEmpty {
                DashboardCard("Expense Mix", subtitle: "top \(data.topExpenseCategories.count)") {
                    ExpenseMixDonut(categories: data.topExpenseCategories)
                }
            }
        }
    }
}
