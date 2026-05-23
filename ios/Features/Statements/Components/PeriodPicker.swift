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
                Text(currentLabel)
                    .font(.subheadline.weight(.medium))
                Image(systemName: "chevron.down")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(Color(.secondarySystemGroupedBackground), in: Capsule())
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
