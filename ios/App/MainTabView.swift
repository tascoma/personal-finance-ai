import SwiftUI

struct MainTabView: View {
    @Environment(AppEnvironment.self) private var env

    var body: some View {
        TabView {
            DashboardView(api: env.api)
                .tabItem { Label("Dashboard", systemImage: "chart.bar.fill") }

            StatementsView(api: env.api)
                .tabItem { Label("Statements", systemImage: "doc.text.fill") }
        }
    }
}
