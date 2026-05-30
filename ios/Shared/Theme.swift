import SwiftUI

/// Design tokens mirroring the web frontend's radius/spacing scale
/// (frontend/src/styles/style.css: --r-*, .gap-*). Named constants so the
/// app's surfaces stay on the same rhythm as the React redesign.

enum Radius {
    static let xs: CGFloat = 4
    static let sm: CGFloat = 6
    static let md: CGFloat = 10
    static let lg: CGFloat = 14
}

enum Space {
    static let xs: CGFloat = 4
    static let sm: CGFloat = 8
    static let md: CGFloat = 12
    static let lg: CGFloat = 16
    static let xl: CGFloat = 24
}

extension View {
    /// The web `.card`: elevated surface + 1px hairline border + rounded corners.
    func appCardStyle(radius: CGFloat = Radius.md) -> some View {
        background(Color.appCard, in: RoundedRectangle(cornerRadius: radius))
            .overlay(
                RoundedRectangle(cornerRadius: radius)
                    .strokeBorder(Color.appLine, lineWidth: 1)
            )
    }
}

extension Text {
    /// The web `.page-eyebrow` / field-label / table-header treatment:
    /// small, uppercase, letter-spaced, tertiary.
    func eyebrow() -> some View {
        self
            .font(.system(size: 11, weight: .semibold))
            .textCase(.uppercase)
            .kerning(0.8)
            .foregroundStyle(Color.appTextTertiary)
    }
}
