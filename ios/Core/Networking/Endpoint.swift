import Foundation

struct Endpoint {
    let method: String
    let path: String
    let body: Data?
    let requiresAuth: Bool

    private init(method: String, path: String, body: Data? = nil, requiresAuth: Bool) {
        self.method = method
        self.path = path
        self.body = body
        self.requiresAuth = requiresAuth
    }

    static func login(email: String, password: String) -> Endpoint {
        struct Body: Encodable { let email: String; let password: String }
        let body = try? JSONEncoder.api().encode(Body(email: email, password: password))
        return Endpoint(method: "POST", path: "/auth/login", body: body, requiresAuth: false)
    }

    static let refresh = Endpoint(method: "POST", path: "/auth/refresh", requiresAuth: false)
    static let logout = Endpoint(method: "POST", path: "/auth/logout", requiresAuth: false)
    static let me = Endpoint(method: "GET", path: "/auth/me", requiresAuth: true)
    static let periods = Endpoint(method: "GET", path: "/periods", requiresAuth: true)

    static func dashboard(year: Int? = nil, fromPeriodId: UUID? = nil, toPeriodId: UUID? = nil) -> Endpoint {
        var query: [String] = []
        if let year { query.append("year=\(year)") }
        if let from = fromPeriodId { query.append("from_period_id=\(from.uuidString.lowercased())") }
        if let to = toPeriodId { query.append("to_period_id=\(to.uuidString.lowercased())") }
        let suffix = query.isEmpty ? "" : "?\(query.joined(separator: "&"))"
        return Endpoint(method: "GET", path: "/dashboard\(suffix)", requiresAuth: true)
    }

    static let balanceSheet = Endpoint(
        method: "GET", path: "/statements/balance-sheet", requiresAuth: true
    )

    static func incomeStatement(periodId: UUID? = nil) -> Endpoint {
        let suffix = periodId.map { "?period_id=\($0.uuidString.lowercased())" } ?? ""
        return Endpoint(method: "GET", path: "/statements/income\(suffix)", requiresAuth: true)
    }

    static func cashflowStatement(periodId: UUID? = nil) -> Endpoint {
        let suffix = periodId.map { "?period_id=\($0.uuidString.lowercased())" } ?? ""
        return Endpoint(method: "GET", path: "/statements/cashflow\(suffix)", requiresAuth: true)
    }

    static func registerDeviceToken(apnsToken: String, bundleId: String) -> Endpoint {
        struct Body: Encodable {
            let apns_token: String
            let bundle_id: String
        }
        let body = try? JSONEncoder.api().encode(Body(apns_token: apnsToken, bundle_id: bundleId))
        return Endpoint(method: "POST", path: "/auth/device-tokens", body: body, requiresAuth: true)
    }

    static func deleteDeviceToken(apnsToken: String) -> Endpoint {
        Endpoint(method: "DELETE", path: "/auth/device-tokens/\(apnsToken)", requiresAuth: true)
    }

    func urlRequest(baseURL: URL) -> URLRequest {
        let fullURL = URL(string: baseURL.absoluteString + path) ?? baseURL
        var req = URLRequest(url: fullURL)
        req.httpMethod = method
        req.httpShouldHandleCookies = true
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        if let body = body {
            req.httpBody = body
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        return req
    }
}
