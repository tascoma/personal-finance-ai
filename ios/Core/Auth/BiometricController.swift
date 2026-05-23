import Foundation
import LocalAuthentication
import Observation

@MainActor
@Observable
final class BiometricController {
    enum BiometryType {
        case faceID, touchID, none

        var displayName: String {
            switch self {
            case .faceID: return "Face ID"
            case .touchID: return "Touch ID"
            case .none: return "Biometrics"
            }
        }

        var systemImage: String {
            switch self {
            case .faceID: return "faceid"
            case .touchID: return "touchid"
            case .none: return "lock.fill"
            }
        }
    }

    // UserDefaults rather than Keychain: this is a non-secret preference flag.
    // The Keychain is for secrets — and on the iOS Simulator the codesigning
    // identity shifts between `simctl install`s, which orphans Keychain entries
    // and breaks the dev loop. The actual biometric verification still goes
    // through LAContext; flipping this flag alone grants no access.
    private static let enabledKey = "biometric_enabled"

    /// True while the gate is in place and waiting for biometric success.
    var isLocked: Bool = false
    /// Consecutive failures since last success; 3 fails clears the flag.
    private(set) var failures: Int = 0
    /// Surfaced for messaging when the user explicitly toggles biometrics off
    /// or the gate gives up after repeated failures.
    var lastErrorMessage: String?

    /// Read on each access so a Settings toggle elsewhere is reflected immediately.
    var isEnabled: Bool { UserDefaults.standard.bool(forKey: Self.enabledKey) }

    /// What the device supports, regardless of whether the user opted in.
    var availableType: BiometryType {
        let context = LAContext()
        var error: NSError?
        guard context.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &error) else {
            return .none
        }
        switch context.biometryType {
        case .faceID: return .faceID
        case .touchID: return .touchID
        default: return .none
        }
    }

    func enable() {
        UserDefaults.standard.set(true, forKey: Self.enabledKey)
        failures = 0
        lastErrorMessage = nil
    }

    func disable(reason: String? = nil) {
        UserDefaults.standard.set(false, forKey: Self.enabledKey)
        isLocked = false
        failures = 0
        lastErrorMessage = reason
    }

    /// Called when the app enters the background, so the next foreground re-prompts.
    func lockIfEnabled() {
        if isEnabled { isLocked = true }
    }

    /// Triggers the system biometric prompt. Returns true on success.
    /// On 3 consecutive failures, clears the enabled flag and surfaces a message.
    @discardableResult
    func unlock() async -> Bool {
        guard isEnabled else {
            isLocked = false
            return true
        }
        let context = LAContext()
        context.localizedFallbackTitle = ""  // hide the system fallback button
        var error: NSError?
        guard context.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &error) else {
            // Device lost biometric capability (e.g. user removed Face ID). Disable.
            disable(reason: "Biometrics no longer available on this device.")
            return true
        }
        do {
            let ok = try await context.evaluatePolicy(
                .deviceOwnerAuthenticationWithBiometrics,
                localizedReason: "Unlock Personal Finance"
            )
            if ok {
                isLocked = false
                failures = 0
                lastErrorMessage = nil
                return true
            }
            return registerFailure()
        } catch let err as LAError where err.code == .userCancel || err.code == .systemCancel || err.code == .appCancel {
            // Cancellation isn't a "failure" for lockout purposes; keep locked.
            return false
        } catch {
            return registerFailure()
        }
    }

    private func registerFailure() -> Bool {
        failures += 1
        if failures >= 3 {
            disable(reason: "Too many failed attempts. Sign in again to re-enable.")
        }
        return false
    }
}
