import SwiftUI
import UIKit

extension Color {
    // Backgrounds — mirrors React CSS vars (dark / light). See frontend/src/styles/style.css.
    static let appBackground = Color(UIColor { t in            // --bg
        t.userInterfaceStyle == .dark ? UIColor(hex: "07090f") : UIColor(hex: "f5f6f8")
    })
    static let appCard = Color(UIColor { t in                  // --bg-1
        t.userInterfaceStyle == .dark ? UIColor(hex: "0c1019") : UIColor(hex: "ffffff")
    })
    static let appSurface = Color(UIColor { t in               // --bg-3
        t.userInterfaceStyle == .dark ? UIColor(hex: "161c29") : UIColor(hex: "f3f5f9")
    })
    static let appBgHover = Color(UIColor { t in               // --bg-hover
        t.userInterfaceStyle == .dark ? UIColor(hex: "1a2233") : UIColor(hex: "eef1f6")
    })

    // Accent
    static let appAccent = Color(UIColor { t in                // --accent
        t.userInterfaceStyle == .dark ? UIColor(hex: "56c8f0") : UIColor(hex: "0284c7")
    })
    static let appAccent2 = Color(UIColor { t in               // --accent-2
        t.userInterfaceStyle == .dark ? UIColor(hex: "92e2ff") : UIColor(hex: "0369a1")
    })
    /// Text/icon colour that sits on top of a solid accent fill (--on-accent).
    static let appOnAccent = Color(UIColor { t in
        t.userInterfaceStyle == .dark ? UIColor(hex: "04101a") : UIColor(hex: "ffffff")
    })

    // Text
    static let appTextPrimary = Color(UIColor { t in           // --text
        t.userInterfaceStyle == .dark ? UIColor(hex: "e9eef7") : UIColor(hex: "0c111c")
    })
    static let appTextSecondary = Color(UIColor { t in         // --text-2
        t.userInterfaceStyle == .dark ? UIColor(hex: "9aa6bd") : UIColor(hex: "4b5670")
    })
    static let appTextTertiary = Color(UIColor { t in          // --text-3
        t.userInterfaceStyle == .dark ? UIColor(hex: "5e6a82") : UIColor(hex: "7a8499")
    })

    // Semantic
    static let appGreen = Color(UIColor { t in                 // --green
        t.userInterfaceStyle == .dark ? UIColor(hex: "4ade80") : UIColor(hex: "16a34a")
    })
    static let appRed = Color(UIColor { t in                   // --red
        t.userInterfaceStyle == .dark ? UIColor(hex: "fb7185") : UIColor(hex: "dc2626")
    })
    static let appAmber = Color(UIColor { t in                 // --amber
        t.userInterfaceStyle == .dark ? UIColor(hex: "fbbf24") : UIColor(hex: "b45309")
    })
    static let appPurple = Color(UIColor { t in                // --purple
        t.userInterfaceStyle == .dark ? UIColor(hex: "a78bfa") : UIColor(hex: "7c3aed")
    })

    // Hairline borders — translucent, like the web's --line / --line-2.
    static let appLine = Color(UIColor { t in
        t.userInterfaceStyle == .dark
            ? UIColor(white: 1, alpha: 0.06) : UIColor(red: 8/255, green: 15/255, blue: 30/255, alpha: 0.07)
    })
    static let appLineStrong = Color(UIColor { t in
        t.userInterfaceStyle == .dark
            ? UIColor(white: 1, alpha: 0.10) : UIColor(red: 8/255, green: 15/255, blue: 30/255, alpha: 0.10)
    })

    // Semantic tints — back pill badges / banners (--*-bg, --accent-tint).
    static let appAccentTint = Color(UIColor { t in
        UIColor(hex: t.userInterfaceStyle == .dark ? "56c8f0" : "0284c7")
            .withAlphaComponent(t.userInterfaceStyle == .dark ? 0.10 : 0.06)
    })
    static let appGreenBg = Color(UIColor { t in
        UIColor(hex: t.userInterfaceStyle == .dark ? "4ade80" : "16a34a")
            .withAlphaComponent(t.userInterfaceStyle == .dark ? 0.12 : 0.10)
    })
    static let appRedBg = Color(UIColor { t in
        UIColor(hex: t.userInterfaceStyle == .dark ? "fb7185" : "dc2626")
            .withAlphaComponent(t.userInterfaceStyle == .dark ? 0.12 : 0.08)
    })
    static let appAmberBg = Color(UIColor { t in
        UIColor(hex: t.userInterfaceStyle == .dark ? "fbbf24" : "b45309")
            .withAlphaComponent(t.userInterfaceStyle == .dark ? 0.12 : 0.10)
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
