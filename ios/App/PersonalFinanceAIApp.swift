import SwiftUI

@main
struct PersonalFinanceAIApp: App {
    @State private var env = AppEnvironment()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(env)
        }
    }
}
