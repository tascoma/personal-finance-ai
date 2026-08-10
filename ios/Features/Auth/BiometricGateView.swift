import SwiftUI

struct BiometricGateView: View {
    @Environment(AppEnvironment.self) private var env
    let onUnlocked: () -> Void

    private var biometric: BiometricController { env.biometric }

    var body: some View {
        VStack(spacing: 24) {
            Spacer()
            Image(systemName: biometric.availableType.systemImage)
                .font(.system(size: 72))
                .foregroundStyle(.tint)

            VStack(spacing: 6) {
                Text("Locked")
                    .font(.title2.weight(.semibold))
                Text("Unlock with \(biometric.availableType.displayName) to continue.")
                    .font(.callout)
                    .foregroundStyle(Color.appTextSecondary)
                    .multilineTextAlignment(.center)
            }

            if let message = biometric.lastErrorMessage {
                Text(message)
                    .font(.footnote)
                    .foregroundStyle(Color.appRed)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
            }

            Spacer()

            Button {
                Task {
                    let ok = await biometric.unlock()
                    if ok { onUnlocked() }
                }
            } label: {
                Label("Unlock", systemImage: biometric.availableType.systemImage)
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 6)
            }
            .buttonStyle(.borderedProminent)
            .padding(.horizontal, 32)
            .padding(.bottom, 24)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.appBackground)
        .task {
            // Auto-prompt on appear; user can re-trigger with the button if they cancel.
            let ok = await biometric.unlock()
            if ok { onUnlocked() }
        }
    }
}
