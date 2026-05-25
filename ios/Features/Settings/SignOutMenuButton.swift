import SwiftUI

struct SignOutMenuButton: View {
    @Environment(AppEnvironment.self) private var env
    @AppStorage("isDarkMode") private var isDarkMode: Bool = true
    @State private var isSigningOut = false

    private var biometricType: BiometricController.BiometryType { env.biometric.availableType }
    private var biometricEnabled: Bool { env.biometric.isEnabled }

    var body: some View {
        Menu {
            if let email = env.auth.currentUser?.email {
                Text(email)
            }

            if biometricType != .none {
                Button {
                    if biometricEnabled {
                        env.biometric.disable()
                    } else {
                        env.biometric.enable()
                    }
                } label: {
                    Label(
                        biometricEnabled
                            ? "Disable \(biometricType.displayName)"
                            : "Enable \(biometricType.displayName)",
                        systemImage: biometricType.systemImage
                    )
                }
            }

            Button {
                isDarkMode.toggle()
            } label: {
                Label(
                    isDarkMode ? "Switch to Light Mode" : "Switch to Dark Mode",
                    systemImage: isDarkMode ? "sun.max" : "moon"
                )
            }

            if !pushIsRegistered {
                Button {
                    Task { await env.push.requestAuthorizationIfNeeded() }
                } label: {
                    Label("Enable notifications", systemImage: "bell.badge")
                }
            }

            Button(role: .destructive) {
                Task { await signOut() }
            } label: {
                Label("Sign out", systemImage: "rectangle.portrait.and.arrow.right")
            }
        } label: {
            Image(systemName: "person.crop.circle")
        }
        .disabled(isSigningOut)
    }

    private var pushIsRegistered: Bool {
        if case .registered = env.push.status { return true }
        return false
    }

    private func signOut() async {
        isSigningOut = true
        defer { isSigningOut = false }
        // Drop the APNs token from our backend first so we stop pushing this
        // device. Best-effort — backend will also delete dead tokens on
        // APNs 410 responses.
        await env.push.deregisterCurrentToken()
        try? await env.api.perform(.logout)
        LoginViewModel.clearSavedCredentials()
        // Disable biometric on sign-out so the next user must opt in explicitly.
        env.biometric.disable()
        env.auth.clear()
    }
}
