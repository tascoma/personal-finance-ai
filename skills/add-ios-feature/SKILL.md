---
name: "add-ios-feature"
description: "Add a new screen or feature to the iOS app"
metadata:
  author: agent-webapp-template
  version: 1.0.0
---

Add a new screen or feature to the iOS app following the MVVM pattern. Replace `<Feature>` with the actual feature name throughout.

## Pattern
Views own layout and user interaction only. All data fetching, state, and business logic live in the `ViewModel`. The `APIClient` is injected via the environment — never instantiated inside a view or view model directly.

## Steps

### 1. Model (`Models/<Feature>.swift`)
Define `Codable` structs that mirror the backend Pydantic schemas. Field names must match the JSON keys returned by the API (use `CodingKeys` if the backend uses snake_case and you want camelCase in Swift).

```swift
struct Feature: Codable, Identifiable {
    let id: Int
    let name: String
    // match backend schema field names exactly, or use CodingKeys
}
```

### 2. ViewModel (`Features/<Feature>/<Feature>ViewModel.swift`)
Own all state and async logic here. Mark it `@MainActor` so published state updates always happen on the main thread.

```swift
import Foundation

@MainActor
final class FeatureViewModel: ObservableObject {
    @Published var items: [Feature] = []
    @Published var isLoading = false
    @Published var errorMessage: String?

    private let client: APIClient

    init(client: APIClient) {
        self.client = client
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            items = try await client.get("/features/")
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
```

### 3. View (`Features/<Feature>/<Feature>View.swift`)
Keep the view thin — layout, navigation, and forwarding user actions to the view model.

```swift
import SwiftUI

struct FeatureView: View {
    @StateObject private var vm: FeatureViewModel
    @Environment(\.apiClient) private var client

    init(client: APIClient) {
        _vm = StateObject(wrappedValue: FeatureViewModel(client: client))
    }

    var body: some View {
        List(vm.items) { item in
            Text(item.name)
        }
        .navigationTitle("Features")
        .task { await vm.load() }
        .overlay {
            if vm.isLoading { ProgressView() }
        }
        .alert("Error", isPresented: .constant(vm.errorMessage != nil)) {
            Button("OK") { vm.errorMessage = nil }
        } message: {
            Text(vm.errorMessage ?? "")
        }
    }
}
```

### 4. Register in navigation
Add the new view to your app's navigation stack or tab bar in `ContentView.swift` or the relevant parent view.

```swift
NavigationLink("Features") {
    FeatureView(client: client)
}
```

Or as a tab:

```swift
FeatureView(client: client)
    .tabItem { Label("Features", systemImage: "list.bullet") }
```

### 5. Backend route check
Confirm the FastAPI route the view model calls exists and returns the expected schema. If it doesn't, use `/add-resource` to create it first.

### 6. Test the view model
Write a unit test using a mock `APIClient` (or a `URLProtocol` stub) that exercises the `load()` path and error handling — no Simulator needed.

```swift
final class FeatureViewModelTests: XCTestCase {
    func testLoadPopulatesItems() async throws {
        let client = APIClient(base: testServerURL, session: stubbedSession)
        let vm = await FeatureViewModel(client: client)
        await vm.load()
        let count = await vm.items.count
        XCTAssertGreaterThan(count, 0)
    }
}
```

## Verification
Run in the Simulator and walk through the golden path: data loads, errors surface correctly, and navigation works. Check Xcode's console for any decoding errors — these usually mean a field name mismatch between the Swift model and the backend schema.
