# IAM design (least privilege)

Every identity gets only what its current job needs. Each permission below is implemented in this repository, and the most important ones are proven by automated checks.

## Machine identities

| Identity | Type | Allowed | Explicitly denied | Where it is defined |
|---|---|---|---|---|
| `invoicematch-app` | Vault **AppRole** | `read` on `secret/data/invoicematch/llm` only | Read other secrets; write, delete, or list any secret | [`invoicematch-app.hcl`](../customer-env/vault/policies/invoicematch-app.hcl), [`init.sh`](../customer-env/vault/init.sh) |
| App process | Container user **uid 10001** | Run the web server; read its credentials volume | Root; write to its file system; any Linux capability; gaining privileges | [`docker-compose.yml`](../customer-env/docker-compose.yml) (`read_only`, `cap_drop: ALL`, `no-new-privileges`) |
| Egress proxy | Container user **uid 10002** | Open tunnels to allow-listed hosts | Root; write to its file system; any capability | [`egress-proxy/Dockerfile`](../customer-env/egress-proxy/Dockerfile), compose file |
| `vault-init` | Short-lived job with an admin token | Create the policy, role, and secrets once | Runs only at start-up, then exits | [`init.sh`](../customer-env/vault/init.sh) |
| CI/CD (GitHub Actions) | Workflow token | `contents: read` | Write to the repository; any other GitHub scope | [`customer-environment.yml`](../.github/workflows/customer-environment.yml) |

### Vault access policy for the app

```hcl
path "secret/data/invoicematch/llm" {
  capabilities = ["read"]
}
```

### AppRole token settings

| Setting | Value | Why |
|---|---|---|
| `token_ttl` / `token_max_ttl` | 15 minutes / 1 hour | The app needs the secret only at start-up |
| Token after use | Revoked immediately by the app (`revoke-self`) | No standing Vault session |
| `secret_id_ttl` | 24 hours | Limits the value of a stolen credential; re-issued on each deployment |
| Credentials delivery | Private volume, owner uid 10001, mode `0400`, mounted read-only | Only the app user can read them; never in images, env files, or the repository |

### Proven by automated checks

| Check | Result |
|---|---|
| App identity CAN read its own secret | PASS |
| App identity CANNOT read another team's secret (`secret/finance/erp`) | PASS |
| App identity CANNOT change its own secret | PASS |
| App identity CANNOT list secrets | PASS |
| App runs as a non-root user (uid 10001) | PASS |
| App file system is read-only | PASS |
| All Linux capabilities dropped and `no-new-privileges` | PASS |

## People and roles

| Role | Access | Not allowed |
|---|---|---|
| AP Specialist / AP Manager / Finance Controller / CFO | Use the app through the ingress; approve within their limit (auto ≤ $10k, AP Manager ≤ $25k, Controller ≤ $100k, CFO above) | Access Vault, servers, or configuration |
| Security reviewer | The only role that can clear an invoice with changed bank details | Approve ordinary invoices |
| Platform engineer (customer) | Deploy, restart, roll back; read logs | Read secret values; **approve invoices** (segregation of duties) |
| InfoSec (customer) | Manage Vault policies, rotate secrets, read the audit log, change the egress allow-list | Approve invoices |
| Vendor engineer | L3 support, through logs and screenshares only | Production or Vault access |

In production, people's roles come from the customer's identity provider (SSO + MFA). Access is reviewed every quarter by the AP Manager and InfoSec.

## Access policies

1. **Default deny.** Vault denies everything not granted; the egress proxy refuses every host not listed.
2. **No shared credentials.** Each component has its own identity.
3. **Short-lived over long-lived.** Vault tokens last minutes and are revoked after use.
4. **Changes need a ticket.** Policy, allow-list, or approval-limit changes go through the customer's change process (InfoSec or Compliance sign-off).
5. **Break-glass.** The Vault root token is used only for setup and emergencies; every use appears in the audit log.
