# Operational runbook: InvoiceMatch in the customer environment

**Service:** InvoiceMatch (AI invoice-to-PO matching) · **Owner:** customer platform team · **Escalation:** InfoSec (secrets, egress), AP Manager (business impact), vendor L3 (code)

All commands run from the repository root. `C` is short for `docker compose -f customer-env/docker-compose.yml`:

```bash
alias C='docker compose -f customer-env/docker-compose.yml'
```

## 1. Service overview

| Component | Purpose | Healthy when |
|---|---|---|
| `ingress` | Entry point at `http://127.0.0.1:8080` | `curl -fsS http://127.0.0.1:8080/healthz` returns `{"status":"ok"}` |
| `app` | InvoiceMatch | `C ps app` shows `healthy` |
| `vault` | Secrets and audit log | `C exec vault vault status` shows `Sealed false` |
| `egress-proxy` | The only route to the AI gateway | `C ps egress-proxy` shows `healthy` |
| `vault-init` | One-time setup | `C ps -a vault-init` shows `Exited (0)` |

**Dependencies:** SharedLLM gateway (`api.sharedllm.com`). If it is down, the app keeps working with its rules reader and sends unreadable invoices to people.

## 2. What "normal" looks like

| Signal | Normal | Where to see it |
|---|---|---|
| Health endpoint | 200 OK | `curl http://127.0.0.1:8080/healthz` |
| AI enabled | `"ai_available": true` | `curl http://127.0.0.1:8080/api/config` |
| Egress | Only `egress_allowed` to `api.sharedllm.com`; occasional `egress_denied` is worth reading | `C logs egress-proxy` |
| Decisions | Exception rate 20–45%; fallback rate below 5% | `C logs app \| grep invoice_decided` |
| Secret reads | One `secret/data/invoicematch/llm` read per app start | `C exec vault tail /vault/logs/audit.log` |

## 3. Routine operations

| Task | Commands |
|---|---|
| **Start** | `bash scripts/fetch_app.sh` then `C --env-file .env up -d --build` |
| **Verify** after any change | `VAULT_ROOT_TOKEN=... bash scripts/verify_environment.sh` (expect `ALL CHECKS PASSED`) |
| **Stop** | `C down` (keeps nothing sensitive: Vault dev data is in memory) |
| **Restart the app** | `C restart app` |
| **Upgrade the app** | Set `APP_COMMIT` to the new tested release → `bash scripts/fetch_app.sh` → `C up -d --build app` → verify |
| **Rotate the AI key** | Create a new key in SharedLLM → `C exec -e VAULT_TOKEN=... vault vault kv put secret/invoicematch/llm SHAREDLLM_KEY=<new>` → update `SEED_SHAREDLLM_KEY` in `.env` → `C restart app` → revoke the old key in SharedLLM |
| **Re-issue app credentials** (secret ID expires after 24 h) | With the current key in `SEED_SHAREDLLM_KEY` in `.env`: `C --env-file .env run --rm vault-init` → `C restart app` (the setup job also rewrites the key, so it must be the current one) |
| **Change the egress allow-list** | InfoSec ticket → edit `customer-env/egress-proxy/allowlist.txt` → `C up -d --build egress-proxy` → verify |

## 4. Safety switches

| Switch | Effect | How |
|---|---|---|
| **Stop automatic approvals** | Every invoice goes to people; nothing is lost | Set `AUTO_APPROVE_LIMIT: "0"` under `app.environment` → `C up -d app` |
| **Rules only (no AI)** | No calls leave the network | Set `LLM_MODE: rules` → `C up -d app` |
| **Cut all egress** | Same as rules only, enforced at the network | `C stop egress-proxy` |

## 5. Incident playbooks

### 5.1 App is down or unhealthy
1. `C ps -a` → is `app` restarting? Then `C logs app --tail 50`.
2. `vault_failed` in the log → go to 5.2.
3. Python error after an upgrade → **roll back**: set `APP_COMMIT` to the previous release, `bash scripts/fetch_app.sh`, `C up -d --build app`, verify.

### 5.2 App cannot get its secret from Vault
1. `C exec vault vault status`: sealed or down? Restart Vault (`C restart vault`), then re-run setup (`C --env-file .env run --rm vault-init` with the current key in `.env`, because dev mode loses data on restart) and `C restart app`.
2. `HTTP Error 400` in `vault_not_ready` lines: the secret ID has expired or is wrong → re-issue credentials (section 3).
3. `HTTP Error 403`: the policy was changed → compare with `customer-env/vault/policies/invoicematch-app.hcl`; InfoSec restores it.

### 5.3 AI calls failing (fallback rate high)
1. `C logs egress-proxy | grep egress_` → `egress_denied` for the gateway host means the allow-list is wrong; `egress_error` means the gateway is unreachable.
2. Check the SharedLLM status and dashboard (requests, errors, spend).
3. Business impact is low: the rules reader takes over and unreadable invoices go to people. If it lasts more than 1 hour, inform the AP Manager.

### 5.4 Unexpected egress attempts (`egress_denied` to unknown hosts)
1. **Severity 2, InfoSec.** Do not add the host to the allow-list.
2. Record the time, source, and host from `C logs egress-proxy`.
3. Check which release is running (`APP_COMMIT`) and whether it changed recently.

### 5.5 Secret exposed (key seen in a log, ticket, or screenshot)
1. Revoke the key in SharedLLM **first**.
2. Create a new key and store it in Vault (section 3, rotate).
3. `C restart app`, verify, and review the SharedLLM usage log for the exposure window.
4. Target: done within 15 minutes.

### 5.6 Wrong approval reported
1. Switch off automatic approvals (section 4).
2. Find the decision in `C logs app | grep invoice_decided` and inform the AP Manager and Compliance.
3. Vendor L3 adds the invoice to the test set before the fix is released.

## 6. The 2 AM checklist
1. **Up?** `curl -fsS http://127.0.0.1:8080/healthz`
2. **Getting its secret?** `C logs app | grep -E 'secret_loaded|vault_failed'`
3. **Reaching only the gateway?** `C logs egress-proxy | tail`
4. **Deciding safely?** If unsure, set the auto-approve limit to 0 and investigate in the morning. Nothing is lost; invoices wait for people.

## 7. Contacts and severity

| Severity | Example | Response |
|---|---|---|
| Sev 1 | App down at month-end; wrong approval | 15 minutes; page the platform on-call |
| Sev 2 | Unexpected egress; AI down for more than 1 hour | 4 hours; InfoSec or platform |
| Sev 3 | Single invoice question | Next business day; AP team |
