import SwiftUI

struct SignOutMenuButton: View {
    @Environment(AppEnvironment.self) private var env
    @State private var isSigningOut = false

    var body: some View {
        Menu {
            if let email = env.auth.currentUser?.email {
                Text(email)
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
        env.auth.clear()
    }
}
