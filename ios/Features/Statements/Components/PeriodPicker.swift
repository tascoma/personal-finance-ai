import SwiftUI

struct PeriodPicker: View {
    let periods: [Period]
    @Binding var selection: UUID?

    var body: some View {
        Menu {
            ForEach(periods) { period in
                Button {
                    selection = period.periodId
                } label: {
                    if period.periodId == selection {
                        Label(period.label, systemImage: "checkmark")
                    } else {
                        Text(period.label)
                    }
                }
            }
        } label: {
            HStack(spacing: 6) {
                Image(systemName: "calendar")
                    .font(.footnote)
                    .foregroundStyle(Color.appAccent)
                Text(currentLabel)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(Color.appTextPrimary)
                Image(systemName: "chevron.down")
                    .font(.caption2)
                    .foregroundStyle(Color.appTextTertiary)
            }
            .padding(.horizontal, Space.md)
            .padding(.vertical, Space.sm)
            .background(Color.appSurface, in: Capsule())
            .overlay(Capsule().strokeBorder(Color.appLine, lineWidth: 1))
        }
        .disabled(periods.isEmpty)
    }

    private var currentLabel: String {
        if let id = selection, let p = periods.first(where: { $0.periodId == id }) {
            return p.label
        }
        return "No period"
    }
}
