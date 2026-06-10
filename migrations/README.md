# Database Migrations

Alembic migration scripts live here. Generate new revisions with:

```powershell
alembic revision --autogenerate -m "describe change"
```

Apply migrations with:

```powershell
alembic upgrade head
```
