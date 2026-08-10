import Foundation
import Observation

/// Backs the Assets tab's cash flow card. Unlike the web — which sums N per-period
/// responses client-side — aggregate here is a single `year=` request, since the
/// backend rolls beginning cash forward correctly for a year scope.
@MainActor
@Observable
final class AssetCashflowViewModel {
    enum Scope: String, CaseIterable, Identifiable {
        case period = "Period"
        case aggregate = "Aggregate"
        var id: String { rawValue }
    }

    typealias State = LoadState<CashflowStatementResponse>

    var state: State = .idle
    var scope: Scope = .period
    var selectedPeriodId: UUID?

    /// Newest-first closed periods, adopted from the parent dashboard.
    private(set) var periods: [Period] = []

    private let api: APIClient
    /// The dashboard's year filter, so aggregate matches the rest of the tab's scope.
    private var year: Int?

    init(api: APIClient) {
        self.api = api
    }

    var selectedPeriod: Period? {
        periods.first { $0.periodId == selectedPeriodId }
    }

    func configure(periods closed: [Period], year: Int?) async {
        let sorted = closed.sorted { $0.periodStart > $1.periodStart }
        let periodsChanged = sorted.map(\.periodId) != periods.map(\.periodId)
        let yearChanged = year != self.year
        periods = sorted
        self.year = year

        guard !periods.isEmpty else {
            state = .error("No closed periods yet.")
            return
        }
        if selectedPeriodId == nil || !periods.contains(where: { $0.periodId == selectedPeriodId }) {
            selectedPeriodId = periods[0].periodId
        }
        if periodsChanged || yearChanged || state == .idle {
            await load()
        }
    }

    func select(scope newScope: Scope) async {
        guard newScope != scope else { return }
        scope = newScope
        await load()
    }

    func select(periodId: UUID) async {
        guard periodId != selectedPeriodId else { return }
        selectedPeriodId = periodId
        await load()
    }

    private func load() async {
        if case .loaded = state {
            // Keep the current figures visible while the next scope loads.
        } else {
            state = .loading
        }

        let endpoint: Endpoint
        switch scope {
        case .period:
            // Returning here while state == .loading would strand the view on a
            // spinner with nothing left to resolve it. Reachable when configure()
            // runs with periods present but the selection cleared.
            guard let selectedPeriodId else {
                state = .error("No period selected")
                return
            }
            endpoint = .cashflowStatement(periodId: selectedPeriodId)
        case .aggregate:
            endpoint = .cashflowStatement(year: year)
        }

        let requestedScope = scope
        do {
            let response = try await api.perform(endpoint, as: CashflowStatementResponse.self)
            guard requestedScope == scope else { return }
            state = .loaded(response)
        } catch let err as APIError {
            if requestedScope == scope { state = .error(err.errorDescription ?? "Failed to load") }
        } catch {
            if requestedScope == scope { state = .error(error.localizedDescription) }
        }
    }
}
