---
name: "add-auth"
description: "Add Supabase Auth JWT verification, current_user dependency, protected routes, frontend and iOS auth flow"
metadata:
  author: agent-webapp-template
  version: 1.0.0
---

Integrate Supabase Auth into the backend and frontend: verify JWTs, expose a `current_user` dependency, protect routes, and wire the auth flow in React and iOS.

## How it works

Supabase Auth issues JWTs signed with your project's JWT secret. The FastAPI backend verifies the token on every protected request — no session table needed. The frontend and iOS app handle sign-in/sign-up via the Supabase client and pass the token in the `Authorization` header.

---

## Backend

### 1. Install PyJWT
```bash
uv add "pyjwt[cryptography]"
```

### 2. Add the JWT secret to config (`backend/app/core/config.py`)
```python
supabase_jwt_secret: str
```

Add to `.env` and `.env.example`:
```
# From Supabase dashboard → Settings → API → JWT Secret
SUPABASE_JWT_SECRET=your-jwt-secret-here
```

### 3. Auth dependency (`backend/app/dependencies/auth.py`)
Decode and verify the Supabase JWT on every request. Raise `401` if the token is missing, expired, or invalid.

```python
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.core.config import settings

bearer = HTTPBearer()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
) -> dict:
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
```

### 4. Protect routes
Add `current_user: dict = Depends(get_current_user)` to any route that requires authentication:

```python
from app.dependencies.auth import get_current_user

@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    return {"user_id": current_user["sub"], "email": current_user.get("email")}
```

The `sub` claim is the Supabase user UUID. Store it in your database records to scope data per user.

---

## React frontend

### 1. Install the Supabase JS client
```bash
cd frontend && npm install @supabase/supabase-js
```

### 2. Create the Supabase client (`frontend/src/lib/supabase.ts`)
```typescript
import { createClient } from "@supabase/supabase-js";

export const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY,
);
```

Add to `frontend/.env.local` (and document in `frontend/.env.example`):
```
VITE_SUPABASE_URL=https://<ref>.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key-here
```

Use the **anon key** in the frontend — not the service role key.

### 3. Auth helpers
Sign up, sign in, and sign out via the Supabase client:

```typescript
// Sign up
const { error } = await supabase.auth.signUp({ email, password });

// Sign in
const { data, error } = await supabase.auth.signInWithPassword({ email, password });

// Sign out
await supabase.auth.signOut();

// Get current session
const { data: { session } } = await supabase.auth.getSession();
```

### 4. Pass the token to the API
Include the JWT in every authenticated API request:

```typescript
const { data: { session } } = await supabase.auth.getSession();
const response = await fetch("/api/me", {
  headers: { Authorization: `Bearer ${session?.access_token}` },
});
```

---

## iOS

### 1. Add Supabase Swift SDK via Swift Package Manager
In Xcode → **File → Add Package Dependencies**:
```
https://github.com/supabase/supabase-swift
```
Add the `Auth` and `Supabase` targets.

### 2. Supabase client (`Core/SupabaseClient.swift`)
```swift
import Supabase

let supabase = SupabaseClient(
    supabaseURL: URL(string: Config.supabaseURL)!,
    supabaseKey: Config.supabaseAnonKey
)
```

Add `supabaseURL` and `supabaseAnonKey` to `Config.swift`, sourced from scheme environment variables.

### 3. Auth flow
```swift
// Sign in
try await supabase.auth.signIn(email: email, password: password)

// Get session token for API calls
let session = try await supabase.auth.session
let token = session.accessToken

// Sign out
try await supabase.auth.signOut()
```

### 4. Pass the token to the API
Add the token to `APIClient` requests:

```swift
var request = URLRequest(url: ...)
request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
```

---

## Verification
1. Sign in via the frontend or iOS app and confirm a session is returned.
2. Call a protected route with the token — expect `200`.
3. Call a protected route without a token — expect `401`.
4. Call a protected route with an expired token — expect `401` with "Token expired".
