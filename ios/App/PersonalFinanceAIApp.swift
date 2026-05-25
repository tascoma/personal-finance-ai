import SwiftUI

@main
struct PersonalFinanceAIApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @State private var env: AppEnvironment
    @AppStorage("isDarkMode") private var isDarkMode: Bool = true

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
                .preferredColorScheme(isDarkMode ? .dark : .light)
                .tint(Color.appAccent)
                .onAppear {
                    appDelegate.pushController = env.push
                }
        }
    }
}
