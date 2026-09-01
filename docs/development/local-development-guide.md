# Local development guide

Members A–C use separate complete local MySQL instances. Member A uses the shared
development S3 bucket for attachment work. Member D can start with MSW mocks and
then point `VITE_API_BASE_URL` to a backend address.

Never commit database passwords or AWS credentials.
