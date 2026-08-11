import Foundation
import Observation

@MainActor
@Observable
final class StatementsViewModel {
    enum Tab: String, CaseIterable, Identifiable {
        case balanceSheet = "Balance"
        case income = "Income"
        case cashflow = "Cash Flow"

        var id: String { rawValue }
    }

    /// Whether a statement covers the selected period or a whole calendar year.
    /// Aggregate is a single `year=` request — the backend rolls beginning cash
    /// forward to the start of that year rather than starting from zero.
    enum Scope: String, CaseIterable, Identifiable {
        case period = "Period"
        case aggregate = "Aggregate"

        var id: String { rawValue }
    }

    var closedPeriods: [Period] = []
    var selectedPeriodId: UUID? = nil
    var tab: Tab = .balanceSheet
    var incomeScope: Scope = .period
    var cashflowScope: Scope = .period

    /// Aggregate scopes to the most recent closed year, not all-time — otherwise it
    /// silently blends in unrelated activity from long-closed prior years.
    var aggregateYear: Int? { closedPeriods.last?.calendarYear }

    var balanceSheet: LoadState<BalanceSheetPivotResponse> = .idle
    var income: LoadState<IncomeStatementResponse> = .idle
    var cashflow: LoadState<CashflowStatementResponse> = .idle
    var periodsError: String? = nil

    private let api: APIClient

    init(api: APIClient) {
        self.api = api
    }

    func loadPeriods() async {
        do {
            let periods = try await api.perform(.periods, as: [Period].self)
            // Newest-first, matching PeriodTabViewModel, AssetCashflowViewModel
            // and the web app. This list feeds the same PeriodPicker as those
            // two, so sorting ascending here meant the picker listed periods in
            // the opposite order depending on which tab you opened it from.
            closedPeriods = periods.filter(\.isClosed).sorted { $0.periodStart > $1.periodStart }
            if selectedPeriodId == nil, let latest = closedPeriods.first {
                selectedPeriodId = latest.periodId
            }
            periodsError = nil
        } catch let err as APIError {
            periodsError = err.errorDescription
        } catch {
            periodsError = error.localizedDescription
        }
    }

    func loadCurrentTab() async {
        await loadPeriods()
        switch tab {
        case .balanceSheet: await loadBalanceSheet()
        case .income: await loadIncome()
        case .cashflow: await loadCashflow()
        }
    }

    func reloadForTab() async {
        switch tab {
        case .balanceSheet:
            if case .loaded = balanceSheet { return }
            await loadBalanceSheet()
        case .income:
            if case .loaded = income { return }
            await loadIncome()
        case .cashflow:
            if case .loaded = cashflow { return }
            await loadCashflow()
        }
    }

    func reloadAfterPeriodChange() async {
        switch tab {
        case .balanceSheet: break  // pivot already includes all periods; no refetch needed
        // An aggregate statement is year-scoped, so the period selection doesn't affect it.
        case .income: if incomeScope == .period { await loadIncome() }
        case .cashflow: if cashflowScope == .period { await loadCashflow() }
        }
    }

    func reloadAfterScopeChange() async {
        switch tab {
        case .balanceSheet: break
        case .income: await loadIncome()
        case .cashflow: await loadCashflow()
        }
    }

    func refresh() async {
        switch tab {
        case .balanceSheet: await loadBalanceSheet()
        case .income: await loadIncome()
        case .cashflow: await loadCashflow()
        }
    }

    private func loadBalanceSheet() async {
        if case .loaded = balanceSheet {} else { balanceSheet = .loading }
        do {
            let response = try await api.perform(.balanceSheet, as: BalanceSheetPivotResponse.self)
            balanceSheet = .loaded(response)
        } catch let err as APIError {
            balanceSheet = .error(err.errorDescription ?? "Failed to load")
        } catch {
            balanceSheet = .error(error.localizedDescription)
        }
    }

    private func loadIncome() async {
        if case .loaded = income {} else { income = .loading }
        do {
            let response = try await api.perform(
                incomeScope == .aggregate
                    ? .incomeStatement(year: aggregateYear)
                    : .incomeStatement(periodId: selectedPeriodId),
                as: IncomeStatementResponse.self
            )
            income = .loaded(response)
        } catch let err as APIError {
            income = .error(err.errorDescription ?? "Failed to load")
        } catch {
            income = .error(error.localizedDescription)
        }
    }

    private func loadCashflow() async {
        if case .loaded = cashflow {} else { cashflow = .loading }
        do {
            let response = try await api.perform(
                cashflowScope == .aggregate
                    ? .cashflowStatement(year: aggregateYear)
                    : .cashflowStatement(periodId: selectedPeriodId),
                as: CashflowStatementResponse.self
            )
            cashflow = .loaded(response)
        } catch let err as APIError {
            cashflow = .error(err.errorDescription ?? "Failed to load")
        } catch {
            cashflow = .error(error.localizedDescription)
        }
    }
}
