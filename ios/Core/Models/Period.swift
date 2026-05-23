import Foundation

struct Period: Decodable, Identifiable, Equatable, Hashable {
    let periodId: UUID
    let periodStart: Date
    let periodEnd: Date
    let status: String
    let closedAt: Date?
    let createdAt: Date

    var id: UUID { periodId }

    var isClosed: Bool { status == "closed" }

    enum CodingKeys: String, CodingKey {
        case periodId = "period_id"
        case periodStart = "period_start"
        case periodEnd = "period_end"
        case status
        case closedAt = "closed_at"
        case createdAt = "created_at"
    }
}

extension Period {
    /// "Jan 2026"-style label matching the backend's `period_label` format.
    var label: String {
        Period.labelFormatter.string(from: periodStart)
    }

    private static let labelFormatter: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(secondsFromGMT: 0)
        f.dateFormat = "MMM yyyy"
        return f
    }()
}
