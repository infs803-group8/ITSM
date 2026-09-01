# System architecture

React frontend → FastAPI backend → MySQL. Attachment bytes transfer through S3
presigned URLs; the backend stores metadata and enforces access.
