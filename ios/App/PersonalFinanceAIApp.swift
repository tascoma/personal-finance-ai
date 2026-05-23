import SwiftUI

@main
struct PersonalFinanceAIApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @State private var env: AppEnvironment

    init() {
        let env = AppEnvironment()
        _env = State(initialValue: env)
        // Initialised lazily here so AppEnvironment isn't constructed in
        // the property wrapper. The adaptor sets up the delegate AFTER init,
        // so we wire pushController in onAppear.
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(env)
                .onAppear {
                    appDelegate.pushController = env.push
                }
        }
    }
}
