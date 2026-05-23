import Foundation
import Observation
import UIKit
import UserNotifications

/// Owns the iOS-side push lifecycle: permission prompts, device-token capture
/// from APNs, registration with our backend, and deregistration on sign-out.
///
/// Wired up via AppDelegateAdaptor so we can intercept the
/// application:didRegisterForRemoteNotificationsWithDeviceToken callback —
/// SwiftUI's `.task`-style lifecycle doesn't expose APNs delegate methods.
@MainActor
@Observable
final class PushNotificationsController: NSObject, UNUserNotificationCenterDelegate {
    enum Status: Equatable {
        case unknown
        case denied
        case authorized
        case registering          // permission granted, awaiting APNs token
        case registered(token: String)
        case failed(String)
    }

    var status: Status = .unknown

    private var api: APIClient?
    private var bundleId: String { Bundle.main.bundleIdentifier ?? "com.tascoma.personalfinanceai" }

    func configure(api: APIClient) {
        self.api = api
        UNUserNotificationCenter.current().delegate = self
    }

    /// Inspect the current permission state without prompting. Call on app launch.
    func refreshStatus() async {
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        switch settings.authorizationStatus {
        case .authorized, .provisional, .ephemeral:
            status = .authorized
            // System remembers the token across launches; ask APNs to redeliver
            // the device-token callback so we can re-register.
            UIApplication.shared.registerForRemoteNotifications()
        case .denied:
            status = .denied
        case .notDetermined:
            status = .unknown
        @unknown default:
            status = .unknown
        }
    }

    /// Prompts for permission if not yet asked. Idempotent; returns the final state.
    @discardableResult
    func requestAuthorizationIfNeeded() async -> Status {
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        if settings.authorizationStatus != .notDetermined {
            await refreshStatus()
            return status
        }
        do {
            let granted = try await UNUserNotificationCenter.current()
                .requestAuthorization(options: [.alert, .badge, .sound])
            if granted {
                status = .registering
                UIApplication.shared.registerForRemoteNotifications()
            } else {
                status = .denied
            }
        } catch {
            status = .failed(error.localizedDescription)
        }
        return status
    }

    /// Called by AppDelegate when APNs hands us a token.
    func didReceive(deviceToken: Data) {
        let hex = deviceToken.map { String(format: "%02x", $0) }.joined()
        status = .registered(token: hex)
        Task { await registerWithBackend(token: hex) }
    }

    /// Called by AppDelegate when APNs registration fails.
    func didFailToRegister(error: Error) {
        status = .failed(error.localizedDescription)
    }

    /// Called from sign-out: best-effort drop the token from the backend so
    /// we stop pushing this device.
    func deregisterCurrentToken() async {
        guard case .registered(let token) = status, let api else { return }
        try? await api.perform(.deleteDeviceToken(apnsToken: token))
        status = .authorized  // permission still granted at the OS level
    }

    // MARK: - UNUserNotificationCenterDelegate

    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        // Show banner + sound even when the app is foregrounded.
        completionHandler([.banner, .sound, .list])
    }

    // MARK: - Backend registration

    private func registerWithBackend(token: String) async {
        guard let api else { return }
        do {
            try await api.perform(.registerDeviceToken(apnsToken: token, bundleId: bundleId))
        } catch {
            // Non-fatal — the device is still registered with APNs at the OS
            // level. Next launch's refreshStatus() will retry the backend
            // registration.
        }
    }
}
