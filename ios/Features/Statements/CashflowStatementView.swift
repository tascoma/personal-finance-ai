import SwiftUI

struct CashflowStatementView: View {
    let response: CashflowStatementResponse

    var body: some View {
        VStack(spacing: 16) {
            summaryCard

            // Operating section: net income + noncash adjustments + working-capital changes
            VStack(alignment: .leading, spacing: 10) {
                Text("Operating Activities")
                    .font(.headline)

                VStack(alignment: .leading, spacing: 6) {
                    Text("Starting point")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.secondary)
                    StatementLineRow(name: "Net income", amount: response.netIncome)
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 10))

                if !response.noncashAdjustments.isEmpty {
                    StatementLinesBlock(
                        header: "Non-cash adjustments",
                        lines: response.noncashAdjustments,
                        totalLabel: "Subtotal — non-cash",
                        total: response.noncashAdjustments.reduce(Decimal(0)) { $0 + $1.amount }
                    )
                }
                if !response.workingCapitalChanges.isEmpty {
                    StatementLinesBlock(
                        header: "Working capital changes",
                        lines: response.workingCapitalChanges,
                        totalLabel: "Subtotal — working capital",
                        total: response.workingCapitalChanges.reduce(Decimal(0)) { $0 + $1.amount }
                    )
                }

                HStack {
                    Text("Cash from operations")
                        .font(.subheadline.weight(.semibold))
                    Spacer()
                    Text(Money.format(response.operatingTotal))
                        .font(.subheadline.weight(.semibold).monospacedDigit())
                        .foregroundStyle(response.operatingTotal >= 0 ? .green : .red)
                }
                .padding(.horizontal, 4)
            }

            section("Investing Activities", lines: response.investing, total: response.investingTotal)
            section("Financing Activities", lines: response.financing, total: response.financingTotal)

            reconciliationCard
        }
    }

    private var summaryCard: some View {
        VStack(spacing: 6) {
            summaryRow("Beginning cash", response.beginningCash)
            summaryRow("Net change", response.netChangeInCash, color: response.netChangeInCash >= 0 ? .green : .red)
            Divider()
            summaryRow("Ending cash", response.endingCash, color: .accentColor, bold: true)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 10))
    }

    private func summaryRow(_ label: String, _ value: Decimal, color: Color = .primary, bold: Bool = false) -> some View {
        let labelFont: Font = bold ? .subheadline.weight(.semibold) : .subheadline
        return HStack {
            Text(label)
                .font(labelFont)
            Spacer()
            Text(Money.format(value))
                .font(labelFont.monospacedDigit())
                .foregroundStyle(color)
        }
    }

    private func section(_ title: String, lines: [StatementLine], total: Decimal) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title).font(.headline)
            StatementLinesBlock(
                header: title.replacingOccurrences(of: " Activities", with: " flows"),
                lines: lines,
                totalLabel: "Net \(title.lowercased().replacingOccurrences(of: " activities", with: ""))",
                total: total,
                totalColor: total >= 0 ? .green : .red
            )
        }
    }

    private var reconciliationCard: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Cash by Account")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.secondary)
                .padding(.bottom, 2)
            if response.cashByAccount.isEmpty {
                Text("—").foregroundStyle(.secondary).font(.footnote)
            } else {
                ForEach(response.cashByAccount) { line in
                    StatementLineRow(name: line.accountName, amount: line.amount)
                }
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 10))
    }
}
