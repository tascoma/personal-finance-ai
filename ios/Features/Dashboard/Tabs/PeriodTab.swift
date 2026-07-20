import SwiftUI

/// A single closed period in review — the web dashboard's "Period" tab.
/// Metrics mirror `frontend/src/pages/dashboard/PeriodTab.tsx`, including its
/// zero-denominator guards (unavailable ratios render as "—" rather than 0).
struct PeriodTab: View {
    @Bindable var vm: PeriodTabViewModel

    var body: some View {
        VStack(spacing: 16) {
            HStack {
                PeriodPicker(periods: vm.periods, selection: periodSelection)
                Spacer()
            }

            switch vm.state {
            case .idle, .loading:
                DashboardCard("Loading period…", subtitle: nil) {
                    ProgressView().frame(maxWidth: .infinity)
                }
            case .error(let message):
                DashboardCard("Couldn't load this period", subtitle: nil) {
                    Text(message)
                        .font(.footnote)
                        .foregroundStyle(Color.appTextTertiary)
                }
            case .loaded(let snapshot):
                Content(snapshot: snapshot, period: vm.selectedPeriod)
            }
        }
    }

    /// `PeriodPicker` writes straight to its binding; route that through the view
    /// model so the write also kicks off the fetch.
    private var periodSelection: Binding<UUID?> {
        Binding(
            get: { vm.selectedPeriodId },
            set: { newValue in
                guard let newValue else { return }
                Task { await vm.select(newValue) }
            }
        )
    }
}

// MARK: - Loaded content

private struct Content: View {
    let snapshot: PeriodTabViewModel.Snapshot
    let period: Period?

    private var curr: DashboardResponse { snapshot.current }
    private var prev: DashboardResponse? { snapshot.previous }
    private var cf: CashflowStatementResponse { snapshot.cashflow }

    // MARK: Derived metrics

    private var netIncome: Decimal { curr.totalIncome - curr.totalExpenses }
    private var comprehensiveIncome: Decimal { netIncome + curr.oci }

    private var debtToEquity: Double? {
        curr.netWorth != 0 ? curr.totalLiabilities.asDouble / curr.netWorth.asDouble : nil
    }

    private var savingsRate: Double {
        curr.compensationIncome > 0
            ? curr.retirementContributions.asDouble / curr.compensationIncome.asDouble * 100
            : 0
    }

    private var prevSavingsRate: Double? {
        guard let prev, prev.compensationIncome > 0 else { return nil }
        return prev.retirementContributions.asDouble / prev.compensationIncome.asDouble * 100
    }

    private var netIncomeDelta: Decimal? {
        guard let prev else { return nil }
        return netIncome - (prev.totalIncome - prev.totalExpenses)
    }

    private var netWorthDelta: Decimal? {
        guard let prev else { return nil }
        return curr.netWorth - prev.netWorth
    }

    private var savingsRateDelta: Double? {
        guard let prevSavingsRate else { return nil }
        return savingsRate - prevSavingsRate
    }

    private var cashRunwayMonths: Double? {
        curr.totalExpenses > 0 ? curr.liquidAssets.asDouble / curr.totalExpenses.asDouble : nil
    }

    private var expenseToIncome: Double? {
        curr.totalIncome > 0 ? curr.totalExpenses.asDouble / curr.totalIncome.asDouble * 100 : nil
    }

    private var operatingCoverage: Double? {
        curr.totalExpenses > 0 ? cf.operatingTotal.asDouble / curr.totalExpenses.asDouble : nil
    }

    private var lifestyleRatio: Double? {
        curr.totalExpenses > 0 ? curr.lifestyleExpenses.asDouble / curr.totalExpenses.asDouble * 100 : nil
    }

    private var topCategory: ExpenseCategoryPoint? { curr.topExpenseCategories.first }

    private var topCategoryShare: Double? {
        guard let topCategory, curr.totalExpenses > 0 else { return nil }
        return topCategory.amount.asDouble / curr.totalExpenses.asDouble * 100
    }

    /// Percent change of `delta` against the prior-period base it was measured from.
    private func pct(_ delta: Decimal, base: Decimal?) -> Double? {
        guard let base, base != 0 else { return nil }
        return delta.asDouble / Swift.abs(base.asDouble) * 100
    }

    // MARK: Hero

    private var hero: HeroCard {
        var delta: HeroDelta?
        if let netIncomeDelta {
            delta = HeroDelta(
                text: "\(Money.delta(netIncomeDelta)) vs prior period",
                trend: netIncomeDelta >= 0 ? .up : .down
            )
        }
        return HeroCard(
            style: .period,
            eyebrow: period.map { "Period · \($0.label)" } ?? "Period",
            value: Money.format(netIncome, fractionDigits: 0),
            delta: delta,
            stats: [
                HeroStat(label: "Savings Rate", value: String(format: "%.1f%%", savingsRate)),
                HeroStat(label: "Net Worth", value: Money.format(curr.netWorth, fractionDigits: 0)),
                HeroStat(label: "Debt / Equity",
                         value: debtToEquity.map { String(format: "%.2f", $0) } ?? "—"),
            ]
        )
    }

