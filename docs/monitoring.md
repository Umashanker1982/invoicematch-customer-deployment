# Monitoring and observability requirements

What the customer's operations team must be able to see, and what wakes someone up.

## Signals each component already produces

| Source | Signal | Format |
|---|---|---|
| App | One `invoice_decided` line per invoice: route, rules, reader, fallback, AI latency, AI cost, grounding discards, breaker state (no invoice text, no bank details) | JSON log line |
| App start-up | `vault_login_ok`, `secret_loaded` (masked key), `vault_not_ready`, `vault_failed` | JSON log lines |
| Egress proxy | `egress_allowed`, `egress_denied`, `egress_error` with source, host, and port | JSON log lines |
| Vault | Every request: identity, path, operation, result (secret values HMAC-hashed) | Audit log file |
| All containers | Health status | Docker health checks |

## Metrics and alerts

| Metric | Normal | Alert | Severity |
|---|---|---|---|
| Service health (`/healthz`) | 200 | 2 failures in a row | **Page** |
| App restarts | 0 | More than 2 in 10 minutes | **Page** |
| `vault_failed` at start-up | Never | Any | **Page** |
| `egress_denied` to a host that is not the gateway | Rare | Any | Ticket to InfoSec (Sev 2) |
| AI fallback rate | Below 5% | Above 20% for 15 minutes | Ticket |
| AI latency p95 | Below 5 s | Above 10 s for 15 minutes | Ticket |
| AI cost per day | Below budget | Above 150% of budget | Ticket to the owner |
| Exception rate | 20–45% | Above 60%, or below 15% (possible rule failure) | Ticket; below 15% is a **page** |
| Vault secret reads by the app | One per start | Many in a short time | Ticket to InfoSec |

## Dashboards

1. **Service:** health, restarts, request rate, latency.
2. **AI:** calls, fallback rate, latency, cost per day (also visible on the SharedLLM dashboard).
3. **Security:** egress allowed vs denied by host; Vault reads by identity.
4. **Business:** invoices per day, auto-approved share, exceptions by rule.

## How it maps to the customer's tools

The containers write to standard output and one audit file. In production a log agent (for example Fluent Bit) ships them to the customer's logging platform (CloudWatch, Splunk, or Elastic), where the alerts above are rules. Nothing in the app needs to change.
