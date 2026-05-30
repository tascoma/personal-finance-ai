import SwiftUI

/// One `account_name … amount` row, the shared building block for income / cashflow
/// section bodies. Caller controls whether `amount` is shown muted or coloured.
struct StatementLineRow: View {
    let name: String
    let amount: Decimal
    var amountColor: Color = .primary
    var indented: Bool = true

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(name)
                .font(.callout)
                .foregroundStyle(Color.appTextSecondary)
                .lineLimit(1)
                .padding(.leading, indented ? Space.md : 0)
            Spacer()
            Text(Money.format(amount))
                .font(.callout.monospacedDigit())
                .foregroundStyle(amountColor)
        }
    }
}

struct StatementSubtotalRow: View {
    let label: String
    let amount: Decimal
    var amountColor: Color = .primary

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label)
                .font(.callout.weight(.semibold))
            Spacer()
            Text(Money.format(amount))
                .font(.callout.weight(.semibold).monospacedDigit())
                .foregroundStyle(amountColor)
        }
        .padding(.vertical, 4)
    }
}

/// Renders one income/expenses/OCI/cashflow section: optional header, lines, subtotal.
struct StatementSectionView: View {
    let section: StatementSection
    var totalColor: Color = .primary

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(section.label)
                .eyebrow()
                .padding(.bottom, 2)

            ForEach(section.lines) { line in
                StatementLineRow(name: line.accountName, amount: line.amount)
            }

            Rectangle().fill(Color.appLine).frame(height: 1)
            StatementSubtotalRow(
                label: "Total \(section.label.lowercased())",
                amount: section.subtotal,
                amountColor: totalColor
            )
        }
        .padding(Space.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .appCardStyle()
    }
}

/// Renders an arbitrary list of lines under a header (cashflow's noncash /
/// working-capital / investing / financing) with a passed-in total label/amount.
struct StatementLinesBlock: View {
    let header: String
    let lines: [StatementLine]
    let totalLabel: String
    let total: Decimal
    var totalColor: Color = .primary

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(header)
                .eyebrow()
                .padding(.bottom, 2)

            if lines.isEmpty {
                Text("—")
                    .font(.footnote)
                    .foregroundStyle(Color.appTextTertiary)
                    .padding(.leading, Space.md)
            } else {
                ForEach(lines) { line in
                    StatementLineRow(name: line.accountName, amount: line.amount)
                }
            }

            Rectangle().fill(Color.appLine).frame(height: 1)
            StatementSubtotalRow(label: totalLabel, amount: total, amountColor: totalColor)
        }
        .padding(Space.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .appCardStyle()
    }
}
