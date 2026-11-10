# Security design summary

**Principle:** the customer controls everything. The app has no internet access, holds no stored secrets, and can read exactly one secret. *AI reads; rules decide; people approve.* The AI never approves money.

## Controls

| # | Threat | Control | Evidence |
|---|---|---|---|
| S-1 | Data exfiltration or calls to unapproved services | Private network with no internet route; one egress path through an allow-list proxy | Checks: *no direct internet access*, *egress proxy refuses example.com*, *allows only api.sharedllm.com* |
| S-2 | Secret leakage through code, images, or config | Key stored only in Vault; fetched at start-up into process memory; never in env files, compose, images, or the repository | Checks: *key not in container configuration*, *no real key stored in this repository* |
| S-3 | Over-privileged service account | Vault policy grants `read` on one path; AppRole tokens are short-lived and revoked after use | Checks: *CANNOT read another team's secret*, *CANNOT change*, *CANNOT list* |
| S-4 | Undetected secret access | Vault file audit device records every request (values hashed) | Check: *Vault audit log recorded the app's secret read* |
| S-5 | Container breakout or tampering | Non-root user, read-only file system, all capabilities dropped, `no-new-privileges` | Checks in section 5 of the verification |
| S-6 | Direct access to internal services | Only the ingress publishes a port; Vault and the app are unreachable from outside | Checks: *Vault not reachable*, *app port 8000 not reachable* |
| S-7 | Key printed in logs | Only the last 4 characters are logged (`...0000`) | Unit test `test_loads_key_from_vault_and_starts_server_without_printing_it` |
| S-8 | Unreviewed code deployed | The app is fetched at a **pinned commit** of a tested release; CI verifies every change | [`fetch_app.sh`](../scripts/fetch_app.sh), CI badge |
| S-9 | Sensitive data sent to the AI | Bank details are removed before the AI call (inside InvoiceMatch); only redacted text leaves through the proxy | InvoiceMatch tests ([source](https://github.com/Umashanker1982/invoicematch)) |
| S-10 | Prompt injection in invoice text | The AI has no tools and cannot decide; written rules decide | InvoiceMatch tests and live demo tour 4 |

## Data flows

| Flow | Data | Protection |
|---|---|---|
| Staff → ingress → app | Invoice text, approvals | Internal network only; production adds TLS and SSO |
| App → Vault | AppRole login, one secret read | Private network; short-lived token; audited |
| App → egress proxy → AI gateway | Redacted invoice text | HTTPS end to end (the proxy only tunnels and cannot read it); one allowed host |
| App logs | Decisions, timings, cost | No invoice text, no bank details, no keys |

## Known limits of the simulation (and the production answer)

| Here | Production |
|---|---|
| Vault runs in **dev mode** (in memory, unsealed, root token) | HA Vault with auto-unseal and no root token in daily use |
| AppRole credentials on a volume | Vault Agent auto-auth or cloud IAM auth |
| Ingress is plain HTTP on localhost | TLS on the internal load balancer, behind SSO |
| A placeholder key is used in CI | The real key is written into Vault by InfoSec; CI can test a real call if the `SHAREDLLM_KEY` repository secret is set |
