# 0006. Text-only storage: media is read, converted to text, deleted

Date: 2026-10-28
Status: Accepted

## Context

Storing images, audio and video would fill a free server's disk, raise privacy risk and complicate backups. What people need later is findable text.

## Decision

Every attachment is read into text (vision reading, transcription, video understanding) and the media is then deleted, locally and remotely. Only text is kept: the user's words in the raw layer and read content as derived, labelled found content. EXIF is stripped before any image leaves the server. Enforced by the principle test `test_p02_media_deleted_after_read`.

## Consequences

- Easier: Small databases, simple backups, strong privacy.
- Harder: The original screenshot or recording cannot be shown again.

Blueprint: §3, §7.2.
