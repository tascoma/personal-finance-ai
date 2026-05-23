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

    private var periodBar: some View {
        HStack {
            if vm.tab == .balanceSheet, case .loaded(let bs) = vm.balanceSheet {
                PeriodPicker(periods: bs.periods, selection: $vm.selectedPeriodId)
            } else {
                PeriodPicker(periods: vm.closedPeriods, selection: $vm.selectedPeriodId)
            }
            Spacer()
            if let label = currentRangeLabel {
                Text(label)
                    .font(.caption)
                    .foregroundStyle(.secondary)
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
        .background(Color(.systemGroupedBackground))
        .refreshable {
            await vm.refresh()
        }
    }

    @ViewBuilder
    private func statePane<T: Equatable, Content: View>(
        _ state: StatementsViewModel.LoadState<T>,
        @ViewBuilder content: (T) -> Content
    ) -> some View {
        switch state {
        case .idle, .loading:
            VStack(spacing: 12) {
                ProgressView()
                Text("Loading…").font(.footnote).foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, minHeight: 200)
        case .error(let message):
            VStack(spacing: 12) {
                Image(systemName: "exclamationmark.triangle")
                    .font(.title)
                    .foregroundStyle(.red)
                Text(message)
                    .font(.callout)
                    .multilineTextAlignment(.center)
                    .foregroundStyle(.secondary)
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
