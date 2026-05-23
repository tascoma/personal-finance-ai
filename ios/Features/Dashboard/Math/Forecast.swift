import Foundation

/// Net-worth forecast through end-of-year `targetYear`, mirroring the math in
/// frontend/src/pages/DashboardPage.tsx so iOS and web agree.
///
/// Produces:
/// - a trailing-12-period average projection (lastNW + k * avgMonthlyNet)
/// - a least-squares linear regression projection
struct Forecast {
    struct Point: Identifiable {
        let label: String
        let value: Double?
        let series: Series

        var id: String { "\(series.rawValue)|\(label)" }
    }

    enum Series: String, CaseIterable {
        case historical = "Historical"
        case trailing = "Trailing-avg"
        case regression = "Linear-regression"
    }

    let monthsRemaining: Int
    let avgMonthlyNet: Double
    let slope: Double
    let currentNetWorth: Double
    let trailingEoy: Double
    let regressionEoy: Double
    /// Combined points across historical + both projections, suitable for SwiftUI Charts.
    let points: [Point]

    static func from(
        netWorthSeries: [NetWorthPoint],
        periodBars: [PeriodBarPoint],
        targetYear: Int
    ) -> Forecast? {
        guard !netWorthSeries.isEmpty else { return nil }

        let histLabels = netWorthSeries.map(\.periodLabel)
        let histVals = netWorthSeries.map { $0.netWorth.asDouble }
        let n = histVals.count
        let lastNw = histVals.last ?? 0
        let lastLabel = histLabels.last ?? ""

        guard let (ly, lm) = parseLabel(lastLabel) else { return nil }
        let monthsRemaining = max(0, (targetYear - ly) * 12 + (12 - lm))

        let trailingBars = Array(periodBars.suffix(12))
        let avgMonthlyNet: Double = trailingBars.isEmpty
            ? 0
            : trailingBars.reduce(0.0) { $0 + $1.net.asDouble } / Double(trailingBars.count)

        var slope: Double = 0
        var intercept: Double = lastNw
        if n >= 2 {
            let sumX = Double((n - 1) * n) / 2.0
            let sumY = histVals.reduce(0.0, +)
            let sumXY = histVals.enumerated().reduce(0.0) { acc, e in acc + Double(e.offset) * e.element }
            let sumXX = (0..<n).reduce(0.0) { acc, i in acc + Double(i * i) }
            let denom = Double(n) * sumXX - sumX * sumX
            if denom != 0 {
                slope = (Double(n) * sumXY - sumX * sumY) / denom
                intercept = (sumY - slope * sumX) / Double(n)
            }
        }

        var futureLabels: [String] = []
        for k in 1...max(monthsRemaining, 0) where monthsRemaining > 0 {
            let total = lm + k
            let year = ly + (total - 1) / 12
            let month = ((total - 1) % 12) + 1
            futureLabels.append("\(monthAbbreviations[month - 1]) \(year)")
        }

        let trailingFuture: [Double] = (1...max(monthsRemaining, 1))
            .prefix(monthsRemaining)
            .map { k in lastNw + Double(k) * avgMonthlyNet }
        let regressionFuture: [Double] = (1...max(monthsRemaining, 1))
            .prefix(monthsRemaining)
            .map { k in intercept + slope * Double(n - 1 + k) }

        // Build flat point list. We mirror the web by re-labeling historical
        // points with the same period labels; future labels are YYYY-MM.
        var points: [Point] = []
        for (i, label) in histLabels.enumerated() {
            points.append(Point(label: label, value: histVals[i], series: .historical))
        }
        // Anchor the trailing projection at the last historical point, then extend
        // through futureLabels so the line is continuous at the boundary.
        if !histLabels.isEmpty {
            points.append(Point(label: histLabels.last!, value: lastNw, series: .trailing))
            for (i, label) in futureLabels.enumerated() {
                points.append(Point(label: label, value: trailingFuture[i], series: .trailing))
            }
        }
        if n >= 2 {
            points.append(Point(label: histLabels.last!, value: intercept + slope * Double(n - 1), series: .regression))
            for (i, label) in futureLabels.enumerated() {
                points.append(Point(label: label, value: regressionFuture[i], series: .regression))
            }
        }

        return Forecast(
            monthsRemaining: monthsRemaining,
            avgMonthlyNet: avgMonthlyNet,
            slope: slope,
            currentNetWorth: lastNw,
            trailingEoy: trailingFuture.last ?? lastNw,
            regressionEoy: regressionFuture.last ?? lastNw,
            points: points
        )
    }

    /// Backend produces `"Apr 2026"`-style labels; we also accept `"2026-04"` to
    /// stay tolerant if a future endpoint changes format.
    private static func parseLabel(_ label: String) -> (year: Int, month: Int)? {
        let dashParts = label.split(separator: "-")
        if dashParts.count == 2,
           let y = Int(dashParts[0]),
           let m = Int(dashParts[1]) {
            return (y, m)
        }
        let spaceParts = label.split(separator: " ")
        if spaceParts.count == 2,
           let y = Int(spaceParts[1]),
           let m = monthAbbreviations.firstIndex(of: String(spaceParts[0])) {
            return (y, m + 1)
        }
        return nil
    }

    fileprivate static let monthAbbreviations = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]
}
