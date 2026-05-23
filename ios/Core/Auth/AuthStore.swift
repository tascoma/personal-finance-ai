import Foundation
import Observation

@MainActor
@Observable
final class AuthStore {
    var accessToken: String?
    var currentUser: User?
    /// Set true after a fresh password sign-in (not auto-resume) so the next view
    /// can offer the biometric opt-in once. Consumer must reset to false.
    var pendingBiometricOptIn: Bool = false

    var isAuthenticated: Bool { accessToken != nil }

    func setSession(token: String, user: User? = nil) {
        self.accessToken = token
        if let user = user { self.currentUser = user }
    }

    func clear() {
        self.accessToken = nil
        self.currentUser = nil
        self.pendingBiometricOptIn = false
    }
}
