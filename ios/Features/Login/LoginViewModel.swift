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
        static let password = "saved_password"
    }

    init(api: APIClient, auth: AuthStore) {
        self.api = api
        self.auth = auth
        self.email = KeychainBridge.string(forKey: Keys.email) ?? ""
        self.password = KeychainBridge.string(forKey: Keys.password) ?? ""
    }

    static func clearSavedCredentials() {
        KeychainBridge.delete(forKey: Keys.email)
        KeychainBridge.delete(forKey: Keys.password)
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
            KeychainBridge.setString(password, forKey: Keys.password)
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
