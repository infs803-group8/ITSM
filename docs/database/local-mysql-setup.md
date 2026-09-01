# Local MySQL setup

Members A–C each run MySQL 8.4 locally with database `service_desk` and the
complete `backend/database/schema.sql`.

```powershell
docker compose -f docker-compose.local.yml up -d mysql
```
