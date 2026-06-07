import XCTest

/// Covers JSONDecoder.api()'s custom date strategy, which must accept both
/// ISO8601 (with Z and fractional seconds) and Python's naive isoformat output
/// (no TZ designator, up to 6 fractional digits).
final class APIDateDecodingTests: XCTestCase {

    private struct Stamp: Codable { let at: Date }

    private func decode(_ raw: String) throws -> Date {
        let json = #"{"at":"\#(raw)"}"#.data(using: .utf8)!
        return try JSONDecoder.api().decode(Stamp.self, from: json).at
    }

    private func components(_ date: Date) -> DateComponents {
        var cal = Calendar(identifier: .iso8601)
        cal.timeZone = TimeZone(secondsFromGMT: 0)!
        return cal.dateComponents([.year, .month, .day, .hour, .minute, .second], from: date)
    }

    func testDateOnly() throws {
        let c = components(try decode("2026-03-15"))
        XCTAssertEqual(c.year, 2026)
        XCTAssertEqual(c.month, 3)
        XCTAssertEqual(c.day, 15)
    }

    func testISO8601WithZ() throws {
        let c = components(try decode("2026-03-15T08:30:00Z"))
        XCTAssertEqual(c.hour, 8)
        XCTAssertEqual(c.minute, 30)
    }

    func testPythonNaiveMicroseconds() throws {
        // datetime.isoformat() with 6 fractional digits and no TZ designator.
        let c = components(try decode("2026-03-15T08:30:00.123456"))
        XCTAssertEqual(c.year, 2026)
        XCTAssertEqual(c.hour, 8)
        XCTAssertEqual(c.second, 0)
    }

    func testUnrecognizedDateThrows() {
        XCTAssertThrowsError(try decode("15/03/2026"))
    }
}
