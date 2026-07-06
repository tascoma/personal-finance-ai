import Foundation

struct PeriodBarPoint: Decodable, Identifiable, Equatable {
    let periodLabel: String
    @DecimalString var income: Decimal
    @DecimalString var expenses: Decimal
    @DecimalString var net: Decimal

    var id: String { periodLabel }

    enum CodingKeys: String, CodingKey {
        case periodLabel = "period_label"
        case income, expenses, net
    }
}

struct NetWorthPoint: Decodable, Identifiable, Equatable {
    let periodLabel: String
    @DecimalString var netWorth: Decimal

    var id: String { periodLabel }

    enum CodingKeys: String, CodingKey {
        case periodLabel = "period_label"
        case netWorth = "net_worth"
    }
}

struct ExpenseCategoryPoint: Decodable, Identifiable, Equatable {
    let category: String
    @DecimalString var amount: Decimal

    var id: String { category }
}

struct ExpenseCategorySeriesPoint: Decodable, Equatable {
    let periodLabel: String
    let category: String
    @DecimalString var amount: Decimal

    enum CodingKeys: String, CodingKey {
        case periodLabel = "period_label"
        case category, amount
    }
}

struct AssetCompositionPoint: Decodable, Identifiable, Equatable {
    let subCategory: String
    @DecimalString var amount: Decimal

    var id: String { subCategory }

    enum CodingKeys: String, CodingKey {
        case subCategory = "sub_category"
        case amount
    }
}

struct AssetSeriesPoint: Decodable, Equatable {
    let periodLabel: String
    let subCategory: String
    @DecimalString var amount: Decimal

    enum CodingKeys: String, CodingKey {
        case periodLabel = "period_label"
        case subCategory = "sub_category"
        case amount
    }
}

struct RetirementContributionPoint: Decodable, Identifiable, Equatable {
    let accountCode: Int
    let accountName: String
    @DecimalString var amount: Decimal

    var id: Int { accountCode }

    enum CodingKeys: String, CodingKey {
        case accountCode = "account_code"
        case accountName = "account_name"
        case amount
    }
}

struct RecentEntryPoint: Decodable, Identifiable, Equatable {
    let description: String
    let entryDate: String
    let sourceType: String
    let periodLabel: String
    @DecimalString var totalDebit: Decimal

    var id: String { "\(periodLabel)|\(entryDate)|\(description)" }

    enum CodingKeys: String, CodingKey {
        case description
        case entryDate = "entry_date"
        case sourceType = "source_type"
        case periodLabel = "period_label"
        case totalDebit = "total_debit"
    }
}

struct DashboardResponse: Decodable {
    @DecimalString var totalIncome: Decimal
    @DecimalString var totalExpenses: Decimal
    @DecimalString var netIncome: Decimal
    @DecimalString var totalAssets: Decimal
    @DecimalString var totalAssetsPrev: Decimal
    @DecimalString var totalLiabilities: Decimal
    @DecimalString var netWorth: Decimal
    @DecimalString var investingCashflow: Decimal
    @DecimalString var salaryIncome: Decimal
    @DecimalString var retirementContributions: Decimal
    @DecimalString var compensationIncome: Decimal
    @DecimalString var lifestyleExpenses: Decimal
    @DecimalString var oci: Decimal
    @DecimalString var liquidAssets: Decimal
    @DecimalString var liquidAssetsPrev: Decimal
    @DecimalString var taxAdvantaged: Decimal
    @DecimalString var taxAdvantagedPrev: Decimal
    let periodCount: Int
    let hasData: Bool
    let periodBars: [PeriodBarPoint]
    let netWorthSeries: [NetWorthPoint]
    let topExpenseCategories: [ExpenseCategoryPoint]
    let expenseCategorySeries: [ExpenseCategorySeriesPoint]
    let assetComposition: [AssetCompositionPoint]
    let assetSeries: [AssetSeriesPoint]
    let ytdYear: Int?
    let ytdRetirementContributions: [RetirementContributionPoint]
    let recentEntries: [RecentEntryPoint]
    let activePeriod: Period?

    enum CodingKeys: String, CodingKey {
        case totalIncome = "total_income"
        case totalExpenses = "total_expenses"
        case netIncome = "net_income"
        case totalAssets = "total_assets"
        case totalAssetsPrev = "total_assets_prev"
        case totalLiabilities = "total_liabilities"
        case netWorth = "net_worth"
        case investingCashflow = "investing_cashflow"
        case salaryIncome = "salary_income"
        case retirementContributions = "retirement_contributions"
        case compensationIncome = "compensation_income"
        case lifestyleExpenses = "lifestyle_expenses"
        case oci
        case liquidAssets = "liquid_assets"
        case liquidAssetsPrev = "liquid_assets_prev"
        case taxAdvantaged = "tax_advantaged"
        case taxAdvantagedPrev = "tax_advantaged_prev"
        case periodCount = "period_count"
        case hasData = "has_data"
        case periodBars = "period_bars"
        case netWorthSeries = "net_worth_series"
        case topExpenseCategories = "top_expense_categories"
        case expenseCategorySeries = "expense_category_series"
        case assetComposition = "asset_composition"
        case assetSeries = "asset_series"
        case ytdYear = "ytd_year"
        case ytdRetirementContributions = "ytd_retirement_contributions"
        case recentEntries = "recent_entries"
        case activePeriod = "active_period"
    }
}
