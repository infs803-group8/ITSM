# IT Service Desk v5.0 → v6.0 修正记录

**日期**：2026-09-01  
**状态**：Approved correction baseline

## 1. 修正原因

v5.0 基线仍使用 `service_desk_dev` 和 `service_desk_final` 两个 Database Name，并把 SQLAlchemy `create_all()` 与生成的 `schema.sql` 作为不同结构路径；后续数据库最终设计已经决定所有环境统一使用完整 `service_desk`。API v1.0 同时允许 Required Role-aware Field 在 `null` 和省略之间变化，且 OpenAPI 没有可直接用于 Frontend Mock 的成功 Example。

## 2. 已完成修正

| 范围 | 旧规则 | v6.0/v1.1 新规则 |
|---|---|---|
| Database Name | 本地 `service_desk_dev`，RDS `service_desk_final` | 本地和 RDS 全部使用 `service_desk`。 |
| 开发表结构 | 容易被理解为成员分别建表 | A/B/C 各自在独立 Instance 中创建相同的完整 19 张表。 |
| Schema Source | SQLAlchemy `create_all()` 与 Release `schema.sql` 职责不清 | `backend/database/schema.sql` 是唯一可执行 Schema Contract；SQLAlchemy Models 必须匹配。 |
| Bootstrap | `Base.metadata.create_all()` | Empty Database 应用 Canonical SQL，再做 Schema Verification。 |
| Required Field | 可以为 null 或被省略 | Required Key 始终存在；无值或当前 Role 不可见时返回 JSON `null`。 |
| OpenAPI Mock | 只有 Schema，没有 Operation Example | 32 个 Operation 全部引用一个经过 Schema Validation 的成功 Example。 |
| Pending Resolution | `ResolutionView` 无法表示尚未确认的方案 | `summary` 立即返回；`type/resolved_at/auto_close_at` 在等待确认时为 null。 |
| Local CORS | 未冻结默认 Origin | 默认允许 `http://localhost:5173`；Final 使用 CloudFront 同 Origin `/api/*`。 |

## 3. 当前有效文件

1. `IT-Service-Desk-Unified-Project-Baseline-v6.0.md`
2. `IT-Service-Desk-Final-API-Specification-v1.1.md`
3. `IT-Service-Desk-OpenAPI-v1.1.yaml`
4. `IT-Service-Desk-Database-Final-Design-v1.1.md`
5. `IT-Service-Desk-MySQL-Schema-v1.0.sql`（DDL 未改变，继续作为 Canonical SQL 内容）

旧版 v5.0、API v1.0 和 Database Design v1.0 只作为历史，不再用于新开发或 Frontend Type Generation。

## 4. 验证结果

- OpenAPI 3.1.0 / Contract Version 1.1.0。
- 28 Paths、32 Operations、80 Schemas。
- 32 个 Operation Success Example，全部通过 Required/Type/Enum/Reference Schema Validation。
- Markdown 32 个 Method/Path 与 OpenAPI 完全一致。
- Database SQL 已在 MySQL 8.4 实际执行：19 张 InnoDB Table、35 个 Foreign Key、2 个 Audit Trigger。

