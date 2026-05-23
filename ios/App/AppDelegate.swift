import UIKit
import SwiftUI

/// Bridges UIKit's APNs device-token callbacks into the SwiftUI app. SwiftUI
/// alone has no place to hook didRegisterForRemoteNotificationsWithDeviceToken,
/// so we adopt UIApplicationDelegate and forward the events to
/// PushNotificationsController via a shared reference held by AppEnvironment.
final class AppDelegate: NSObject, UIApplicationDelegate {
    /// Set by PersonalFinanceAIApp on init so the delegate can route APNs
    /// callbacks into the same controller instance the app uses elsewhere.
    weak var pushController: PushNotificationsController?

    func application(
        _ application: UIApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        Task { @MainActor in
            pushController?.didReceive(deviceToken: deviceToken)
        }
    }

    func application(
        _ application: UIApplication,
        didFailToRegisterForRemoteNotificationsWithError error: Error
    ) {
        Task { @MainActor in
            pushController?.didFailToRegister(error: error)
        }
    }
}
