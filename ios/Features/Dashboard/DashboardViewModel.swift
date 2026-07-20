import Foundation
import Observation

@MainActor
@Observable
final class DashboardViewModel {
    enum State: Equatable {
        case idle
        case loading
        case loaded(DashboardResponse)
        case error(String)

        static func == (lhs: State, rhs: State) -> Bool {
            switch (lhs, rhs) {
            case (.idle, .idle), (.loading, .loading): return true
            case (.error(let a), .error(let b)): return a == b
            case (.loaded, .loaded): return true   // identity-only; avoids deep equality on big payload
            default: return false
            }
        }
    }

    /// Calendar-year scope for every dashboard visualization.
    enum YearFilter: Equatable, Hashable, Identifiable {
        case year(Int)
        case allTime

        var id: String {
            switch self {
            case .year(let y): return "\(y)"
            case .allTime: return "all"
            }
        }

        var label: String {
            switch self {
            case .year(let y): return "\(y)"
            case .allTime: return "All Years"
            }
        }
    }

    var state: State = .idle
    var closedPeriods: [Period] = []
    var selectedFilter: YearFilter = .allTime

    private let api: APIClient
    private var didBootstrap = false
    /// Responses keyed by filter so switching back to an already-loaded year is
    /// instant. Closed-period data is stable within a session; pull-to-refresh
    /// clears this.
    private var cache: [YearFilter: DashboardResponse] = [:]

    init(api: APIClient) {
        self.api = api
    }

    var dashboard: DashboardResponse? {
        if case .loaded(let d) = state { return d }
        return nil
    }

    /// Years that have at least one closed period, newest first.
    var availableYears: [Int] {
        Set(closedPeriods.map(\.calendarYear)).sorted(by: >)
    }

    /// Menu options: each available year, then "All Years".
    var filterOptions: [YearFilter] {
        availableYears.map { .year($0) } + [.allTime]
    }

    /// Calendar year to scope the dashboard to (nil for all-time). The backend
    /// filters on `period_start.year == year`, so this is authoritative — no need
    /// to translate to period IDs (which risks an empty range reading as "all").
    private func year(for filter: YearFilter) -> Int? {
        if case .year(let y) = filter { return y }
        return nil
    }

    /// The currently-scoped calendar year, or nil for all-time. Tabs that fetch their
    /// own year-scoped data (the Assets cash flow card) read this.
    var selectedYear: Int? { year(for: selectedFilter) }

    /// Fetch periods, pick the default year (current year if present, else the
    /// most recent year with data, else all-time), load it, then warm the cache
    /// for the remaining years in the background so later switches are instant.
    func bootstrap() async {
        if didBootstrap {
            await showFilter(selectedFilter, updateWidget: false)
            return
        }
        didBootstrap = true
        await loadPeriods()

        let currentYear = Calendar(identifier: .gregorian).component(.year, from: Date())
        if availableYears.contains(currentYear) {
            selectedFilter = .year(currentYear)
        } else if let latest = availableYears.first {
            selectedFilter = .year(latest)
        } else {
            selectedFilter = .allTime
        }
        await fetchAndShow(selectedFilter, updateWidget: true)
        prefetchOthers()
    }

    func select(_ filter: YearFilter) async {
        guard filter != selectedFilter else { return }
        selectedFilter = filter
        await showFilter(filter, updateWidget: false)
    }

    func refresh() async {
        cache.removeAll()
        await loadPeriods()
        await fetchAndShow(selectedFilter, updateWidget: true)
        prefetchOthers()
    }

    /// Show a filter from cache instantly when possible; otherwise fetch it.
    private func showFilter(_ filter: YearFilter, updateWidget: Bool) async {
        if let cached = cache[filter] {
            state = .loaded(cached)
            return
        }
        await fetchAndShow(filter, updateWidget: updateWidget)
    }

    private func fetchAndShow(_ filter: YearFilter, updateWidget: Bool) async {
        if case .loaded = state {
            // Keep current data visible during refetch; fall through.
        } else {
            state = .loading
        }
        do {
            let response = try await fetch(filter)
            cache[filter] = response
            // Guard against out-of-order responses: only apply if still selected.
            guard filter == selectedFilter else { return }
            state = .loaded(response)
            if updateWidget { writeWidgetSnapshot(from: response) }
        } catch let err as APIError {
            if filter == selectedFilter { state = .error(err.errorDescription ?? "Failed to load") }
        } catch {
            if filter == selectedFilter { state = .error(error.localizedDescription) }
        }
    }

    private func fetch(_ filter: YearFilter) async throws -> DashboardResponse {
        try await api.perform(.dashboard(year: year(for: filter)), as: DashboardResponse.self)
    }

    /// Warm the cache for every other filter option in the background.
    private func prefetchOthers() {
        let options = filterOptions
        Task { [weak self] in
            guard let self else { return }
            for option in options where self.cache[option] == nil {
                if let response = try? await self.fetch(option) {
                    self.cache[option] = response
                }
            }
        }
    }

    private func loadPeriods() async {
        do {
            let all = try await api.perform(.periods, as: [Period].self)
            closedPeriods = all.filter { $0.status == "closed" }
        } catch {
            closedPeriods = []
        }
    }

    private func writeWidgetSnapshot(from response: DashboardResponse) {
        let lastBar = response.periodBars.last
        let snapshot = WidgetSnapshot(
            netWorth: response.netWorth,
            totalAssets: response.totalAssets,
            totalLiabilities: response.totalLiabilities,
            monthlyIncome: lastBar?.income ?? 0,
            monthlyExpenses: lastBar?.expenses ?? 0,
            monthlyNet: lastBar?.net ?? 0,
            periodLabel: lastBar?.periodLabel ?? "—",
            capturedAt: Date()
        )
        SharedContainer.writeSnapshot(snapshot)
    }
}
