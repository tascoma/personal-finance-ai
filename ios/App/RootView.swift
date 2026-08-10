import SwiftUI

struct RootView: View {
    @Environment(AppEnvironment.self) private var env
    @Environment(\.scenePhase) private var scenePhase
    @State private var phase: Phase = .biometric

    enum Phase: Equatable {
        case biometric          // Showing BiometricGateView (only if biometric enabled)
        case bootstrapping      // Trying cookie refresh + /auth/me
        case ready              // MainTabView or LoginView, depending on auth
    }

    var body: some View {
        Group {
            switch phase {
            case .biometric:
                if env.biometric.isEnabled {
                    BiometricGateView {
                        Task { await beginBootstrap() }
                    }
                } else {
                    // Skip the gate entirely if biometric isn't opted in.
                    BootstrappingView()
                        .task { await beginBootstrap() }
                }
            case .bootstrapping:
                BootstrappingView()
            case .ready:
                if env.auth.isAuthenticated {
                    MainTabView()
                } else {
                    LoginView(api: env.api, auth: env.auth)
                }
            }
        }
        // Bootstrap is driven by the phase views: when biometric is disabled the
        // .biometric phase's .task fires it immediately, otherwise it waits for
        // unlock. Nothing to do on appear.
        .onChange(of: scenePhase) { _, newPhase in
            switch newPhase {
            case .background, .inactive:
                // Re-lock on backgrounding so warm foregrounding re-prompts.
                if env.biometric.isEnabled, env.auth.isAuthenticated {
                    env.biometric.lockIfEnabled()
                    phase = .biometric
                }
            case .active:
                break
            @unknown default:
                break
            }
        }
    }

    private func beginBootstrap() async {
        phase = .bootstrapping
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
                    .foregroundStyle(Color.appTextSecondary)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task {
            try? await Task.sleep(for: .seconds(3))
            showSlowHint = true
        }
    }
}
