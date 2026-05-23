import Foundation

actor TokenRefresher {
    private var inFlight: Task<String, Error>?

    func refresh(baseURL: URL, session: URLSession) async throws -> String {
        if let existing = inFlight {
            return try await existing.value
        }
        let task = Task<String, Error> {
            try await Self.performRefresh(baseURL: baseURL, session: session)
        }
        inFlight = task
        defer { inFlight = nil }
        return try await task.value
    }

    private static func performRefresh(baseURL: URL, session: URLSession) async throws -> String {
        let req = Endpoint.refresh.urlRequest(baseURL: baseURL)
        let (data, response) = try await session.data(for: req)
        guard let http = response as? HTTPURLResponse else {
            throw APIError.unknown("Bad response")
        }
        if http.statusCode == 401 {
            throw APIError.unauthorized
        }
        guard (200..<300).contains(http.statusCode) else {
            throw APIError.server(status: http.statusCode, detail: nil)
        }
        do {
            return try JSONDecoder.api().decode(TokenResponse.self, from: data).accessToken
        } catch {
            throw APIError.decoding(String(describing: error))
        }
    }
}
