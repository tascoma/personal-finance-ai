import Foundation
import Observation

@MainActor
@Observable
final class AppEnvironment {
    let baseURL: URL
    let session: URLSession
    let auth: AuthStore
    let refresher: TokenRefresher
    let api: APIClient
    let biometric: BiometricController
    let push: PushNotificationsController

    init() {
        self.baseURL = AppEnvironment.loadBaseURL()

        let config = URLSessionConfiguration.default
        config.httpShouldSetCookies = true
        config.httpCookieAcceptPolicy = .always
        config.httpCookieStorage = HTTPCookieStorage.shared
        config.timeoutIntervalForRequest = 90
        self.session = URLSession(configuration: config)

        let auth = AuthStore()
        let refresher = TokenRefresher()
        self.auth = auth
        self.refresher = refresher
        self.api = APIClient(baseURL: baseURL, session: session, auth: auth, refresher: refresher)
        self.biometric = BiometricController()
        self.push = PushNotificationsController()
        self.push.configure(api: self.api)
    }

    private static func loadBaseURL() -> URL {
        let raw = (Bundle.main.object(forInfoDictionaryKey: "API_BASE_URL") as? String) ?? ""
        let trimmed = raw.trimmingCharacters(in: .whitespaces)
        let fallback = "http://127.0.0.1:8000"
        let source = trimmed.isEmpty ? fallback : (trimmed.hasSuffix("/") ? String(trimmed.dropLast()) : trimmed)
        if let url = URL(string: source + "/api/v1"), url.scheme != nil, url.host != nil {
            return url
        }
        // Fall back rather than fatalError: a typo in Release.xcconfig would
        // otherwise ship a crash-on-launch to the App Store, and the local
        // fallback above is already the sane default for a malformed value.
        assertionFailure("Invalid API_BASE_URL: '\(raw)' (resolved to '\(source)')")
        return URL(string: fallback + "/api/v1")!
    }
}
