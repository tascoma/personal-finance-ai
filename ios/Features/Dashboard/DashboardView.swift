import SwiftUI

struct DashboardView: View {
    @Environment(AppEnvironment.self) private var env
    @State private var vm: DashboardViewModel
    @State private var selectedTab: Tab = .overview
    @State private var isSigningOut = false

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
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        Menu {
                            Button(role: .destructive) {
                                Task { await signOut() }
                            } label: {
                                Label("Sign out", systemImage: "rectangle.portrait.and.arrow.right")
                            }
                        } label: {
                            Image(systemName: "person.crop.circle")
                        }
                        .disabled(isSigningOut)
                    }
                }
        }
        .task { await vm.load() }
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
                    Task { await vm.load() }
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

                Group {
                    switch selectedTab {
                    case .overview: OverviewTab(data: data)
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
        .background(Color(.systemGroupedBackground))
        .refreshable {
            await vm.refresh()
        }
    }

    private func signOut() async {
        isSigningOut = true
        defer { isSigningOut = false }
        try? await env.api.perform(.logout)
        env.auth.clear()
    }
}
