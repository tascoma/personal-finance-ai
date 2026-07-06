import SwiftUI
import Charts

struct IncomeExpensesChart: View {
    let bars: [PeriodBarPoint]

    private enum Series: String, Plottable {
        case income = "Income"
        case expenses = "Expenses"
    }

    /// Categorical string axes aren't thinned by `.automatic(desiredCount:)`, so with
    /// 6+ periods every label renders and gets clipped. Pick a subset up front instead.
    private var xAxisLabelValues: [String] {
        let labels = bars.map(\.periodLabel)
        guard labels.count > 4 else { return labels }
        let step = Int(ceil(Double(labels.count) / 4.0))
        return stride(from: 0, to: labels.count, by: step).map { labels[$0] }
    }

    var body: some View {
        Chart {
            ForEach(bars) { bar in
                BarMark(
                    x: .value("Period", bar.periodLabel),
                    y: .value("Amount", bar.income.asDouble)
                )
                .foregroundStyle(by: .value("Series", Series.income))
                .position(by: .value("Series", Series.income))

                BarMark(
                    x: .value("Period", bar.periodLabel),
                    y: .value("Amount", bar.expenses.asDouble)
                )
                .foregroundStyle(by: .value("Series", Series.expenses))
                .position(by: .value("Series", Series.expenses))
            }
        }
        .chartForegroundStyleScale([
            Series.income: Color.appGreen,
            Series.expenses: Color.appRed,
        ])
        .chartXAxis {
            AxisMarks(values: xAxisLabelValues) { value in
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
        .chartLegend(position: .bottom, alignment: .center, spacing: 8)
        .frame(height: 200)
    }
}
