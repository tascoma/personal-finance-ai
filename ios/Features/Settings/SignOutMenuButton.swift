import SwiftUI

struct SignOutMenuButton: View {
    @Environment(AppEnvironment.self) private var env
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

    private func signOut() async {
        isSigningOut = true
        defer { isSigningOut = false }
        try? await env.api.perform(.logout)
        // Disable biometric on sign-out so the next user must opt in explicitly.
        env.biometric.disable()
        env.auth.clear()
    }
}
