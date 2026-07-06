---
name: "test-frontend"
description: "Set up Vitest + React Testing Library and write frontend component and integration tests"
metadata:
  author: agent-webapp-template
  version: 1.0.0
---

Set up Vitest and React Testing Library for the React frontend and write component/integration tests. This is the frontend counterpart to `/add-tests` (which covers backend pytest). Run from `frontend/`.

## First-time setup (run once)

### 1. Install dev dependencies
```bash
npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
```

### 2. Configure Vitest (`frontend/vite.config.ts`)
Add a `test` block to the existing Vite config so tests run in a jsdom DOM environment with a global setup file:

```typescript
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts",
  },
});
```

### 3. Test setup file (`frontend/src/test/setup.ts`)
```typescript
import "@testing-library/jest-dom";
```

### 4. Add the test script (`frontend/package.json`)
```json
"scripts": {
  "test": "vitest"
}
```

## Writing tests

### Component test (`src/components/Foo.test.tsx`)
Render the component and assert on what the user sees:

```tsx
import { render, screen } from "@testing-library/react";
import { Foo } from "./Foo";

test("renders the heading", () => {
  render(<Foo title="Hello" />);
  expect(screen.getByRole("heading", { name: "Hello" })).toBeInTheDocument();
});
```

### Mock the API client
Never hit the real backend from a unit test. Mock the `api` wrapper (`src/lib/api.ts`, from `/setup-frontend`):

```tsx
import { vi } from "vitest";
import { api } from "../lib/api";

vi.mock("../lib/api", () => ({
  api: { get: vi.fn().mockResolvedValue([{ id: 1, name: "alpha" }]) },
}));
```

Then render the component that calls `api.get` and assert it shows the mocked data (use `findBy*` queries to await the async render).

## Verification
```bash
npm run test
```

All tests pass. Use `npm run test -- --watch` while developing and `npm run test -- --run` for a single CI-style run.
