import XCTest

/// Coverage for the net-worth projection math.
///
/// `Forecast` is ~137 lines of arithmetic that drives a headline figure on the
/// dashboard, and it had no tests because the test target only compiled four
/// files. It imports Foundation only, so adding it to the target's sources was
/// enough to make this possible.
final class ForecastTests: XCTestCase {

    // The models are Decodable-only (their money fields use @DecimalString), so
    // build fixtures the same way the app does — through the API decoder.
    private func netWorthSeries(_ pairs: [(String, String)]) throws -> [NetWorthPoint] {
        let json = pairs
            .map { #"{"period_label":"\#($0.0)","net_worth":"\#($0.1)"}"# }
            .joined(separator: ",")
        return try JSONDecoder.api().decode([NetWorthPoint].self, from: Data("[\(json)]".utf8))
    }

    private func periodBars(_ nets: [String]) throws -> [PeriodBarPoint] {
        let json = nets.enumerated()
            .map { #"{"period_label":"P\#($0.offset)","income":"0","expenses":"0","net":"\#($0.element)"}"# }
            .joined(separator: ",")
        return try JSONDecoder.api().decode([PeriodBarPoint].self, from: Data("[\(json)]".utf8))
    }

    func testReturnsNilWithoutHistory() throws {
        XCTAssertNil(Forecast.from(netWorthSeries: [], periodBars: [], targetYear: 2026))
    }

    func testTrailingProjectionExtendsByAverageMonthlyNet() throws {
        // Last close is Oct 2026 → two months remain in the year.
        let series = try netWorthSeries([("Aug 2026", "1000"), ("Sep 2026", "1100"), ("Oct 2026", "1200")])
        let bars = try periodBars(["100", "100", "100"])

        let f = try XCTUnwrap(Forecast.from(netWorthSeries: series, periodBars: bars, targetYear: 2026))

        XCTAssertEqual(f.monthsRemaining, 2)
        XCTAssertEqual(f.avgMonthlyNet, 100, accuracy: 0.0001)
        XCTAssertEqual(f.currentNetWorth, 1200, accuracy: 0.0001)
        // 1200 + 2 * 100
        XCTAssertEqual(f.trailingEoy, 1400, accuracy: 0.0001)
    }

    func testAcceptsTheYYYYMMLabelFormatToo() throws {
        // The backend emits period labels in both shapes; a parser that handled
        // only "Mon YYYY" silently produced monthsRemaining = 0.
        let series = try netWorthSeries([("2026-10", "1200")])
        let bars = try periodBars(["50"])

        let f = try XCTUnwrap(Forecast.from(netWorthSeries: series, periodBars: bars, targetYear: 2026))

        XCTAssertEqual(f.monthsRemaining, 2)
        XCTAssertEqual(f.trailingEoy, 1300, accuracy: 0.0001)
    }

    func testRegressionRecoversAPerfectlyLinearTrend() throws {
        let series = try netWorthSeries([
            ("Jul 2026", "1000"), ("Aug 2026", "1200"),
            ("Sep 2026", "1400"), ("Oct 2026", "1600"),
        ])
        let bars = try periodBars(["200", "200", "200", "200"])

        let f = try XCTUnwrap(Forecast.from(netWorthSeries: series, periodBars: bars, targetYear: 2026))

        XCTAssertEqual(f.slope, 200, accuracy: 0.0001)
        // Fit continues two months past the last point: 1600 + 2 * 200.
        XCTAssertEqual(f.regressionEoy, 2000, accuracy: 0.0001)
    }

    func testNoMonthsRemainingWhenHistoryEndsAtDecember() throws {
        let series = try netWorthSeries([("Dec 2026", "5000")])
        let bars = try periodBars(["100"])

        let f = try XCTUnwrap(Forecast.from(netWorthSeries: series, periodBars: bars, targetYear: 2026))

        XCTAssertEqual(f.monthsRemaining, 0)
        XCTAssertEqual(f.trailingEoy, 5000, accuracy: 0.0001)
        // Only historical points; no projection segments to draw.
        XCTAssertTrue(f.points.allSatisfy { $0.series == .historical || $0.label == "Dec 2026" })
    }

    func testHandlesASingleHistoricalPointWithoutRegression() throws {
        let series = try netWorthSeries([("Nov 2026", "800")])
        let bars = try periodBars(["25"])

        let f = try XCTUnwrap(Forecast.from(netWorthSeries: series, periodBars: bars, targetYear: 2026))

        // n < 2, so the regression stays flat rather than dividing by zero.
        XCTAssertEqual(f.slope, 0, accuracy: 0.0001)
        XCTAssertEqual(f.monthsRemaining, 1)
        XCTAssertEqual(f.trailingEoy, 825, accuracy: 0.0001)
    }
}
