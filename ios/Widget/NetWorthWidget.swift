import WidgetKit
import SwiftUI

struct NetWorthWidget: Widget {
    let kind: String = "NetWorthWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: SnapshotProvider()) { entry in
            NetWorthWidgetView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("Net Worth")
        .description("Your current net worth and this month's cash flow.")
        .supportedFamilies([.systemSmall, .systemMedium, .systemLarge])
    }
}

struct SnapshotEntry: TimelineEntry {
    let date: Date
    let snapshot: WidgetSnapshot?
}

struct SnapshotProvider: TimelineProvider {
    func placeholder(in context: Context) -> SnapshotEntry {
        SnapshotEntry(date: Date(), snapshot: .placeholder)
    }

    func getSnapshot(in context: Context, completion: @escaping (SnapshotEntry) -> Void) {
        let snap = context.isPreview ? .placeholder : SharedContainer.readSnapshot()
        completion(SnapshotEntry(date: Date(), snapshot: snap))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<SnapshotEntry>) -> Void) {
        let snap = SharedContainer.readSnapshot()
        let entry = SnapshotEntry(date: Date(), snapshot: snap)
        // WidgetKit allocates a reload budget; 30 minutes is a respectful cadence
        // for net-worth which moves slowly. The main app also calls
        // WidgetCenter.reloadAllTimelines() after every successful /dashboard fetch.
        let next = Date().addingTimeInterval(30 * 60)
        completion(Timeline(entries: [entry], policy: .after(next)))
    }
}

struct NetWorthWidgetView: View {
    @Environment(\.widgetFamily) private var family
    let entry: SnapshotEntry

    var body: some View {
        Group {
            if let snapshot = entry.snapshot {
                switch family {
                case .systemSmall:
                    SmallView(snapshot: snapshot)
                case .systemMedium:
                    MediumView(snapshot: snapshot)
                case .systemLarge:
                    LargeView(snapshot: snapshot)
                default:
                    SmallView(snapshot: snapshot)
                }
            } else {
                PlaceholderView()
            }
        }
    }
}

// MARK: - Size variants

private struct SmallView: View {
    let snapshot: WidgetSnapshot

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Net Worth")
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(Money.compact(snapshot.netWorth))
                .font(.title2.weight(.semibold))
                .foregroundStyle(.tint)
                .minimumScaleFactor(0.7)
            Spacer()
            HStack(spacing: 4) {
                Image(systemName: snapshot.monthlyNet >= 0 ? "arrow.up.right" : "arrow.down.right")
                    .font(.caption2)
                Text(Money.compact(snapshot.monthlyNet))
                    .font(.caption.weight(.medium))
            }
            .foregroundStyle(snapshot.monthlyNet >= 0 ? .green : .red)
            Text(snapshot.periodLabel)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }
}

private struct MediumView: View {
    let snapshot: WidgetSnapshot

    var body: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Net Worth")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Text(Money.compact(snapshot.netWorth))
                    .font(.title2.weight(.semibold))
                    .foregroundStyle(.tint)
                    .minimumScaleFactor(0.7)
                Spacer()
                Text(snapshot.periodLabel)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 6) {
                row(label: "Income", value: snapshot.monthlyIncome, color: .green)
                row(label: "Expenses", value: snapshot.monthlyExpenses, color: .red)
                Divider()
                row(label: "Net",
                    value: snapshot.monthlyNet,
                    color: snapshot.monthlyNet >= 0 ? .green : .red,
                    bold: true)
            }
        }
    }

    @ViewBuilder
    private func row(label: String, value: Decimal, color: Color, bold: Bool = false) -> some View {
        let valueFont: Font = bold ? .caption.weight(.semibold) : .caption
        HStack(spacing: 6) {
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(Money.compact(value))
                .font(valueFont.monospacedDigit())
                .foregroundStyle(color)
        }
    }
}

private struct LargeView: View {
    let snapshot: WidgetSnapshot

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Net Worth")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Text(Money.format(snapshot.netWorth))
                    .font(.title.weight(.semibold))
                    .foregroundStyle(.tint)
                    .minimumScaleFactor(0.7)
            }

            Divider()

            row("Total Assets", snapshot.totalAssets, color: .primary)
            row("Total Liabilities", snapshot.totalLiabilities, color: .red)

            Divider()

            Text("This month — \(snapshot.periodLabel)")
                .font(.caption2)
                .foregroundStyle(.secondary)
            row("Income", snapshot.monthlyIncome, color: .green)
            row("Expenses", snapshot.monthlyExpenses, color: .red)
            row("Net", snapshot.monthlyNet, color: snapshot.monthlyNet >= 0 ? .green : .red, bold: true)

            Spacer()

            Text("Updated \(snapshot.capturedAt.formatted(date: .abbreviated, time: .shortened))")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }

    @ViewBuilder
    private func row(_ label: String, _ value: Decimal, color: Color, bold: Bool = false) -> some View {
        let labelFont: Font = bold ? .footnote.weight(.semibold) : .footnote
        HStack {
            Text(label)
                .font(labelFont)
            Spacer()
            Text(Money.format(value))
                .font(labelFont.monospacedDigit())
                .foregroundStyle(color)
        }
    }
}

private struct PlaceholderView: View {
    @Environment(\.widgetFamily) private var family

    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: "chart.bar.fill")
                .font(.title2)
                .foregroundStyle(.tint)
            Text("Open Personal Finance")
                .font(family == .systemSmall ? .caption2 : .footnote)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Text("Sign in to populate this widget.")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding(.horizontal, 8)
    }
}

#Preview(as: .systemSmall) {
    NetWorthWidget()
} timeline: {
    SnapshotEntry(date: .now, snapshot: .placeholder)
}

#Preview(as: .systemMedium) {
    NetWorthWidget()
} timeline: {
    SnapshotEntry(date: .now, snapshot: .placeholder)
}

#Preview(as: .systemLarge) {
    NetWorthWidget()
} timeline: {
    SnapshotEntry(date: .now, snapshot: .placeholder)
}
