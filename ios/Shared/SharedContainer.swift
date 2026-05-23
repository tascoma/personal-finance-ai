import Foundation
import WidgetKit

/// Reads and writes the WidgetSnapshot from the App Group container shared
/// between the main app and the widget extension.
enum SharedContainer {
    static let appGroupID = "group.com.tascoma.personalfinanceai"
    private static let snapshotFileName = "dashboard-snapshot.json"

    private static var containerURL: URL? {
        FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: appGroupID)
    }

    private static var snapshotURL: URL? {
        containerURL?.appendingPathComponent(snapshotFileName)
    }

    /// Writes the snapshot to disk and asks WidgetKit to reload all timelines.
    /// Safe to call from any actor (file IO is synchronous and quick for a
    /// few-hundred-byte JSON blob).
    static func writeSnapshot(_ snapshot: WidgetSnapshot) {
        guard let url = snapshotURL else { return }
        do {
            let encoder = JSONEncoder()
            encoder.dateEncodingStrategy = .iso8601
            let data = try encoder.encode(snapshot)
            try data.write(to: url, options: .atomic)
            WidgetCenter.shared.reloadAllTimelines()
        } catch {
            // Non-fatal — widget will just keep the previous snapshot.
        }
    }

    static func readSnapshot() -> WidgetSnapshot? {
        guard let url = snapshotURL,
              FileManager.default.fileExists(atPath: url.path)
        else { return nil }
        do {
            let data = try Data(contentsOf: url)
            let decoder = JSONDecoder()
            decoder.dateDecodingStrategy = .iso8601
            return try decoder.decode(WidgetSnapshot.self, from: data)
        } catch {
            return nil
        }
    }
}
