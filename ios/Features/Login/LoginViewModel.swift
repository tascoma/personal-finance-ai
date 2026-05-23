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

    init(api: APIClient, auth: AuthStore) {
        self.api = api
        self.auth = auth
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
            auth.setSession(token: token.accessToken)
            let user = try await api.perform(.me, as: User.self)
            auth.currentUser = user
            password = ""
        } catch let err as APIError {
            errorMessage = err.errorDescription
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
