import SwiftUI

struct KPICard: View {
    let label: String
    let value: String
    let valueColor: Color
    let sub: String?
    let subColor: Color?

    init(label: String, value: String, valueColor: Color = .primary, sub: String? = nil, subColor: Color? = nil) {
        self.label = label
        self.value = value
        self.valueColor = valueColor
        self.sub = sub
        self.subColor = subColor
    }

    var body: some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            Text(label)
                .eyebrow()
                .lineLimit(2)
            Text(value)
                .font(.title3.weight(.semibold).monospacedDigit())
                .foregroundStyle(valueColor)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
            if let sub = sub {
                Text(sub)
                    .font(.caption2)
                    .foregroundStyle(subColor ?? Color.appTextTertiary)
                    .lineLimit(1)
            }
        }
        .padding(Space.md)
        .frame(maxWidth: .infinity, minHeight: 80, alignment: .topLeading)
        .appCardStyle()
    }
}

struct KPIGrid<Content: View>: View {
    let content: () -> Content

    init(@ViewBuilder content: @escaping () -> Content) {
        self.content = content
    }

    var body: some View {
        LazyVGrid(
            columns: [GridItem(.flexible(), spacing: Space.md), GridItem(.flexible(), spacing: Space.md)],
            spacing: Space.md
        ) {
            content()
        }
    }
}

struct DashboardCard<Content: View>: View {
    let title: String
    let subtitle: String?
    let content: () -> Content

    init(_ title: String, subtitle: String? = nil, @ViewBuilder content: @escaping () -> Content) {
        self.title = title
        self.subtitle = subtitle
        self.content = content
    }

    var body: some View {
        VStack(alignment: .leading, spacing: Space.md) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.headline)
                    .foregroundStyle(Color.appTextPrimary)
                if let sub = subtitle {
                    Text(sub)
                        .font(.caption)
                        .foregroundStyle(Color.appTextTertiary)
                }
            }
            Rectangle()
                .fill(Color.appLine)
                .frame(height: 1)
            content()
        }
        .padding(Space.lg)
        .frame(maxWidth: .infinity, alignment: .leading)
        .appCardStyle(radius: Radius.lg)
    }
}
