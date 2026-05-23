import SwiftUI

struct RootView: View {
    @Environment(AppEnvironment.self) private var env
    @State private var phase: Phase = .bootstrapping

    enum Phase: Equatable {
        case bootstrapping
        case ready
    }

    var body: some View {
        Group {
            switch phase {
            case .bootstrapping:
                BootstrappingView()
                    .task { await bootstrap() }
            case .ready:
                if env.auth.isAuthenticated {
                    MainTabView()
                } else {
                    LoginView(api: env.api, auth: env.auth)
                }
            }
        }
    }

    private func bootstrap() async {
        do {
            let token = try await env.refresher.refresh(baseURL: env.baseURL, session: env.session)
            env.auth.accessToken = token
            let user = try await env.api.perform(.me, as: User.self)
            env.auth.currentUser = user
        } catch {
            env.auth.clear()
        }
        phase = .ready
    }
}

private struct BootstrappingView: View {
    @State private var showSlowHint = false

    var body: some View {
        VStack(spacing: 16) {
            ProgressView()
            if showSlowHint {
                Text("Waking server…")
                    .foregroundStyle(.secondary)
            }
        }
        .task {
            try? await Task.sleep(for: .seconds(3))
            showSlowHint = true
        }
    }
}
