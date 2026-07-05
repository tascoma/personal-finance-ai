---
name: "setup-frontend"
description: "Wire up the React app: API client, env config, routing, auth state"
metadata:
  author: agent-webapp-template
  version: 1.0.0
---

Wire up the React frontend: environment config, API client, auth state, and basic routing. Run from the `frontend/` directory unless noted.

The template ships a minimal Vite + React + TS app (api client at `src/lib/api.ts`, a `/api` proxy, and a health-check page). This skill layers routing and auth on top of that base — you are not starting from an empty folder.

## Steps

### 1. Install dependencies
```bash
npm install
```

Install routing and (if using auth) the Supabase JS client:
```bash
npm install react-router-dom
npm install @supabase/supabase-js   # only if using Supabase Auth
```

### 2. Environment config
Create `frontend/.env.local` for local dev values (gitignored) and `frontend/.env.example` to document the shape:

```
VITE_API_URL=http://localhost:8000
VITE_SUPABASE_URL=https://<ref>.supabase.co   # if using auth
VITE_SUPABASE_ANON_KEY=your-anon-key-here     # if using auth
```

For production these are set as environment variables on the Render Static Site.

### 3. API client (`frontend/src/lib/api.ts`)
A thin fetch wrapper that reads the base URL from env and attaches the auth token when present.

```typescript
const BASE = import.meta.env.VITE_API_URL ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}/api${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: (path: string) => request<void>(path, { method: "DELETE" }),
};
```

If auth is enabled, get the session token from Supabase and pass it as a header — see the `/add-auth` skill.

### 4. Routing (`frontend/src/main.tsx`)
Wrap the app in a router:

```tsx
import { BrowserRouter } from "react-router-dom";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
```

Define routes in `App.tsx`:

```tsx
import { Routes, Route } from "react-router-dom";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/login" element={<LoginPage />} />
    </Routes>
  );
}
```

### 5. Auth state (if using Supabase Auth)
Create an auth context to share session state across the app:

```tsx
// src/lib/auth.tsx
import { createContext, useContext, useEffect, useState } from "react";
import { Session } from "@supabase/supabase-js";
import { supabase } from "./supabase";

const AuthContext = createContext<Session | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_, s) => setSession(s));
    return () => subscription.unsubscribe();
  }, []);

  return <AuthContext.Provider value={session}>{children}</AuthContext.Provider>;
}

export const useSession = () => useContext(AuthContext);
```

Wrap `<App />` in `<AuthProvider>` in `main.tsx`.

### 6. Protected routes
Redirect unauthenticated users away from protected pages:

```tsx
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const session = useSession();
  if (!session) return <Navigate to="/login" replace />;
  return <>{children}</>;
}
```

Use it in your route definitions:
```tsx
<Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
```

## Verification
```bash
npm run dev
```

- The app loads at `http://localhost:5173`.
- A fetch to `/api/` (proxied to the backend) returns a response without CORS errors.
- If auth is wired, signing in sets the session and redirects to the protected route.
