---
name: "setup-storage"
description: "Set up Supabase Storage for file uploads"
metadata:
  author: agent-webapp-template
  version: 1.0.0
---

Set up Supabase Storage as the blob store for file uploads: create a bucket, configure env vars, and wire the upload/delete service into a route.

## How it works

Files are uploaded from the FastAPI backend to a Supabase Storage bucket using the `supabase-py` client. The service role key is used server-side (it bypasses RLS). Each file gets a UUID-based key; the returned public URL is what you store in the database alongside the record that owns the file.

The `supabase` package is already installed and `get_storage_client()` is already wired in `backend/app/dependencies/`.

---

## Steps

### 1. Create the bucket in Supabase
Use the MCP tool to create a bucket, or do it in the Supabase dashboard under **Storage**:

- **Name:** match the `STORAGE_BUCKET` env var (default: `uploads`)
- **Public:** enable if files should be served without auth; disable for private files requiring signed URLs

To create via dashboard: Storage → New bucket → set name and public/private.

### 2. Set environment variables
Add to `.env` (shape is already in `.env.example`):

```
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
STORAGE_BUCKET=uploads
```

Get these from the Supabase dashboard → **Settings → API**. Use the **service role** key (not anon) — the backend uploads on behalf of users and needs to bypass RLS.

### 3. Add a file upload route

Inject `get_storage_client` and `settings` into the route, call `upload_file` from the storage service, and persist the returned URL.

```python
from fastapi import APIRouter, Depends, UploadFile
from supabase import Client

from app.core.config import settings
from app.dependencies import get_storage_client
from app.services.storage import upload_file

router = APIRouter(prefix="/files", tags=["files"])

@router.post("/", status_code=201)
async def upload(
    file: UploadFile,
    client: Client = Depends(get_storage_client),
):
    data = await file.read()
    url = upload_file(
        client=client,
        bucket=settings.storage_bucket,
        data=data,
        filename=file.filename or "upload",
    )
    return {"url": url}
```

Use the optional `folder` argument to organise files by resource type (e.g. `folder="avatars"`).

### 4. Delete a file
Call `delete_file` from the storage service when a record that owns a file is deleted:

```python
from app.services.storage import delete_file

delete_file(client=client, bucket=settings.storage_bucket, url=record.file_url)
```

### 5. Store the URL in the database
Add a nullable `file_url: str | None` column to the relevant SQLAlchemy model and Pydantic schema. Save the URL returned by `upload_file` during create/update.

### 6. Private buckets and signed URLs
If the bucket is private, generate a time-limited signed URL instead of using the public URL:

```python
response = client.storage.from_(settings.storage_bucket).create_signed_url(key, expires_in=3600)
signed_url = response["signedURL"]
```

Return the signed URL from the route rather than the stored public URL.

---

## Verification
Upload a test file via the route and confirm:
1. The file appears in the Supabase dashboard under **Storage → uploads**.
2. The returned URL resolves in a browser (for public buckets).
3. Calling the delete path removes the file from the bucket.
