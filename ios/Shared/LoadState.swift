import Foundation

/// The load lifecycle of a single async-backed screen or tab.
///
/// `StatementsViewModel` already had exactly this as a nested generic while
/// `PeriodTabViewModel` and `AssetCashflowViewModel` each declared their own
/// monomorphic copy of the same four cases. One shared type keeps the view-side
/// `switch` statements uniform.
///
/// `DashboardViewModel` deliberately keeps its own `State`: it overrides `==`
/// so that `.loaded` compares by case rather than by value, avoiding deep
/// equality checks on a large `DashboardResponse` on every comparison.
enum LoadState<T: Equatable>: Equatable {
    case idle
    case loading
    case loaded(T)
    case error(String)

    var value: T? {
        if case .loaded(let v) = self { return v }
        return nil
    }

    var isLoading: Bool {
        if case .loading = self { return true }
        return false
    }
}
