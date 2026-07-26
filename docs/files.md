# Files API

**Namespace:** `anthropic.files` ·
**FFL:** `src/anthropic_handlers/ffl/files.ffl` ·
**Handlers:** `src/anthropic_handlers/handlers/files/files_handlers.py` ·
**Impl (`_lib`):** `src/anthropic_handlers/tools/_lib/files.py` ·
**CLIs:** `tools/upload-file.sh`, `list-files.sh`, `delete-file.sh` ·
**Tests:** `tests/test_files.py`, `tests/live/test_files_live.py`

## Overview

Wraps the Anthropic **Files API** — store documents on Anthropic's side so later Messages
calls reference them by `file_id` instead of re-uploading inline content. Best for RAG flows
where the same document is queried repeatedly. **3 event facets**: `UploadFile`, `ListFiles`,
`DeleteFile`. Reference:
`https://docs.anthropic.com/en/docs/build-with-claude/files-api`.

## How it works

`_files_api(client)` locates the SDK namespace **beta-first then GA** — `client.beta.files`
if present, else `client.files`, else a clear `RuntimeError` (the Files API shipped as a beta;
this forward-compats a future GA).

- **`upload_file`** — validates the local path, autodetects `mime_type` via `mimetypes` (falls
  back to `application/octet-stream`, or takes an explicit override), and calls
  `api.upload(file=(name, fh, mime))`. Returns id + metadata (`_file_to_dict`).
- **`list_files`** — `api.list(limit=…)`, reads `.data` off the cursor page, materialises the
  first page up to `limit`.
- **`delete_file`** — `api.delete(file_id)`, returns `{id, deleted, type}`.

The handler serialises the listing into the `files_json` bridge field.

## Fan-out

**Single-task per call — no fan-out.** Each facet is one API round-trip. Uploading many files
is a caller-side loop (or many independent tasks), not a fan-out facet.

## Data & fields

- `FileMetadata {id, type, filename, mime_type, size_bytes, created_at, downloadable}`
- `FileListing {count, files_json}` — **`files_json`** decodes to a list of `FileMetadata`.
- `FileDeletion {id, type, deleted}`.

## External libraries / binaries

- **`anthropic`** (pip, required); `mimetypes` + `pathlib` (stdlib). `[files]` extra declared
  but empty. No binary dependencies.

## Facets & workflows

| Facet | Kind | Effect / Cost | Purpose |
|---|---|---|---|
| `UploadFile(path, mime_type="")` | event | external / **cheap** | upload a local file, get `file_id` + metadata |
| `ListFiles(limit=50)` | event | external / **cheap** | list uploaded files, most-recent-first |
| `DeleteFile(file_id)` | event | external / **cheap** | delete a previously-uploaded file |

All `cheap` — file operations are storage/metadata round-trips, no inference.

## Cache / output

The Files API **is** the "output/cache" here: uploaded files persist **on Anthropic's side**
until explicitly deleted, referenced by `file_id` — nothing is written to `$FW_CACHE_ROOT`,
MinIO, or local disk. The uploaded document is consumed by
[`messages.CreateMessageWithFile`](messages.md) / [`compose.DocumentQA`](composition.md).

## Gotchas & notes

- **SDK surface drift.** `_files_api` tries `client.beta.files` then `client.files`; an
  `AttributeError`/`RuntimeError` here means an incompatible `anthropic` version — pin a recent
  release.
- **`mime_type` autodetect is by filename.** For content-typed uploads (e.g. force
  `application/pdf`) pass `mime_type` explicitly; unknown extensions fall back to
  `application/octet-stream`.
- **`downloadable`** on the metadata reflects the API's flag — user-uploaded files are
  generally not re-downloadable (only tool/skill-generated files are), so treat it as
  informational.

## Related specs

- [messages.md](messages.md) — `CreateMessageWithFile` references the `file_id` this area
  produces.
- [composition.md](composition.md) — `DocumentQA` chains `UploadFile` → `CreateMessageWithFile`.
- [architecture.md](architecture.md) — dispatch + the `files_json` bridge.
