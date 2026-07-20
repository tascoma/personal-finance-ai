import SwiftUI

struct AssetInsightsTab: View {
    let data: DashboardResponse
    let closedPeriods: [Period]
    let selectedYear: Int?
    @State private var cashflowVM: AssetCashflowViewModel

    init(data: DashboardResponse, api: APIClient, closedPeriods: [Period], selectedYear: Int?) {
        self.data = data
        self.closedPeriods = closedPeriods
        self.selectedYear = selectedYear
        _cashflowVM = State(initialValue: AssetCashflowViewModel(api: api))
    }

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

    /// First-vs-last growth over whatever's currently in scope, mirroring
    /// `OverviewTab.ytdDelta` — this stays available for any 2+ period scope
    /// (a single calendar year included), instead of requiring a prior year's
    /// baseline that a single-year filter would never have.
    private var ytdGrowth: (pct: Double, delta: Double)? {
        let totals = growthTotals
        guard let first = totals.first, totals.count > 1, first != 0 else { return nil }
        let last = totals[totals.count - 1]
        return ((last - first) / first * 100, last - first)
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

            DashboardCard("Statement of Cash Flows", subtitle: cashflowSubtitle) {
                cashflowContent
            }
        }
        .task(id: TaskKey(periodIds: closedPeriods.map(\.periodId), year: selectedYear)) {
            await cashflowVM.configure(periods: closedPeriods, year: selectedYear)
        }
    }

    /// Re-runs the cash flow fetch when either the period list or the year scope moves.
    private struct TaskKey: Equatable {
        let periodIds: [UUID]
        let year: Int?
    }

    private var cashflowSubtitle: String {
        switch cashflowVM.scope {
        case .period:
            return cashflowVM.selectedPeriod?.label ?? "No closed periods"
        case .aggregate:
            return selectedYear.map { "\($0) · aggregate" } ?? "All years · aggregate"
        }
    }

    @ViewBuilder
    private var cashflowContent: some View {
        VStack(spacing: Space.md) {
            Picker("Scope", selection: cashflowScope) {
                ForEach(AssetCashflowViewModel.Scope.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)

            if cashflowVM.scope == .period && !cashflowVM.periods.isEmpty {
                HStack {
                    PeriodPicker(periods: cashflowVM.periods, selection: cashflowPeriod)
                    Spacer()
                }
            }

            switch cashflowVM.state {
            case .idle, .loading:
                ProgressView().frame(maxWidth: .infinity, minHeight: 220)
            case .error(let message):
                Text(message)
                    .font(.footnote)
                    .foregroundStyle(Color.appTextTertiary)
                    .frame(maxWidth: .infinity, minHeight: 220)
            case .loaded(let cf):
                CashflowWaterfallChart(cashflow: cf)
                CashflowTotalsRow(cashflow: cf)
            }
        }
    }

    private var cashflowScope: Binding<AssetCashflowViewModel.Scope> {
        Binding(
            get: { cashflowVM.scope },
            set: { newValue in Task { await cashflowVM.select(scope: newValue) } }
        )
    }

    private var cashflowPeriod: Binding<UUID?> {
        Binding(
            get: { cashflowVM.selectedPeriodId },
            set: { newValue in
                guard let newValue else { return }
                Task { await cashflowVM.select(periodId: newValue) }
            }
        )
    }
}

/// Operating / Investing / Financing / Net Change under the waterfall.
private struct CashflowTotalsRow: View {
    let cashflow: CashflowStatementResponse

    private var totals: [(label: String, value: Decimal)] {
        [
            ("Operating", cashflow.operatingTotal),
            ("Investing", cashflow.investingTotal),
            ("Financing", cashflow.financingTotal),
            ("Net Change", cashflow.netChangeInCash),
        ]
    }

    var body: some View {
        HStack(alignment: .top, spacing: Space.md) {
            ForEach(totals, id: \.label) { total in
                VStack(alignment: .leading, spacing: 4) {
                    Text(total.label)
                        .eyebrow()
                        .lineLimit(1)
                        .minimumScaleFactor(0.7)
                    Text(Money.compact(total.value))
                        .font(.subheadline.weight(.semibold).monospacedDigit())
                        .foregroundStyle(total.value >= 0 ? Color.appGreen : Color.appRed)
                        .lineLimit(1)
                        .minimumScaleFactor(0.7)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }
}
