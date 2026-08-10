import SwiftUI

struct StatementsView: View {
    @State private var vm: StatementsViewModel

    init(api: APIClient) {
        _vm = State(initialValue: StatementsViewModel(api: api))
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 12) {
                tabBar
                if let scope = scopeBinding {
                    scopeBar(scope)
                }
                periodBar
                Divider()
                content
            }
            .navigationTitle("Statements")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) { SignOutMenuButton() }
            }
        }
        .task { await vm.loadCurrentTab() }
    }

    private var tabBar: some View {
        Picker("Statement", selection: $vm.tab) {
            ForEach(StatementsViewModel.Tab.allCases) { tab in
                Text(tab.rawValue).tag(tab)
            }
        }
        .pickerStyle(.segmented)
        .padding(.horizontal)
        .onChange(of: vm.tab) { _, _ in
            Task { await vm.reloadForTab() }
        }
    }

    /// The balance sheet pivot spans all periods, so it has no period/aggregate choice.
    private var scopeBinding: Binding<StatementsViewModel.Scope>? {
        switch vm.tab {
        case .balanceSheet: return nil
        case .income: return $vm.incomeScope
        case .cashflow: return $vm.cashflowScope
        }
    }

    private func scopeBar(_ scope: Binding<StatementsViewModel.Scope>) -> some View {
        Picker("Scope", selection: scope) {
            ForEach(StatementsViewModel.Scope.allCases) { Text($0.rawValue).tag($0) }
        }
        .pickerStyle(.segmented)
        .padding(.horizontal)
        .onChange(of: scope.wrappedValue) { _, _ in
            Task { await vm.reloadAfterScopeChange() }
        }
    }

    /// Aggregate statements are year-scoped, so the period picker doesn't apply.
    private var showsPeriodPicker: Bool {
        switch vm.tab {
        case .balanceSheet: return true
        case .income: return vm.incomeScope == .period
        case .cashflow: return vm.cashflowScope == .period
        }
    }

    private var periodBar: some View {
        HStack {
            if showsPeriodPicker {
                if vm.tab == .balanceSheet, case .loaded(let bs) = vm.balanceSheet {
                    PeriodPicker(periods: bs.periods, selection: $vm.selectedPeriodId)
                } else {
                    PeriodPicker(periods: vm.closedPeriods, selection: $vm.selectedPeriodId)
                }
            }
            Spacer()
            if let label = currentRangeLabel {
                Text(label)
                    .font(.caption)
                    .foregroundStyle(Color.appTextSecondary)
            }
        }
        .padding(.horizontal)
        .onChange(of: vm.selectedPeriodId) { _, _ in
            Task { await vm.reloadAfterPeriodChange() }
        }
    }

    private var currentRangeLabel: String? {
        switch vm.tab {
        case .balanceSheet:
            return nil
        case .income:
            if case .loaded(let inc) = vm.income { return inc.rangeLabel.contains("-") ? nil : inc.rangeLabel }
            return nil
        case .cashflow:
            if case .loaded(let cf) = vm.cashflow { return cf.rangeLabel.contains("-") ? nil : cf.rangeLabel }
            return nil
        }
    }

    @ViewBuilder
    private var content: some View {
        ScrollView {
            VStack(spacing: 16) {
                switch vm.tab {
                case .balanceSheet:
                    statePane(vm.balanceSheet) { bs in
                        BalanceSheetView(response: bs, selectedPeriodId: vm.selectedPeriodId)
                    }
                case .income:
                    statePane(vm.income) { inc in
                        IncomeStatementView(response: inc)
                    }
                case .cashflow:
                    statePane(vm.cashflow) { cf in
                        CashflowStatementView(response: cf)
                    }
                }
            }
            .padding(.horizontal)
            .padding(.bottom, 24)
        }
        .scrollIndicators(.hidden)
        .background(Color.appBackground)
        .refreshable {
            await vm.refresh()
        }
    }

    @ViewBuilder
    private func statePane<T: Equatable, Content: View>(
        _ state: LoadState<T>,
        @ViewBuilder content: (T) -> Content
    ) -> some View {
        switch state {
        case .idle, .loading:
            VStack(spacing: 12) {
                ProgressView()
                Text("Loading…").font(.footnote).foregroundStyle(Color.appTextSecondary)
            }
            .frame(maxWidth: .infinity, minHeight: 200)
        case .error(let message):
            VStack(spacing: 12) {
                Image(systemName: "exclamationmark.triangle")
                    .font(.title)
                    .foregroundStyle(Color.appRed)
                Text(message)
                    .font(.callout)
                    .multilineTextAlignment(.center)
                    .foregroundStyle(Color.appTextSecondary)
                Button("Try again") {
                    Task { await vm.refresh() }
                }
                .buttonStyle(.borderedProminent)
            }
            .frame(maxWidth: .infinity, minHeight: 200)
        case .loaded(let value):
            content(value)
        }
    }
}
