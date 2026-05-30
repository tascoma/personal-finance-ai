interface Props {
  email?: string
  initials: string
}

export default function UserAvatar({ email, initials }: Props) {
  return (
    <div className="header-user-avatar" title={email}>
      {initials}
    </div>
  )
}
