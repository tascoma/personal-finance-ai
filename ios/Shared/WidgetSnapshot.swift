import Foundation

/// Compact dashboard data the widget renders. Captured by the main app on
/// every successful /dashboard fetch and written to the shared App Group
/// container; the widget only ever READS from disk and never makes network
/// calls (keeps the extension within its tight memory/time budget and avoids
/// shipping auth tokens into the widget process).
struct WidgetSnapshot: Codable, Equatable {
    var netWorth: Decimal
    var totalAssets: Decimal
    var totalLiabilities: Decimal
    var monthlyIncome: Decimal
    var monthlyExpenses: Decimal
    var monthlyNet: Decimal
    /// "Apr 2026"-style label for the period the monthly figures cover.
    var periodLabel: String
    /// When the snapshot was captured. Widget can show "as of" timestamp.
    var capturedAt: Date

    static let placeholder = WidgetSnapshot(
        netWorth: 276_815,
        totalAssets: 575_175,
        totalLiabilities: 298_360,
        monthlyIncome: 9_059,
        monthlyExpenses: 8_799,
        monthlyNet: 260,
        periodLabel: "Apr 2026",
        capturedAt: Date()
    )
}
