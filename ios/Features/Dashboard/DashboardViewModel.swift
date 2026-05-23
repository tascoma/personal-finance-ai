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

    var state: State = .idle

    private let api: APIClient

    init(api: APIClient) {
        self.api = api
    }

    var dashboard: DashboardResponse? {
        if case .loaded(let d) = state { return d }
        return nil
    }

    func load() async {
        if case .loaded = state {
            // Keep current data visible during refetch; fall through.
        } else {
            state = .loading
        }
        do {
            let response = try await api.perform(.dashboard(), as: DashboardResponse.self)
            state = .loaded(response)
            writeWidgetSnapshot(from: response)
        } catch let err as APIError {
            state = .error(err.errorDescription ?? "Failed to load")
        } catch {
            state = .error(error.localizedDescription)
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

    func refresh() async {
        await load()
    }
}
