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

                HeroCard(
                    style: .forecast,
                    eyebrow: "Projected Net Worth",
                    value: Money.format(Decimal(f.trailingEoy), fractionDigits: 0),
                    delta: HeroDelta(
                        text: "\(Money.delta(Decimal(gain))) (\(gainPct >= 0 ? "+" : "")\(String(format: "%.1f", gainPct))%) · EOY",
                        trend: gain >= 0 ? .up : .down
                    ),
                    stats: [
                        HeroStat(label: "Current NW", value: Money.format(Decimal(f.currentNetWorth), fractionDigits: 0)),
                        HeroStat(label: "Avg Monthly Net", value: Money.delta(Decimal(f.avgMonthlyNet))),
                        HeroStat(label: "Months Left", value: "\(f.monthsRemaining)"),
                    ],
                    sparkline: data.netWorthSeries.map { $0.netWorth.asDouble }
                )

                DashboardCard("Net Worth Forecast", subtitle: "historical + projected through EOY") {
                    NetWorthForecastChart(forecast: f)
                }
            } else {
                DashboardCard("Not enough data", subtitle: "close a period to project") {
                    Text("Need at least one closed period with net-worth history to forecast.")
                        .font(.footnote)
                        .foregroundStyle(Color.appTextTertiary)
                }
            }
        }
    }
}
