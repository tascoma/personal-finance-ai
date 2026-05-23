import Foundation
import SwiftUI

enum Money {
    static func format(_ value: Decimal, fractionDigits: Int = 2) -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .currency
        formatter.locale = Locale(identifier: "en_US")
        formatter.maximumFractionDigits = fractionDigits
        formatter.minimumFractionDigits = fractionDigits
        let ns = NSDecimalNumber(decimal: value)
        return formatter.string(from: ns) ?? ns.stringValue
    }

    /// Compact form ($12.3K, $1.4M) for dense chart axes.
    static func compact(_ value: Decimal) -> String {
        let double = NSDecimalNumber(decimal: value).doubleValue
        let abs = Swift.abs(double)
        let sign = double < 0 ? "-" : ""
        if abs >= 1_000_000 {
            return String(format: "%@$%.1fM", sign, abs / 1_000_000)
        } else if abs >= 1_000 {
            return String(format: "%@$%.1fK", sign, abs / 1_000)
        } else {
            return String(format: "%@$%.0f", sign, abs)
        }
    }

    /// Render a delta like `+$1,234.56` / `($1,234.56)` with sign.
    static func delta(_ value: Decimal) -> String {
        let abs = Money.format(Swift.abs(value))
        return value >= 0 ? "+\(abs)" : "(\(abs))"
    }

    static func toDouble(_ value: Decimal) -> Double {
        NSDecimalNumber(decimal: value).doubleValue
    }
}

extension Decimal {
    /// Convenience for chart axes; converts Decimal precision to Double for plotting.
    var asDouble: Double { Money.toDouble(self) }
}
