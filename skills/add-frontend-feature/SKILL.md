---
name: "add-frontend-feature"
description: "Add a page or feature to the React frontend"
metadata:
  author: agent-webapp-template
  version: 1.0.0
---

Add a new page or feature to the React frontend. Replace `<Feature>` with the actual feature name throughout.

## Pattern
Pages own layout and user interaction only. Data fetching and state live in a custom hook. The `api` client from `src/lib/api.ts` handles all HTTP calls — no raw `fetch` in components.

## Steps

### 1. Types (`src/types/<feature>.ts`)
Define TypeScript types that mirror the backend Pydantic schemas. Field names must match the JSON keys returned by the API.

```typescript
export interface Feature {
  id: number;
  name: string;
  // match backend schema field names exactly
}

export interface CreateFeatureRequest {
  name: string;
}
```

### 2. Hook (`src/hooks/use<Feature>.ts`)
Own all data fetching and mutation state here. Keep components free of `async` logic.

```typescript
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Feature, CreateFeatureRequest } from "../types/feature";

export function useFeature() {
  const [items, setItems] = useState<Feature[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    try {
      setItems(await api.get<Feature[]>("/features/"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function create(data: CreateFeatureRequest) {
    const item = await api.post<Feature>("/features/", data);
    setItems((prev) => [...prev, item]);
  }

  async function remove(id: number) {
    await api.delete(`/features/${id}`);
    setItems((prev) => prev.filter((i) => i.id !== id));
  }

  return { items, loading, error, create, remove };
}
```

### 3. Page component (`src/pages/<Feature>Page.tsx`)
Keep it thin — layout, iteration, and forwarding user actions to the hook.

```tsx
import { useFeature } from "../hooks/useFeature";

export default function FeaturePage() {
  const { items, loading, error, create, remove } = useFeature();

  if (loading) return <p>Loading…</p>;
  if (error) return <p>Error: {error}</p>;

  return (
    <div>
      <h1>Features</h1>
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            {item.name}
            <button onClick={() => remove(item.id)}>Delete</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

### 4. Register the route
Add the page to the route definitions in `App.tsx`:

```tsx
import FeaturePage from "./pages/FeaturePage";

<Route path="/features" element={<FeaturePage />} />
```

Wrap in `<ProtectedRoute>` if the page requires authentication.

### 5. Add navigation
Add a link to the new page from your nav bar or home page:

```tsx
import { Link } from "react-router-dom";

<Link to="/features">Features</Link>
```

### 6. Backend route check
Confirm the FastAPI route the hook calls exists and returns the expected schema. If it doesn't, use `/add-resource` to create it first.

## Verification
Run `npm run dev` and walk through the golden path:
- Data loads on mount.
- Create and delete actions update the list without a full reload.
- Errors surface in the UI rather than the console.
- No CORS errors in the browser network tab.
