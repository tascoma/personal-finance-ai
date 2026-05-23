import Foundation
import Observation

@MainActor
@Observable
final class StatementsViewModel {
    enum LoadState<T: Equatable>: Equatable {
        case idle
        case loading
        case loaded(T)
        case error(String)
    }

    enum Tab: String, CaseIterable, Identifiable {
        case balanceSheet = "Balance"
        case income = "Income"
        case cashflow = "Cash Flow"

        var id: String { rawValue }
    }

    var closedPeriods: [Period] = []
    var selectedPeriodId: UUID? = nil
    var tab: Tab = .balanceSheet

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
            closedPeriods = periods.filter(\.isClosed).sorted { $0.periodStart < $1.periodStart }
            if selectedPeriodId == nil, let latest = closedPeriods.last {
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
                .incomeStatement(periodId: selectedPeriodId),
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
                .cashflowStatement(periodId: selectedPeriodId),
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
