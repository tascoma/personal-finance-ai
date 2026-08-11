import Foundation
import Observation

@MainActor
@Observable
final class LoginViewModel {
    var email: String = ""
    var password: String = ""
    var isSubmitting: Bool = false
    var errorMessage: String?

    private let api: APIClient
    private let auth: AuthStore

    private enum Keys {
        static let email = "saved_email"
        /// Retained only so sign-out can evict passwords written by builds that
        /// used to persist them. Nothing writes this key any more.
        static let legacyPassword = "saved_password"
    }

    init(api: APIClient, auth: AuthStore) {
        self.api = api
        self.auth = auth
        self.email = KeychainBridge.string(forKey: Keys.email) ?? ""
        // The password is deliberately not restored. Session resumption is the
        // refresh cookie's job (see RootView.beginBootstrap), and prefilling a
        // SecureField meant a device whose owner declined Face ID — the default —
        // opened straight to a filled password and a live Sign In button.
        KeychainBridge.delete(forKey: Keys.legacyPassword)
    }

    static func clearSavedCredentials() {
        KeychainBridge.delete(forKey: Keys.email)
        KeychainBridge.delete(forKey: Keys.legacyPassword)
    }

    var canSubmit: Bool {
        !isSubmitting && !email.isEmpty && password.count >= 8
    }

    func submit() async {
        guard canSubmit else { return }
        isSubmitting = true
        errorMessage = nil
        defer { isSubmitting = false }

        do {
            let token = try await api.perform(
                .login(email: email, password: password),
                as: TokenResponse.self
            )
            KeychainBridge.setString(email, forKey: Keys.email)
            auth.setSession(token: token.accessToken)
            let user = try await api.perform(.me, as: User.self)
            auth.currentUser = user
            auth.pendingBiometricOptIn = true
        } catch let err as APIError {
            errorMessage = err.errorDescription
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
