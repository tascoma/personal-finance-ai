import Foundation
import Observation

/// Drives the dashboard's Period tab: a single closed period's snapshot, plus the
/// prior period for deltas and that period's cash flow statement.
@MainActor
@Observable
final class PeriodTabViewModel {
    /// One period's fully-loaded snapshot. `previous` is nil for the oldest period,
    /// which is what suppresses the delta copy rather than showing a bogus swing.
    struct Snapshot: Equatable {
        let current: DashboardResponse
        let previous: DashboardResponse?
        let cashflow: CashflowStatementResponse

        static func == (lhs: Snapshot, rhs: Snapshot) -> Bool {
            lhs.cashflow.rangeLabel == rhs.cashflow.rangeLabel
        }
    }

    typealias State = LoadState<Snapshot>

    var state: State = .idle
    var selectedPeriodId: UUID?

    /// Newest-first, matching `DashboardViewModel`'s ordering and the web's. The
    /// "prior period" for deltas is therefore the *next* element, not the previous one.
    private(set) var periods: [Period] = []

    private let api: APIClient
    private var cache: [UUID: Snapshot] = [:]

    init(api: APIClient) {
        self.api = api
    }

    var selectedPeriod: Period? {
        periods.first { $0.periodId == selectedPeriodId }
    }

    /// Adopt the closed periods the parent dashboard already fetched, defaulting the
    /// selection to the newest. Re-entrant: later calls only refresh the list.
    func setPeriods(_ closed: [Period]) async {
        periods = closed.sorted { $0.periodStart > $1.periodStart }
        guard !periods.isEmpty else {
            state = .error("No closed periods yet.")
            return
        }
        if selectedPeriodId == nil || !periods.contains(where: { $0.periodId == selectedPeriodId }) {
            selectedPeriodId = periods[0].periodId
            await load()
        }
    }

    func select(_ periodId: UUID) async {
        guard periodId != selectedPeriodId else { return }
        selectedPeriodId = periodId
        if let cached = cache[periodId] {
            state = .loaded(cached)
            return
        }
        await load()
    }

    func refresh() async {
        cache.removeAll()
        await load()
    }

    private func load() async {
        guard let periodId = selectedPeriodId else { return }
        if case .loaded = state {
            // Keep the current snapshot visible while the next one loads.
        } else {
            state = .loading
        }

        // Periods are newest-first, so the prior period sits one index later.
        let priorId: UUID? = periods
            .firstIndex { $0.periodId == periodId }
            .flatMap { $0 + 1 < periods.count ? periods[$0 + 1].periodId : nil }

        do {
            async let current = api.perform(.dashboard(periodId: periodId), as: DashboardResponse.self)
            async let cashflow = api.perform(.cashflowStatement(periodId: periodId), as: CashflowStatementResponse.self)
            async let previous = fetchPrevious(priorId)

            let snapshot = Snapshot(
                current: try await current,
                previous: try await previous,
                cashflow: try await cashflow
            )
            cache[periodId] = snapshot
            // Guard against out-of-order responses: only apply if still selected.
            guard periodId == selectedPeriodId else { return }
            state = .loaded(snapshot)
        } catch let err as APIError {
            if periodId == selectedPeriodId { state = .error(err.errorDescription ?? "Failed to load") }
        } catch {
            if periodId == selectedPeriodId { state = .error(error.localizedDescription) }
        }
    }

    /// The prior period is only used for deltas, so a failure here degrades to
    /// "no prior period" rather than failing the whole snapshot.
    private func fetchPrevious(_ periodId: UUID?) async -> DashboardResponse? {
        guard let periodId else { return nil }
        return try? await api.perform(.dashboard(periodId: periodId), as: DashboardResponse.self)
    }
}
