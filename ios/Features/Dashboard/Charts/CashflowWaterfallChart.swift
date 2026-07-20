import SwiftUI
import Charts

/// Cash movement as a waterfall: Beginning → Operating → Investing → Financing → Ending
/// (web assets "Statement of Cash Flows"). The two totals are absolute bars from zero;
/// the three middle steps are floating bars spanning their running balance.
struct CashflowWaterfallChart: View {
    let cashflow: CashflowStatementResponse

    private struct Step {
        let label: String
        let start: Double
        let end: Double
        let amount: Double
        let isTotal: Bool
    }

    private var steps: [Step] {
        let beginning = cashflow.beginningCash.asDouble
        let operating = cashflow.operatingTotal.asDouble
        let investing = cashflow.investingTotal.asDouble
        let financing = cashflow.financingTotal.asDouble
        let ending = cashflow.endingCash.asDouble

        let afterOperating = beginning + operating
        let afterInvesting = afterOperating + investing
        let afterFinancing = afterInvesting + financing

        return [
            Step(label: "Beginning", start: 0, end: beginning, amount: beginning, isTotal: true),
            Step(label: "+ Operating", start: beginning, end: afterOperating, amount: operating, isTotal: false),
            Step(label: "+ Investing", start: afterOperating, end: afterInvesting, amount: investing, isTotal: false),
            Step(label: "+ Financing", start: afterInvesting, end: afterFinancing, amount: financing, isTotal: false),
            Step(label: "Ending", start: 0, end: ending, amount: ending, isTotal: true),
        ]
    }

    private func color(for step: Step) -> Color {
        if step.isTotal { return .appAccent }
        return step.amount >= 0 ? .appGreen : .appRed
    }

    var body: some View {
        Chart {
            ForEach(Array(steps.enumerated()), id: \.offset) { _, step in
                BarMark(
                    x: .value("Step", step.label),
                    yStart: .value("From", Swift.min(step.start, step.end)),
                    yEnd: .value("To", Swift.max(step.start, step.end))
                )
                .foregroundStyle(color(for: step).opacity(0.6))
                .cornerRadius(4)
            }
        }
        .chartXAxis {
            AxisMarks { value in
                AxisGridLine()
                AxisValueLabel {
                    if let label = value.as(String.self) {
                        Text(label).font(.caption2)
                    }
                }
            }
        }
        .chartYAxis {
            AxisMarks(position: .leading) { value in
                AxisGridLine()
                AxisValueLabel {
                    if let n = value.as(Double.self) {
                        Text(Money.compact(Decimal(n))).font(.caption2)
                    }
                }
            }
        }
        .frame(height: 220)
    }
}
