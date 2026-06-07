import XCTest

final class MoneyTests: XCTestCase {

    func testFormatAddsCurrencyAndTwoDecimals() {
        XCTAssertEqual(Money.format(Decimal(string: "1234.5")!), "$1,234.50")
        XCTAssertEqual(Money.format(Decimal(0)), "$0.00")
    }

    func testFormatRespectsFractionDigits() {
        XCTAssertEqual(Money.format(Decimal(string: "1234.567")!, fractionDigits: 0), "$1,235")
    }

    func testCompactScalesThousandsAndMillions() {
        XCTAssertEqual(Money.compact(Decimal(950)), "$950")
        XCTAssertEqual(Money.compact(Decimal(12_300)), "$12.3K")
        XCTAssertEqual(Money.compact(Decimal(1_400_000)), "$1.4M")
        XCTAssertEqual(Money.compact(Decimal(-2_500)), "-$2.5K")
    }

    func testDeltaSignsValues() {
        XCTAssertEqual(Money.delta(Decimal(string: "1234.56")!), "+$1,234.56")
        XCTAssertEqual(Money.delta(Decimal(string: "-1234.56")!), "($1,234.56)")
        XCTAssertEqual(Money.delta(Decimal(0)), "+$0.00")
    }

    func testToDoubleAndAsDouble() {
        XCTAssertEqual(Money.toDouble(Decimal(string: "12.5")!), 12.5, accuracy: 1e-9)
        XCTAssertEqual(Decimal(string: "12.5")!.asDouble, 12.5, accuracy: 1e-9)
    }
}
