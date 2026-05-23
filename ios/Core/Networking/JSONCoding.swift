import Foundation

@propertyWrapper
struct DecimalString: Codable, Equatable, Hashable {
    var wrappedValue: Decimal

    init(wrappedValue: Decimal) { self.wrappedValue = wrappedValue }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        let raw = try container.decode(String.self)
        guard let value = Decimal(string: raw, locale: Locale(identifier: "en_US_POSIX")) else {
            throw DecodingError.dataCorruptedError(
                in: container, debugDescription: "Expected Decimal string, got '\(raw)'"
            )
        }
        self.wrappedValue = value
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(NSDecimalNumber(decimal: wrappedValue).stringValue)
    }
}

@propertyWrapper
struct OptionalDecimalString: Codable, Equatable, Hashable {
    var wrappedValue: Decimal?

    init(wrappedValue: Decimal?) { self.wrappedValue = wrappedValue }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self.wrappedValue = nil
            return
        }
        let raw = try container.decode(String.self)
        self.wrappedValue = Decimal(string: raw, locale: Locale(identifier: "en_US_POSIX"))
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        if let value = wrappedValue {
            try container.encode(NSDecimalNumber(decimal: value).stringValue)
        } else {
            try container.encodeNil()
        }
    }
}

extension KeyedDecodingContainer {
    func decode(_: DecimalString.Type, forKey key: Key) throws -> DecimalString {
        try decodeIfPresent(DecimalString.self, forKey: key) ?? DecimalString(wrappedValue: 0)
    }

    func decode(_: OptionalDecimalString.Type, forKey key: Key) throws -> OptionalDecimalString {
        try decodeIfPresent(OptionalDecimalString.self, forKey: key)
            ?? OptionalDecimalString(wrappedValue: nil)
    }
}

extension JSONDecoder {
    static func api() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let raw = try container.decode(String.self)
            let normalized = APIDateFormatter.normalize(raw)
            if let date = APIDateFormatter.isoFractional.date(from: normalized)
                ?? APIDateFormatter.iso.date(from: normalized)
                ?? APIDateFormatter.naiveFractional.date(from: normalized)
                ?? APIDateFormatter.naivePlain.date(from: normalized)
                ?? APIDateFormatter.dateOnly.date(from: raw) {
                return date
            }
            throw DecodingError.dataCorruptedError(
                in: container, debugDescription: "Unrecognized date: \(raw)"
            )
        }
        return decoder
    }
}

extension JSONEncoder {
    static func api() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }
}

private enum APIDateFormatter {
    static let iso: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()

    static let isoFractional: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    static let dateOnly: DateFormatter = {
        let f = DateFormatter()
        f.calendar = Calendar(identifier: .iso8601)
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(secondsFromGMT: 0)
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    // Python's datetime.isoformat() produces naive timestamps with no TZ
    // designator. ISO8601DateFormatter requires Z/+HHMM; these fall back for that.
    static let naiveFractional: DateFormatter = {
        let f = DateFormatter()
        f.calendar = Calendar(identifier: .iso8601)
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(secondsFromGMT: 0)
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSS"
        return f
    }()

    static let naivePlain: DateFormatter = {
        let f = DateFormatter()
        f.calendar = Calendar(identifier: .iso8601)
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(secondsFromGMT: 0)
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return f
    }()

    // ISO8601DateFormatter only accepts exactly 3 fractional digits. Python's
    // datetime serializes 6 (microseconds). Truncate to 3 so the parser accepts it.
    static func normalize(_ raw: String) -> String {
        guard let dot = raw.firstIndex(of: ".") else { return raw }
        let afterDot = raw.index(after: dot)
        var end = afterDot
        while end < raw.endIndex, raw[end].isNumber {
            end = raw.index(after: end)
        }
        let digits = raw.distance(from: afterDot, to: end)
        if digits <= 3 { return raw }
        let truncated = raw.index(afterDot, offsetBy: 3)
        return String(raw[..<truncated]) + String(raw[end...])
    }
}
