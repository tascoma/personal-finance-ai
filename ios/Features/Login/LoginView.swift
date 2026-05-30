import SwiftUI

struct LoginView: View {
    @State private var vm: LoginViewModel
    @FocusState private var focused: Field?

    private enum Field { case email, password }

    init(api: APIClient, auth: AuthStore) {
        _vm = State(initialValue: LoginViewModel(api: api, auth: auth))
    }

    var body: some View {
        ZStack {
            Color.appBackground.ignoresSafeArea()

            VStack(alignment: .leading, spacing: Space.xl) {
                header

                VStack(alignment: .leading, spacing: Space.lg) {
                    field(label: "Email") {
                        TextField("you@example.com", text: $vm.email)
                            .keyboardType(.emailAddress)
                            .textContentType(.username)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .focused($focused, equals: .email)
                            .submitLabel(.next)
                            .onSubmit { focused = .password }
                    }
                    field(label: "Password") {
                        SecureField("••••••••", text: $vm.password)
                            .textContentType(.password)
                            .focused($focused, equals: .password)
                            .submitLabel(.go)
                            .onSubmit { Task { await vm.submit() } }
                    }
                }

                if let message = vm.errorMessage {
                    Text(message)
                        .font(.footnote)
                        .foregroundStyle(Color.appRed)
                        .padding(.horizontal, Space.md)
                        .padding(.vertical, 10)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.appRedBg, in: RoundedRectangle(cornerRadius: Radius.sm))
                }

                submitButton
            }
            .frame(maxWidth: 360)
            .padding(.horizontal, Space.xl)
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: Space.md) {
            RoundedRectangle(cornerRadius: Radius.md)
                .fill(
                    LinearGradient(
                        colors: [.appAccent, .appAccent2],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .frame(width: 44, height: 44)
                .overlay(
                    Image(systemName: "chart.line.uptrend.xyaxis")
                        .font(.system(size: 20, weight: .semibold))
                        .foregroundStyle(Color.appOnAccent)
                )

            VStack(alignment: .leading, spacing: Space.xs) {
                Text("Personal Finance").eyebrow()
                Text("Sign in")
                    .font(.system(size: 26, weight: .semibold))
                    .foregroundStyle(Color.appTextPrimary)
            }
        }
    }

    private func field<Content: View>(label: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).eyebrow()
            content()
                .textFieldStyle(.plain)
                .font(.callout)
                .foregroundStyle(Color.appTextPrimary)
                .padding(.horizontal, Space.md)
                .padding(.vertical, 10)
                .background(Color.appSurface, in: RoundedRectangle(cornerRadius: Radius.sm))
                .overlay(
                    RoundedRectangle(cornerRadius: Radius.sm)
                        .strokeBorder(Color.appLine, lineWidth: 1)
                )
        }
    }

    private var submitButton: some View {
        Button {
            Task { await vm.submit() }
        } label: {
            HStack {
                Spacer()
                if vm.isSubmitting {
                    ProgressView().tint(Color.appOnAccent)
                } else {
                    Text("Sign in").font(.callout.weight(.semibold))
                }
                Spacer()
            }
            .padding(.vertical, 12)
            .background(Color.appAccent.opacity(vm.canSubmit ? 1 : 0.4),
                        in: RoundedRectangle(cornerRadius: Radius.sm))
            .foregroundStyle(Color.appOnAccent)
        }
        .disabled(!vm.canSubmit)
    }
}
