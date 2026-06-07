import XCTest

/// Round-trip coverage for the @DecimalString / @OptionalDecimalString wrappers
/// that bridge the backend's string-encoded Decimals without float drift.
final class DecimalStringTests: XCTestCase {

    private struct Wrap: Codable, Equatable {
        @DecimalString var amount: Decimal
    }

    private struct OptWrap: Codable, Equatable {
        @OptionalDecimalString var amount: Decimal?
    }

    func testDecodesStringToDecimal() throws {
        let json = #"{"amount":"1234.56"}"#.data(using: .utf8)!
        let decoded = try JSONDecoder().decode(Wrap.self, from: json)
        XCTAssertEqual(decoded.amount, Decimal(string: "1234.56"))
    }

    func testEncodesDecimalAsString() throws {
        let value = Wrap(amount: Decimal(string: "1234.56")!)
        let data = try JSONEncoder().encode(value)
        let str = String(data: data, encoding: .utf8)!
        XCTAssertEqual(str, #"{"amount":"1234.56"}"#)
    }

    func testRoundTripPreservesPrecision() throws {
        // A value that would drift if routed through Double.
        let original = Wrap(amount: Decimal(string: "0.1")! + Decimal(string: "0.2")!)
        let data = try JSONEncoder().encode(original)
        let back = try JSONDecoder().decode(Wrap.self, from: data)
        XCTAssertEqual(back.amount, Decimal(string: "0.3"))
        XCTAssertEqual(back, original)
    }

    func testMissingKeyDefaultsToZero() throws {
        let json = "{}".data(using: .utf8)!
        let decoded = try JSONDecoder().decode(Wrap.self, from: json)
        XCTAssertEqual(decoded.amount, 0)
    }

    func testInvalidStringThrows() {
        let json = #"{"amount":"not-a-number"}"#.data(using: .utf8)!
        XCTAssertThrowsError(try JSONDecoder().decode(Wrap.self, from: json))
    }

    func testOptionalDecodesNullToNil() throws {
        let json = #"{"amount":null}"#.data(using: .utf8)!
        let decoded = try JSONDecoder().decode(OptWrap.self, from: json)
        XCTAssertNil(decoded.amount)
    }

    func testOptionalEncodesNilAsNull() throws {
        let value = OptWrap(amount: nil)
        let data = try JSONEncoder().encode(value)
        XCTAssertEqual(String(data: data, encoding: .utf8), #"{"amount":null}"#)
    }

    func testOptionalRoundTripsValue() throws {
        let value = OptWrap(amount: Decimal(string: "-42.00"))
        let data = try JSONEncoder().encode(value)
        let back = try JSONDecoder().decode(OptWrap.self, from: data)
        XCTAssertEqual(back.amount, Decimal(string: "-42.00"))
    }
}
