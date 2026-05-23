import SwiftUI

struct ForecastTab: View {
    let data: DashboardResponse

    private var forecast: Forecast? {
        let currentYear = Calendar(identifier: .gregorian).component(.year, from: Date())
        return Forecast.from(
            netWorthSeries: data.netWorthSeries,
            periodBars: data.periodBars,
            targetYear: currentYear
        )
    }

    var body: some View {
        VStack(spacing: 16) {
            if let f = forecast {
                let gain = f.trailingEoy - f.currentNetWorth
                let gainPct = f.currentNetWorth != 0 ? gain / f.currentNetWorth * 100 : 0
                let gainColor: Color = gain >= 0 ? .green : .red
                let netColor: Color = f.avgMonthlyNet >= 0 ? .green : .red

                KPIGrid {
                    KPICard(label: "Current Net Worth",
                            value: Money.format(Decimal(f.currentNetWorth)),
                            valueColor: .accentColor,
                            sub: "latest closed period")
                    KPICard(label: "Projected EOY",
                            value: Money.format(Decimal(f.trailingEoy)),
                            valueColor: gainColor,
                            sub: "trailing-avg")
                    KPICard(label: "Projected Gain",
                            value: String(format: "%@%@", gain >= 0 ? "+" : "", Money.format(Decimal(gain))),
                            valueColor: gainColor,
                            sub: String(format: "%@%.1f%% over %d mo",
                                        gainPct >= 0 ? "+" : "", gainPct, f.monthsRemaining))
                    KPICard(label: "Avg Monthly Net",
                            value: String(format: "%@%@", f.avgMonthlyNet >= 0 ? "+" : "", Money.format(Decimal(f.avgMonthlyNet))),
                            valueColor: netColor,
                            sub: "trailing 12 periods")
                }

                DashboardCard("Net Worth Forecast", subtitle: "historical · projected through EOY") {
                    NetWorthForecastChart(forecast: f)
                }

                DashboardCard("Method", subtitle: "how these are computed") {
                    VStack(alignment: .leading, spacing: 10) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Trailing-avg projection")
                                .font(.subheadline.weight(.semibold))
                            Text("Average monthly net (income − expenses) over the last 12 closed periods, applied forward through EOY.")
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                        }
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Linear-regression projection")
                                .font(.subheadline.weight(.semibold))
                            Text("Least-squares line fit to the historical net-worth series. Sanity check vs. trailing-avg.")
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            } else {
                DashboardCard("Not enough data", subtitle: "close a period to project") {
                    Text("Need at least one closed period with net-worth history to forecast.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }
}
