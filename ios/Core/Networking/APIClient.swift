import Foundation

struct APIClient {
    let baseURL: URL
    let session: URLSession
    let auth: AuthStore
    let refresher: TokenRefresher

    func perform<T: Decodable>(_ endpoint: Endpoint, as: T.Type) async throws -> T {
        let data = try await performData(endpoint)
        do {
            return try JSONDecoder.api().decode(T.self, from: data)
        } catch {
            throw APIError.decoding(String(describing: error))
        }
    }

    func perform(_ endpoint: Endpoint) async throws {
        _ = try await performData(endpoint)
    }

    private func performData(_ endpoint: Endpoint) async throws -> Data {
        var req = endpoint.urlRequest(baseURL: baseURL)
        if endpoint.requiresAuth, let token = await auth.accessToken {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let (data, response) = try await send(req)
        guard let http = response as? HTTPURLResponse else {
            throw APIError.unknown("Bad response")
        }

        guard http.statusCode == 401, endpoint.requiresAuth else {
            return try handle(data: data, http: http)
        }

        // 401 on an auth-required endpoint: try refresh once, then retry.
        let newToken: String
        do {
            newToken = try await refresher.refresh(baseURL: baseURL, session: session)
        } catch {
            await MainActor.run { auth.clear() }
            throw APIError.unauthorized
        }
        await MainActor.run { auth.accessToken = newToken }

        var retry = endpoint.urlRequest(baseURL: baseURL)
        retry.setValue("Bearer \(newToken)", forHTTPHeaderField: "Authorization")
        let (data2, resp2) = try await send(retry)
        guard let http2 = resp2 as? HTTPURLResponse else {
            throw APIError.unknown("Bad response")
        }
        // A 401 that survives a *successful* refresh means the session is
        // genuinely dead (e.g. the server bumped token_version). Only the
        // refresh-failure path above used to clear auth, so this case left the
        // app believing it was signed in: RootView re-evaluates auth at
        // bootstrap only, so every subsequent pull-to-refresh showed "Session
        // expired" forever with no route back to the login screen.
        if http2.statusCode == 401 {
            await MainActor.run { auth.clear() }
            throw APIError.unauthorized
        }
        return try handle(data: data2, http: http2)
    }

    private func handle(data: Data, http: HTTPURLResponse) throws -> Data {
        if (200..<300).contains(http.statusCode) {
            return data
        }
        if http.statusCode == 401 {
            throw APIError.unauthorized
        }
        let detail = extractDetail(from: data)
        throw APIError.server(status: http.statusCode, detail: detail)
    }

    private func extractDetail(from data: Data) -> String? {
        if let dict = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let detail = dict["detail"] as? String {
            return detail
        }
        return nil
    }

    private func send(_ req: URLRequest) async throws -> (Data, URLResponse) {
        do {
            return try await session.data(for: req)
        } catch let err as URLError {
            throw APIError.transport(err)
        } catch {
            throw APIError.unknown(error.localizedDescription)
        }
    }
}
