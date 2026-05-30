import SwiftUI

struct IncomeStatementView: View {
    let response: IncomeStatementResponse

    var body: some View {
        VStack(spacing: 16) {
            summaryCard

            if !response.income.isEmpty {
                grouping(title: "Income", sections: response.income, total: response.totalIncome, totalColor: .appGreen)
            }

            if !response.expenses.isEmpty {
                grouping(title: "Expenses", sections: response.expenses, total: response.totalExpenses, totalColor: .appRed)
            }

            if !response.otherComprehensiveIncome.isEmpty {
                grouping(title: "Other Comprehensive Income", sections: response.otherComprehensiveIncome, total: response.totalOci, totalColor: .secondary)
            }
        }
    }

    private var summaryCard: some View {
        VStack(spacing: 6) {
            summaryRow("Total Income", response.totalIncome, color: .appGreen)
            summaryRow("Total Expenses", response.totalExpenses, color: .appRed)
            Rectangle().fill(Color.appLine).frame(height: 1)
            summaryRow("Net Income", response.netIncome, color: response.netIncome >= 0 ? .appGreen : .appRed, bold: true)
            if response.totalOci != 0 || response.comprehensiveIncome != response.netIncome {
                summaryRow("Other Comprehensive Inc.", response.totalOci, color: .secondary)
                summaryRow("Comprehensive Income", response.comprehensiveIncome, color: response.comprehensiveIncome >= 0 ? .appGreen : .appRed, bold: true)
            }
        }
        .padding(Space.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .appCardStyle()
    }

    private func summaryRow(_ label: String, _ value: Decimal, color: Color, bold: Bool = false) -> some View {
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

    private func grouping(title: String, sections: [StatementSection], total: Decimal, totalColor: Color) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.headline)
                .foregroundStyle(Color.appTextPrimary)
            ForEach(sections) { section in
                StatementSectionView(section: section, totalColor: totalColor)
            }
            HStack {
                Text("Total \(title.lowercased())")
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
