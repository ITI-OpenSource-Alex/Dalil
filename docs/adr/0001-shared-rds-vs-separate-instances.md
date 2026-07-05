# ADR 0001: Shared RDS Instance vs. Separate Instances per Service

* **Status**: Accepted
* **Date**: 2026-06-28
* **Deciders**: Ahmed Mounir (Gliitchhh410) & Antigravity

---

## Context

The GOA platform is composed of 9 microservices, 5 of which require persistent database storage:
1. User Service (`user_db`)
2. Orchestration Service (`orchestration_db`)
3. RAG Service (`rag_db`)
4. Writing Service (`writing_db`)
5. Exam Service (`exam_db`)

We need to decide on the database deployment topology in AWS (Staging and Production environments) that balances budget constraints, management overhead, and architectural isolation.

---

## Alternatives Considered

### Option A: Separate RDS Instance per Service
Host a completely independent AWS RDS Postgres database cluster for each of the 5 services.
* **Pros**: 
  * **Complete Isolation**: Direct CPU, RAM, and IOPS isolation. A resource-heavy similarity query on `rag_db` cannot starve resources for user authentication on `user_db`.
  * **Independent Maintenance**: Custom patching, backup, and restore schedules per service.
* **Cons**:
  * **High Costs**: Standard multi-AZ db.t3.medium RDS instances cost ~$50–$150/month each. Operating 5 separate database clusters in staging alone would cost upwards of $250–$750/month.
  * **High Management Overhead**: Requires managing, monitoring, and backing up 5 individual AWS resources.

### Option B: Shared Schema on a Single Database
Host a single RDS instance and a single database schema, where all tables for all services reside together.
* **Pros**:
  * **Cost-Efficient**: Minimum possible database footprint.
  * **Simpler Setup**: One database connection string to manage.
* **Cons**:
  * **No Logical Separation**: Any service can read/write to tables owned by other services, violating the database-per-service pattern.
  * **High Risk of Coupling**: Risk of developers writing cross-service SQL joins, breaking domain boundaries.

---

## Decision

We chose **Option C (Hybrid)**: **A single shared RDS PostgreSQL database instance hosting separate logical databases (`user_db`, `rag_db`, `orchestration_db`, etc.) with strict service-specific access credentials.**

---

## Consequences

* **Pros**:
  * **Cost Efficiency**: We pay for only one RDS instance in staging and production, resulting in substantial savings.
  * **Logical Isolation**: Separate logical databases prevent database-level coupling. The user service has no credentials to connect to `rag_db`, and vice versa.
  * **Simple Backups**: A single RDS snapshot captures the state of the entire system for disaster recovery.
* **Cons**:
  * **Noisy Neighbor Effect**: Since all databases share the same CPU/RAM/disk IOPS, a heavy workload on RAG search can temporarily degrade response times for User or Orchestration services.
  * **Connection Limits**: The cumulative database connection count from all 5 services could overwhelm the single RDS instance.
* **Mitigation**:
  * **RDS Proxy**: We deploy AWS RDS Proxy in front of the database instance. This handles connection pooling, throttles excessive requests, and prevents connection exhaustion.
  * **Performance Monitoring**: Set up CloudWatch alarms on RDS CPU utilization > 80% to scale up the shared instance size dynamically.
