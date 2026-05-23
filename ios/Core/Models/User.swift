import Foundation

struct User: Decodable, Identifiable, Equatable {
    let userId: UUID
    let email: String
    let isActive: Bool
    let createdAt: Date

    var id: UUID { userId }

    enum CodingKeys: String, CodingKey {
        case userId = "user_id"
        case email
        case isActive = "is_active"
        case createdAt = "created_at"
    }
}
