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
        .task {
            // Re-register the device with our backend if APNs already remembers
            // this device from a previous launch (system retains the token across
            // launches; our backend may have lost it during a redeploy).
            await env.push.refreshStatus()
        }
        .onAppear { evaluateOptIn() }
        .onChange(of: env.auth.pendingBiometricOptIn) { _, newValue in
            evaluateOptIn()
            if newValue {
                // Fresh login — ask for notification permission once, regardless
                // of whether the biometric alert fires (it might be skipped if
                // biometric isn't available or is already enabled).
                Task { await env.push.requestAuthorizationIfNeeded() }
            }
        }
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