    var body: some View {
        VStack(spacing: 16) {
            hero

            KPIGrid {
                KPICard(label: "Ending Cash", value: Money.format(cf.endingCash, fractionDigits: 0))
                KPICard(label: "Cash Runway",
                        value: cashRunwayMonths.map { String(format: "%.1f mo", $0) } ?? "—")
                KPICard(label: "Expense / Income",
                        value: expenseToIncome.map { String(format: "%.1f%%", $0) } ?? "—")
                KPICard(label: "Op. CF Coverage",
                        value: operatingCoverage.map { String(format: "%.2f×", $0) } ?? "—")
            }

            DashboardCard("Income Statement", subtitle: period?.label) {
                IncomeStatementContent(
                    totalIncome: curr.totalIncome,
                    totalExpenses: curr.totalExpenses,
                    netIncome: netIncome,
                    oci: curr.oci
                )
            }

            DashboardCard("Balance Sheet", subtitle: period.map { "as of \($0.label)" }) {
                VStack(spacing: Space.md) {
                    SnapshotRow(label: "Total Assets", value: Money.format(curr.totalAssets))
                    SnapshotRow(label: "Total Liabilities", value: Money.format(curr.totalLiabilities))
                    Rectangle().fill(Color.appLine).frame(height: 1)
                    SnapshotRow(label: "Net Worth", value: Money.format(curr.netWorth), bold: true)
                    if let netWorthDelta {
                        DeltaCaption(delta: netWorthDelta, pct: pct(netWorthDelta, base: prev?.netWorth))
                    }
                    SnapshotRow(label: "Liquid Assets", value: Money.format(curr.liquidAssets))
                    SnapshotRow(label: "Tax-Advantaged", value: Money.format(curr.taxAdvantaged))
                }
            }

            DashboardCard("Cash Flow", subtitle: period?.label) {
                VStack(spacing: Space.md) {
                    ForEach(cashflowSections, id: \.label) { section in
                        SnapshotRow(
                            label: section.label,
                            value: Money.delta(section.value),
                            valueColor: section.value >= 0 ? .appGreen : .appRed
                        )
                    }
                    Rectangle().fill(Color.appLine).frame(height: 1)
                    SnapshotRow(
                        label: "Beginning → Ending",
                        value: "\(Money.compact(cf.beginningCash)) → \(Money.compact(cf.endingCash))"
                    )
                }
            }

            if !curr.topExpenseCategories.isEmpty {
                DashboardCard("Spend Categories", subtitle: period?.label) {
                    TopCategoriesBars(categories: curr.topExpenseCategories)
                }
            }

            DashboardCard("Insights", subtitle: nil) {
                VStack(alignment: .leading, spacing: Space.md) {
                    ForEach(insights, id: \.self) { line in
                        HStack(alignment: .top, spacing: Space.sm) {
                            Image(systemName: "chart.line.uptrend.xyaxis")
                                .font(.caption)
                                .foregroundStyle(Color.appAccent)
                            Text(line)
                                .font(.subheadline)
                                .foregroundStyle(Color.appTextSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            }
        }
    }

    private var cashflowSections: [(label: String, value: Decimal)] {
        [
            ("Operating", cf.operatingTotal),
            ("Investing", cf.investingTotal),
            ("Financing", cf.financingTotal),
            ("Net Change", cf.netChangeInCash),
        ]
    }

    /// The generated commentary from the web tab, each line guarded on the data it needs.
    private var insights: [String] {
        var lines: [String] = []

        if let netIncomeDelta {
            let direction = netIncomeDelta >= 0 ? "increased" : "decreased"
            let suffix = pct(netIncomeDelta, base: prev.map { $0.totalIncome - $0.totalExpenses })
                .map { String(format: " (%.1f%%)", Swift.abs($0)) } ?? ""
            lines.append("Net income \(direction) by \(Money.format(Swift.abs(netIncomeDelta)))\(suffix) vs the prior period.")
        } else {
            lines.append("First tracked period — no prior comparison.")
        }

        if curr.compensationIncome == 0 {
            lines.append("No compensation income recorded this period.")
        } else if let savingsRateDelta {
            let direction = savingsRateDelta >= 0 ? "up" : "down"
            lines.append(String(format: "Savings rate is %.1f%%, %@ %.1f pts from the prior period.",
                                savingsRate, direction, Swift.abs(savingsRateDelta)))
        } else {
            lines.append(String(format: "Savings rate is %.1f%% — no prior period to compare.", savingsRate))
        }

        if let netWorthDelta {
            let direction = netWorthDelta >= 0 ? "grew" : "shrank"
            let suffix = pct(netWorthDelta, base: prev?.netWorth)
                .map { String(format: " (%.1f%%)", Swift.abs($0)) } ?? ""
            lines.append("Net worth \(direction) by \(Money.format(Swift.abs(netWorthDelta)))\(suffix) vs the prior period.")
        } else {
            lines.append("No prior period to compare net worth against.")
        }

        if let topCategory, let topCategoryShare {
            lines.append(String(format: "%@ was your largest expense at %@ (%.0f%% of total spend).",
                                topCategory.category, Money.format(topCategory.amount), topCategoryShare))
        }

        if let lifestyleRatio {
            lines.append(String(format: "Discretionary (lifestyle) spending made up %.0f%% of total expenses.", lifestyleRatio))
        }

        if curr.oci != 0 {
            lines.append("Other comprehensive income of \(Money.format(curr.oci)) brought comprehensive income to \(Money.format(comprehensiveIncome)).")
        }

        return lines
    }
}

/// The small signed "+$1,234 (+5.2%)" line under a snapshot total.
private struct DeltaCaption: View {
    let delta: Decimal
    let pct: Double?

    var body: some View {
        HStack(spacing: 4) {
            Spacer()
            Image(systemName: delta >= 0 ? "arrow.up.right" : "arrow.down.right")
                .font(.system(size: 10, weight: .semibold))
            Text(pctSuffix)
                .font(.caption2.weight(.medium).monospacedDigit())
        }
        .foregroundStyle(delta >= 0 ? Color.appGreen : Color.appRed)
    }

    private var pctSuffix: String {
        let base = Money.delta(delta)
        guard let pct else { return base }
        return String(format: "%@ (%@%.1f%%)", base, pct >= 0 ? "+" : "", pct)
    }
}
