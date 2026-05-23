import Foundation

enum APIError: Error, LocalizedError, Equatable {
    case invalidURL
    case transport(URLError)
    case decoding(String)
    case server(status: Int, detail: String?)
    case unauthorized
    case unknown(String)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid URL."
        case .transport(let err):
            return err.localizedDescription
        case .decoding:
            return "Server returned data the app couldn't parse."
        case .server(_, let detail):
            return detail ?? "Server error."
        case .unauthorized:
            return "Session expired. Please sign in again."
        case .unknown(let msg):
            return msg
        }
    }

    static func == (lhs: APIError, rhs: APIError) -> Bool {
        switch (lhs, rhs) {
        case (.invalidURL, .invalidURL): return true
        case (.unauthorized, .unauthorized): return true
        case (.transport(let l), .transport(let r)): return l.code == r.code
        case (.server(let ls, let ld), .server(let rs, let rd)): return ls == rs && ld == rd
        case (.decoding(let l), .decoding(let r)): return l == r
        case (.unknown(let l), .unknown(let r)): return l == r
        default: return false
        }
    }
}
