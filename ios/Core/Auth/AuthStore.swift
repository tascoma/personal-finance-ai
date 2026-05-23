import Foundation
import Observation

@MainActor
@Observable
final class AuthStore {
    var accessToken: String?
    var currentUser: User?

    var isAuthenticated: Bool { accessToken != nil }

    func setSession(token: String, user: User? = nil) {
        self.accessToken = token
        if let user = user { self.currentUser = user }
    }

    func clear() {
        self.accessToken = nil
        self.currentUser = nil
    }
}
