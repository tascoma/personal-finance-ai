import SwiftUI

struct LoginView: View {
    @State private var vm: LoginViewModel

    init(api: APIClient, auth: AuthStore) {
        _vm = State(initialValue: LoginViewModel(api: api, auth: auth))
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Email", text: $vm.email)
                        .keyboardType(.emailAddress)
                        .textContentType(.username)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    SecureField("Password", text: $vm.password)
                        .textContentType(.password)
                }

                if let message = vm.errorMessage {
                    Section {
                        Text(message)
                            .foregroundStyle(.red)
                    }
                }

                Section {
                    Button {
                        Task { await vm.submit() }
                    } label: {
                        HStack {
                            Spacer()
                            if vm.isSubmitting {
                                ProgressView()
                            } else {
                                Text("Sign in")
                            }
                            Spacer()
                        }
                    }
                    .disabled(!vm.canSubmit)
                }
            }
            .navigationTitle("Personal Finance")
        }
    }
}
