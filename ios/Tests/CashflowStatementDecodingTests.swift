import XCTest

/// Decoding coverage for the year-scoped cash flow statement, the response behind
/// the Statements "Aggregate" scope and the Assets tab's waterfall card.
///
/// These matter more than they look: the `KeyedDecodingContainer` extension in
/// JSONCoding makes every `@DecimalString` field default to zero when its key is
/// absent rather than throwing, so a partial or renamed payload renders as `$0.00`
/// instead of failing loudly. The final test pins that behaviour down.
final class CashflowStatementDecodingTests: XCTestCase {

    /// A year-scoped response: `range_label` is the year rather than a period UUID,
    /// and beginning cash is rolled forward from the start of that year.
    private static let yearScoped = #"""
    {
      "range_label": "2026",
      "net_income": "12480.22",
      "noncash_adjustments": [
        {"account_code": 7100, "account_name": "RSU vesting", "sub_category": "Non-cash", "amount": "-4200.00"}
      ],
      "working_capital_changes": [],
      "operating_total": "8280.22",
      "investing": [
        {"account_code": 1500, "account_name": "Brokerage", "sub_category": "Investments", "amount": "-5000.00"}
      ],
      "investing_total": "-5000.00",
      "financing": [],
      "financing_total": "-1200.00",
      "net_change_in_cash": "2080.22",
      "cash_by_account": [],
      "beginning_cash": "40019.78",
      "ending_cash": "42100.00"
    }
    """#

    func testDecodesYearScopedResponse() throws {
        let data = Self.yearScoped.data(using: .utf8)!
        let cf = try JSONDecoder.api().decode(CashflowStatementResponse.self, from: data)

        XCTAssertEqual(cf.rangeLabel, "2026")
        XCTAssertEqual(cf.beginningCash, Decimal(string: "40019.78"))
        XCTAssertEqual(cf.endingCash, Decimal(string: "42100.00"))
        XCTAssertEqual(cf.operatingTotal, Decimal(string: "8280.22"))
        XCTAssertEqual(cf.investingTotal, Decimal(string: "-5000.00"))
        XCTAssertEqual(cf.financingTotal, Decimal(string: "-1200.00"))
        XCTAssertEqual(cf.netChangeInCash, Decimal(string: "2080.22"))
        XCTAssertEqual(cf.noncashAdjustments.count, 1)
        XCTAssertEqual(cf.noncashAdjustments.first?.accountName, "RSU vesting")
        XCTAssertTrue(cf.workingCapitalChanges.isEmpty)
    }

    /// The waterfall card draws Beginning → Operating → Investing → Financing → Ending,
    /// so the three section totals must actually bridge the two cash balances. A
    /// year-scoped aggregate is where this could silently break, since beginning cash
    /// is computed separately from the period lines rather than rolled up from them.
    func testWaterfallStepsReconcileBeginningToEndingCash() throws {
        let data = Self.yearScoped.data(using: .utf8)!
        let cf = try JSONDecoder.api().decode(CashflowStatementResponse.self, from: data)

        let walked = cf.beginningCash + cf.operatingTotal + cf.investingTotal + cf.financingTotal
        XCTAssertEqual(walked, cf.endingCash)
        XCTAssertEqual(cf.netChangeInCash, cf.endingCash - cf.beginningCash)
    }

    /// Missing money keys default to zero rather than throwing. This is deliberate in
    /// JSONCoding, but it means a payload that lost `beginning_cash` renders a
    /// plausible-looking `$0.00` waterfall instead of surfacing an error.
    func testMissingMoneyKeysDefaultToZeroRatherThanThrowing() throws {
        let partial = #"""
        {
          "range_label": "2026",
          "noncash_adjustments": [],
          "working_capital_changes": [],
          "investing": [],
          "financing": [],
          "cash_by_account": []
        }
        """#.data(using: .utf8)!

        let cf = try JSONDecoder.api().decode(CashflowStatementResponse.self, from: partial)
        XCTAssertEqual(cf.beginningCash, 0)
        XCTAssertEqual(cf.endingCash, 0)
        XCTAssertEqual(cf.operatingTotal, 0)
    }
}
