# Personal Finance AI — iOS

Native SwiftUI companion app for the [personal-finance-ai](../) backend. Lives in the monorepo so backend and iOS changes can land atomically.

Min target: **iOS 17**. No SPM runtime dependencies — URLSession + SwiftUI Charts only.

## Bootstrap

The Xcode project is generated from [project.yml](project.yml) via [XcodeGen](https://github.com/yonaskolb/XcodeGen) — the `.xcodeproj` is gitignored.

```bash
brew install xcodegen
cd ios
xcodegen
open PersonalFinanceAI.xcodeproj
```

In Xcode, pick a scheme from the toolbar:

| Scheme  | Backend                                                  |
| ------- | -------------------------------------------------------- |
| Debug   | `http://127.0.0.1:8000` (run the backend locally)        |
| Staging | `https://personal-finance-agent-1-tqet.onrender.com`     |
| Release | `https://personal-finance-agent-ipuu.onrender.com`       |

Set your Apple developer team in Xcode → target → Signing & Capabilities. The xcconfig leaves `DEVELOPMENT_TEAM` blank so this file stays portable.

## Project layout

```
App/          @main entry, root view, environment wiring
Config/       xcconfig per build configuration
Core/
  Networking/ APIClient, TokenRefresher actor, Endpoint, JSON coding (Decimal-as-string)
  Auth/       AuthStore (@Observable, @MainActor)
  Models/     Swift mirrors of backend Pydantic schemas
Features/
  Login/      Email+password sign-in
  Home/       Phase 1 placeholder (replaced by Dashboard in Phase 2)
Shared/       Code shared with the widget extension (Phase 5)
```

## Phase status

- [x] **Phase 1** — Scaffold + login. Cookie-backed refresh on relaunch.
- [ ] **Phase 2** — Dashboard (4 tabs, 5 charts via SwiftUI Charts).
- [ ] **Phase 3** — Statements (Balance Sheet, Income, Cash Flow) with period picker.
- [ ] **Phase 4** — Face ID / Touch ID app lock.
- [ ] **Phase 5** — Home Screen widget (WidgetKit).
- [ ] **Phase 6** — Push notifications (backend + iOS, period status change).

See [`../.claude/plans/plan-a-feature-for-sequential-gizmo.md`](../) for the full plan.

## Auth model

- Login `POST /auth/login` returns `access_token` in JSON; the **refresh token is set as an HttpOnly cookie** scoped to `/api/v1/auth` (30-day TTL).
- `URLSession`'s `HTTPCookieStorage.shared` persists that cookie across app launches.
- On launch, `RootView.bootstrap` calls `POST /auth/refresh` (cookie carries automatically). If it succeeds, the user is signed in without a password prompt.
- `APIClient.perform()` automatically retries once on 401 after refreshing. Concurrent 401s coalesce through `TokenRefresher` (an actor) so only one `/refresh` ever runs at a time.

## Monetary precision

The backend serializes all `Decimal` values as JSON **strings**. Swift models use the `@DecimalString` / `@OptionalDecimalString` property wrappers from [`Core/Networking/JSONCoding.swift`](Core/Networking/JSONCoding.swift). Convert to `Double` only at the chart boundary — never store doubles in models.

## Local dev against `127.0.0.1`

`Debug.xcconfig` sets `API_BASE_URL=http://127.0.0.1:8000` and the Info.plist enables `NSAppTransportSecurity > NSAllowsLocalNetworking`. The simulator can reach the host's loopback at this address; for a physical device, swap in your Mac's LAN IP.

Backend must be running:

```bash
cd ../backend
uv run python -m app.main
```

## Adding a file

Sources are picked up by directory globs in `project.yml`. After adding a file in `App/`, `Core/`, `Features/`, or `Shared/`, rerun `xcodegen` to refresh the Xcode project.

## Without XcodeGen

If you'd rather manage the Xcode project by hand, create a SwiftUI iOS app target, drag the four source folders into Xcode, and apply the xcconfigs via Project → Info → Configurations. Add `API_BASE_URL` (string, value `$(API_BASE_URL)`), `APNS_SANDBOX` (string, value `$(APNS_SANDBOX)`), and `NSAppTransportSecurity > NSAllowsLocalNetworking = YES` to the Info.plist. Committing the `.xcodeproj` requires removing it from `.gitignore`.
