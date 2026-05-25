import SwiftUI

struct BalanceSheetView: View {
    let response: BalanceSheetPivotResponse
    let selectedPeriodId: UUID?

    private var columnIndex: Int {
        guard let id = selectedPeriodId,
              let idx = response.periods.firstIndex(where: { $0.periodId == id })
        else { return max(0, response.periods.count - 1) }
        return idx
    }

    private var totalAssets: Decimal { response.decimal(response.totalAssets, at: columnIndex) }
    private var totalLiabilities: Decimal { response.decimal(response.totalLiabilities, at: columnIndex) }
    private var totalEquity: Decimal { response.decimal(response.totalEquity, at: columnIndex) }
    private var totalLiabAndEquity: Decimal { totalLiabilities + totalEquity }
    private var totalOffBs: Decimal { response.decimal(response.totalOffBalanceSheet, at: columnIndex) }

    var body: some View {
        VStack(spacing: 16) {
            balanceCard

            sectionStack(title: "Assets", sections: response.assets, totalLabel: "Total assets", total: totalAssets, totalColor: .appAccent)
            sectionStack(title: "Liabilities", sections: response.liabilities, totalLabel: "Total liabilities", total: totalLiabilities, totalColor: .appRed)
            sectionStack(title: "Equity", sections: response.equity, totalLabel: "Total equity", total: totalEquity, totalColor: .appGreen)

            if !response.offBalanceSheet.isEmpty {
                sectionStack(title: "Off Balance Sheet", sections: response.offBalanceSheet, totalLabel: "Total off-balance-sheet", total: totalOffBs, totalColor: .secondary)
            }
        }
    }

    private var balanceCard: some View {
        VStack(spacing: 6) {
            balanceRow("Total Assets", totalAssets, color: .appAccent)
            balanceRow("Total Liabilities + Equity", totalLiabAndEquity, color: .primary)
            let diff = totalAssets - totalLiabAndEquity
            balanceRow("Imbalance", diff, color: diff == 0 ? .appGreen : .appRed)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.appCard, in: RoundedRectangle(cornerRadius: 10))
    }

    private func balanceRow(_ label: String, _ value: Decimal, color: Color) -> some View {
        HStack {
            Text(label)
                .font(.subheadline)
            Spacer()
            Text(Money.format(value))
                .font(.subheadline.weight(.semibold).monospacedDigit())
                .foregroundStyle(color)
        }
    }

    private func sectionStack(
        title: String,
        sections: [BalanceSheetPivotSection],
        totalLabel: String,
        total: Decimal,
        totalColor: Color
    ) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.headline)

            ForEach(sections) { section in
                VStack(alignment: .leading, spacing: 4) {
                    Text(section.label)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.secondary)
                    ForEach(section.rows) { row in
                        StatementLineRow(name: row.accountName, amount: row.amount(at: columnIndex))
                    }
                    let subtotal = section.subtotal(at: columnIndex)
                    if section.rows.count > 1 || subtotal != 0 {
                        Divider()
                        StatementSubtotalRow(
                            label: "Subtotal — \(section.label.lowercased())",
                            amount: subtotal
                        )
                    }
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.appCard, in: RoundedRectangle(cornerRadius: 10))
            }

            HStack {
                Text(totalLabel)
                    .font(.subheadline.weight(.semibold))
                Spacer()
                Text(Money.format(total))
                    .font(.subheadline.weight(.semibold).monospacedDigit())
                    .foregroundStyle(totalColor)
            }
            .padding(.horizontal, 4)
        }
    }
}
