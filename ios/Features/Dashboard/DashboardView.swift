import SwiftUI

struct DashboardView: View {
    @Environment(AppEnvironment.self) private var env
    @State private var vm: DashboardViewModel
    @State private var selectedTab: Tab = .overview

    enum Tab: String, CaseIterable, Identifiable {
        case overview = "Overview"
        case expenses = "Expenses"
        case assets = "Assets"
        case forecast = "Forecast"

        var id: String { rawValue }
    }

    init(api: APIClient) {
        _vm = State(initialValue: DashboardViewModel(api: api))
    }

    var body: some View {
        NavigationStack {
            content
                .navigationTitle("Dashboard")
                .navigationBarTitleDisplayMode(.inline)
                .toolbarBackground(.visible, for: .navigationBar)
                .toolbarBackground(Color.appBackground, for: .navigationBar)
                .toolbar {
                    ToolbarItem(placement: .topBarLeading) { yearFilterMenu }
                    ToolbarItem(placement: .topBarTrailing) { SignOutMenuButton() }
                }
        }
        .task { await vm.bootstrap() }
    }

    private var yearFilterMenu: some View {
        Menu {
            ForEach(vm.filterOptions) { option in
                Button {
                    Task { await vm.select(option) }
                } label: {
                    if option == vm.selectedFilter {
                        Label(option.label, systemImage: "checkmark")
                    } else {
                        Text(option.label)
                    }
                }
            }
        } label: {
            HStack(spacing: 4) {
                Image(systemName: "calendar")
                    .font(.footnote)
                Text(vm.selectedFilter.label)
                    .font(.subheadline.weight(.medium))
                Image(systemName: "chevron.down")
                    .font(.caption2)
            }
            .foregroundStyle(Color.appAccent)
        }
    }

    @ViewBuilder
    private var content: some View {
        switch vm.state {
        case .idle, .loading:
            VStack(spacing: 12) {
                ProgressView()
                Text("Loading dashboard…")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        case .error(let message):
            VStack(spacing: 12) {
                Image(systemName: "exclamationmark.triangle")
                    .font(.largeTitle)
                    .foregroundStyle(.red)
                Text(message)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                Button("Try again") {
                    Task { await vm.refresh() }
                }
                .buttonStyle(.borderedProminent)
            }
            .padding()
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        case .loaded(let data):
            loaded(data)
        }
    }

    @ViewBuilder
    private func loaded(_ data: DashboardResponse) -> some View {
        ScrollView {
            VStack(spacing: 16) {
                Picker("Tab", selection: $selectedTab) {
                    ForEach(Tab.allCases) { tab in
                        Text(tab.rawValue).tag(tab)
                    }
                }
                .pickerStyle(.segmented)
                .padding(.horizontal, 4)

                HStack(spacing: 6) {
                    Text("Showing").eyebrow()
                    Text(vm.selectedFilter.label)
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(Color.appAccent)
                    Spacer()
                }

                Group {
                    switch selectedTab {
                    case .overview: OverviewTab(data: data, scopeLabel: vm.selectedFilter.label)
                    case .expenses: ExpenseInsightsTab(data: data)
                    case .assets: AssetInsightsTab(data: data)
                    case .forecast: ForecastTab(data: data)
                    }
                }
            }
            .padding(.horizontal)
            .padding(.bottom, 24)
        }
        .scrollIndicators(.hidden)
        .background(Color.appBackground)
        .refreshable {
            await vm.refresh()
        }
    }
}
