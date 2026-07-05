---
name: "setup-ios"
description: "Create the Xcode project and wire up the API client in ios/"
metadata:
  author: agent-webapp-template
  version: 1.0.0
---

Create the Xcode project inside `ios/`, establish the folder structure, and wire up a reusable API client that talks to the FastAPI backend.

## Steps

### 1. Create the Xcode project
Open Xcode → **File → New → Project → App**.

| Setting | Value |
|---|---|
| **Product name** | your app name |
| **Team** | your Apple developer team |
| **Organization identifier** | reverse-domain (e.g. `com.yourname`) |
| **Interface** | SwiftUI |
| **Language** | Swift |
| **Storage** | None (add later if needed) |

Save the project into `ios/` in the repo root. Xcode creates a `<AppName>.xcodeproj` (or `.xcworkspace` if using Swift Package Manager) and a source folder.

### 2. Establish the folder structure
Inside the Xcode project, create groups mirroring this layout:

```
ios/<AppName>/
├── App/
│   ├── <AppName>App.swift      # @main entry point
│   └── ContentView.swift
├── Core/
│   ├── APIClient.swift         # URLSession wrapper
│   └── Config.swift            # base URL and environment config
├── Features/
│   └── <Feature>/
│       ├── <Feature>View.swift
│       └── <Feature>ViewModel.swift
└── Models/                     # Codable structs matching backend schemas
```

Groups in Xcode are logical — make sure "Create folder references" is checked so the filesystem matches.

### 3. Config (`Core/Config.swift`)
Store the backend base URL here. Use a build scheme environment variable or a `Config.xcconfig` file so the URL differs between debug (local) and release (Render).

```swift
enum Config {
    static var apiBaseURL: URL {
        // Set API_BASE_URL in the active scheme's environment variables.
        let raw = ProcessInfo.processInfo.environment["API_BASE_URL"]
            ?? "http://127.0.0.1:8000"
        return URL(string: raw)!
    }
}
```

For production builds, set `API_BASE_URL` to the Render backend URL in the Release scheme.

### 4. API client (`Core/APIClient.swift`)
A lightweight `URLSession` wrapper. All network calls go through here — no raw `URLSession` calls scattered in views or view models.

```swift
import Foundation

struct APIClient {
    private let base: URL
    private let session: URLSession

    init(base: URL = Config.apiBaseURL, session: URLSession = .shared) {
        self.base = base
        self.session = session
    }

    func get<T: Decodable>(_ path: String) async throws -> T {
        let (data, _) = try await session.data(from: base.appendingPathComponent(path))
        return try JSONDecoder().decode(T.self, from: data)
    }

    func post<Body: Encodable, Response: Decodable>(
        _ path: String, body: Body
    ) async throws -> Response {
        var request = URLRequest(url: base.appendingPathComponent(path))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(body)
        let (data, _) = try await session.data(for: request)
        return try JSONDecoder().decode(Response.self, from: data)
    }
}
```

Extend with `put`, `patch`, and `delete` as needed.

### 5. Add the client to the environment
Inject `APIClient` via SwiftUI's environment so views don't instantiate it directly and tests can swap it.

```swift
// App/<AppName>App.swift
@main
struct MyApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(\.apiClient, APIClient())
        }
    }
}

// Core/APIClientKey.swift
private struct APIClientKey: EnvironmentKey {
    static let defaultValue = APIClient()
}

extension EnvironmentValues {
    var apiClient: APIClient {
        get { self[APIClientKey.self] }
        set { self[APIClientKey.self] = newValue }
    }
}
```

### 6. .gitignore additions
Add to `.gitignore` at the repo root (or create `ios/.gitignore`):

```
ios/DerivedData/
ios/*.xcodeproj/xcuserdata/
ios/*.xcworkspace/xcuserdata/
ios/*.xcworkspace/xcshareddata/swiftpm/
```

## Verification
Run the app in the iOS Simulator. A minimal `ContentView` that calls `apiClient.get("/")` and displays the result confirms the wiring is correct.
