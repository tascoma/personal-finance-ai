import SwiftUI

struct MainTabView: View {
    @Environment(AppEnvironment.self) private var env
    @State private var showBiometricOptIn = false

    private var biometricType: BiometricController.BiometryType { env.biometric.availableType }

    var body: some View {
        TabView {
            DashboardView(api: env.api)
                .tabItem { Label("Dashboard", systemImage: "chart.bar.fill") }

            StatementsView(api: env.api)
                .tabItem { Label("Statements", systemImage: "doc.text.fill") }
        }
        .onAppear { evaluateOptIn() }
        .onChange(of: env.auth.pendingBiometricOptIn) { _, _ in evaluateOptIn() }
        .alert("Enable \(biometricType.displayName)?",
               isPresented: $showBiometricOptIn) {
            Button("Enable") {
                env.biometric.enable()
                env.auth.pendingBiometricOptIn = false
            }
            Button("Not now", role: .cancel) {
                env.auth.pendingBiometricOptIn = false
            }
        } message: {
            Text("Use \(biometricType.displayName) to unlock the app next time without typing your password.")
        }
    }

    private func evaluateOptIn() {
        guard env.auth.pendingBiometricOptIn,
              biometricType != .none,
              !env.biometric.isEnabled else { return }
        showBiometricOptIn = true
    }
}
