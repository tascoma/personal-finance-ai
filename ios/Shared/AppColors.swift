import SwiftUI
import UIKit

extension Color {
    // Backgrounds — mirrors React CSS vars (dark / light)
    static let appBackground = Color(UIColor { t in
        t.userInterfaceStyle == .dark ? UIColor(hex: "05080f") : UIColor(hex: "eef5ff")
    })
    static let appCard = Color(UIColor { t in
        t.userInterfaceStyle == .dark ? UIColor(hex: "090e1f") : UIColor(hex: "ffffff")
    })
    static let appSurface = Color(UIColor { t in
        t.userInterfaceStyle == .dark ? UIColor(hex: "0e1530") : UIColor(hex: "ddeeff")
    })

    // Accent
    static let appAccent = Color(UIColor { t in
        t.userInterfaceStyle == .dark ? UIColor(hex: "56c8f0") : UIColor(hex: "0284c7")
    })
    static let appAccent2 = Color(UIColor { t in
        t.userInterfaceStyle == .dark ? UIColor(hex: "88dbf8") : UIColor(hex: "0369a1")
    })

    // Text
    static let appTextPrimary = Color(UIColor { t in
        t.userInterfaceStyle == .dark ? UIColor(hex: "ddeeff") : UIColor(hex: "0a1628")
    })
    static let appTextSecondary = Color(UIColor { t in
        t.userInterfaceStyle == .dark ? UIColor(hex: "6a9bb8") : UIColor(hex: "2d5a7a")
    })
    static let appTextTertiary = Color(UIColor { t in
        t.userInterfaceStyle == .dark ? UIColor(hex: "2f5470") : UIColor(hex: "6b9ab8")
    })

    // Semantic
    static let appGreen = Color(UIColor { t in
        t.userInterfaceStyle == .dark ? UIColor(hex: "4ade80") : UIColor(hex: "16a34a")
    })
    static let appRed = Color(UIColor { t in
        t.userInterfaceStyle == .dark ? UIColor(hex: "f87171") : UIColor(hex: "dc2626")
    })
    static let appAmber = Color(UIColor { t in
        t.userInterfaceStyle == .dark ? UIColor(hex: "fbbf24") : UIColor(hex: "b45309")
    })

    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let r = Double((int >> 16) & 0xff) / 255
        let g = Double((int >>  8) & 0xff) / 255
        let b = Double( int        & 0xff) / 255
        self.init(red: r, green: g, blue: b)
    }
}

extension UIColor {
    convenience init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let r = CGFloat((int >> 16) & 0xff) / 255
        let g = CGFloat((int >>  8) & 0xff) / 255
        let b = CGFloat( int        & 0xff) / 255
        self.init(red: r, green: g, blue: b, alpha: 1)
    }
}
