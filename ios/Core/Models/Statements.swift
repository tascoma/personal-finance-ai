import Foundation

// MARK: - Shared statement rows (income, cashflow)

struct StatementLine: Decodable, Identifiable, Equatable {
    let accountCode: Int
    let accountName: String
    let subCategory: String
    @DecimalString var amount: Decimal

    var id: Int { accountCode }

    enum CodingKeys: String, CodingKey {
        case accountCode = "account_code"
        case accountName = "account_name"
        case subCategory = "sub_category"
        case amount
    }
}

struct StatementSection: Decodable, Identifiable, Equatable {
    let label: String
    let lines: [StatementLine]
    @DecimalString var subtotal: Decimal

    var id: String { label }
}

// MARK: - Balance sheet pivot

struct BalanceSheetPivotRow: Decodable, Identifiable, Equatable {
    let accountCode: Int
    let accountName: String
    let subCategory: String
    let balances: [String]  // parallel to BalanceSheetPivotResponse.periods

    var id: Int { accountCode }

    enum CodingKeys: String, CodingKey {
        case accountCode = "account_code"
        case accountName = "account_name"
        case subCategory = "sub_category"
        case balances
    }

    func amount(at index: Int) -> Decimal {
        guard index >= 0, index < balances.count else { return 0 }
        return Decimal(string: balances[index], locale: Locale(identifier: "en_US_POSIX")) ?? 0
    }
}

struct BalanceSheetPivotSection: Decodable, Identifiable, Equatable {
    let label: String
    let rows: [BalanceSheetPivotRow]
    let subtotals: [String]  // parallel to BalanceSheetPivotResponse.periods

    var id: String { label }

    func subtotal(at index: Int) -> Decimal {
        guard index >= 0, index < subtotals.count else { return 0 }
        return Decimal(string: subtotals[index], locale: Locale(identifier: "en_US_POSIX")) ?? 0
    }
}

struct BalanceSheetPivotResponse: Decodable, Equatable {
    let periods: [Period]
    let assets: [BalanceSheetPivotSection]
    let liabilities: [BalanceSheetPivotSection]
    let equity: [BalanceSheetPivotSection]
    let offBalanceSheet: [BalanceSheetPivotSection]
    let totalAssets: [String]
    let totalLiabilities: [String]
    let totalEquity: [String]
    let totalOffBalanceSheet: [String]

    enum CodingKeys: String, CodingKey {
        case periods, assets, liabilities, equity
        case offBalanceSheet = "off_balance_sheet"
        case totalAssets = "total_assets"
        case totalLiabilities = "total_liabilities"
        case totalEquity = "total_equity"
        case totalOffBalanceSheet = "total_off_balance_sheet"
    }

    func decimal(_ raw: [String], at index: Int) -> Decimal {
        guard index >= 0, index < raw.count else { return 0 }
        return Decimal(string: raw[index], locale: Locale(identifier: "en_US_POSIX")) ?? 0
    }
}

// MARK: - Income statement

struct IncomeStatementResponse: Decodable, Equatable {
    let rangeLabel: String
    let income: [StatementSection]
    let expenses: [StatementSection]
    let otherComprehensiveIncome: [StatementSection]
    @DecimalString var totalIncome: Decimal
    @DecimalString var totalExpenses: Decimal
    @DecimalString var totalOci: Decimal
    @DecimalString var netIncome: Decimal
    @DecimalString var comprehensiveIncome: Decimal

    enum CodingKeys: String, CodingKey {
        case rangeLabel = "range_label"
        case income, expenses
        case otherComprehensiveIncome = "other_comprehensive_income"
        case totalIncome = "total_income"
        case totalExpenses = "total_expenses"
        case totalOci = "total_oci"
        case netIncome = "net_income"
        case comprehensiveIncome = "comprehensive_income"
    }
}

// MARK: - Cash flow statement

struct CashflowStatementResponse: Decodable, Equatable {
    let rangeLabel: String
    @DecimalString var netIncome: Decimal
    let noncashAdjustments: [StatementLine]
    let workingCapitalChanges: [StatementLine]
    @DecimalString var operatingTotal: Decimal
    let investing: [StatementLine]
    @DecimalString var investingTotal: Decimal
    let financing: [StatementLine]
    @DecimalString var financingTotal: Decimal
    @DecimalString var netChangeInCash: Decimal
    let cashByAccount: [StatementLine]
    @DecimalString var beginningCash: Decimal
    @DecimalString var endingCash: Decimal

    enum CodingKeys: String, CodingKey {
        case rangeLabel = "range_label"
        case netIncome = "net_income"
        case noncashAdjustments = "noncash_adjustments"
        case workingCapitalChanges = "working_capital_changes"
        case operatingTotal = "operating_total"
        case investing
        case investingTotal = "investing_total"
        case financing
        case financingTotal = "financing_total"
        case netChangeInCash = "net_change_in_cash"
        case cashByAccount = "cash_by_account"
        case beginningCash = "beginning_cash"
        case endingCash = "ending_cash"
    }
}
