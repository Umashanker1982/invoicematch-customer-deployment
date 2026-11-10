# Knowledge transfer guide

Goal: the customer's teams can run, change, and troubleshoot InvoiceMatch **without the vendor**.

## 1. Who needs what

| Team | Must be able to | Read first |
|---|---|---|
| **Platform team** (owner) | Start, stop, upgrade, roll back, verify; handle alerts | [runbook.md](runbook.md), [deployment_architecture.md](deployment_architecture.md) |
| **InfoSec** | Manage Vault policies, rotate keys, review the audit log and egress log, approve allow-list changes | [iam_design.md](iam_design.md), [security_design.md](security_design.md) |
| **AP Manager** (business owner) | Know the safety switch; own business rules and limits | Runbook section 4, InvoiceMatch [scope](https://github.com/Umashanker1982/invoicematch/blob/main/scoping/scope.md) |
| **On-call engineers** | Follow the 2 AM checklist and playbooks | Runbook sections 5–6 |

## 2. Getting started (about 30 minutes, on a Linux, macOS, or WSL machine with Docker)

```bash
git clone https://github.com/Umashanker1982/invoicematch-customer-deployment.git
cd invoicematch-customer-deployment
cp .env.example .env              # set VAULT_ROOT_TOKEN to a long random value
bash scripts/fetch_app.sh         # gets InvoiceMatch at the pinned release
docker compose --env-file .env -f customer-env/docker-compose.yml up -d --build
set -a; . ./.env; set +a
bash scripts/verify_environment.sh   # expect: ALL CHECKS PASSED
```

Open http://127.0.0.1:8080 to use the app. To use real AI, put a SharedLLM key in `SEED_SHAREDLLM_KEY` in `.env` before starting; it goes into Vault, not into the app's settings.

## 3. How it fits together (the 5-minute explanation)

1. Staff reach the app only through the **ingress**.
2. At start-up the app logs in to **Vault** with its own identity and reads **one** secret, the AI gateway key, into memory.
3. The app has **no internet**. Its only way out is the **egress proxy**, which allows just the AI gateway.
4. Vault and the proxy **log** every secret read and every connection attempt.
5. **GitHub Actions** (or the customer's pipeline) rebuilds the environment and runs 22 checks after every change.

## 4. Common changes and how to make them safely

| Change | Where | Then |
|---|---|---|
| New app release | `APP_COMMIT` in `scripts/fetch_app.sh` | Rebuild app, run verification |
| Allow a new outbound host | `customer-env/egress-proxy/allowlist.txt` (InfoSec ticket) | Rebuild proxy, run verification, add a check if it matters |
| Give the app another secret | Add the path to `invoicematch-app.hcl` and the value in `init.sh` (InfoSec) | Re-run `vault-init`, restart app, verify |
| Change approval limits | `AUTO_APPROVE_LIMIT`, `AP_MANAGER_LIMIT`, `CONTROLLER_LIMIT` in the compose file (Compliance sign-off) | Restart app |
| Add a control check | `scripts/verify_environment.sh` | Push; CI runs it |

## 5. Ownership (RACI)

| Activity | Platform | InfoSec | AP Manager | Vendor |
|---|---|---|---|---|
| Deploy, upgrade, roll back | **R/A** | C | I | C |
| Incident response | **R/A** | C | I | C (L3) |
| Vault policies and key rotation | C | **R/A** | I | I |
| Egress allow-list | C | **R/A** | I | C |
| Business rules and limits | C | I | **A** | R |
| Monthly verification review | **R** | C | I | I |

R = responsible, A = accountable, C = consulted, I = informed.

## 6. Handover plan

| Week | Session | Exit check |
|---|---|---|
| 1 | Architecture walkthrough; run the getting-started steps together | Customer engineer starts and verifies the environment alone |
| 2 | Runbook drills: rotate the key; upgrade and roll back | Both done without vendor help |
| 3 | Incident drills: Vault failure (5.2) and unexpected egress (5.4) | Resolved using only the runbook |
| 4 | Customer on-call takes the first line; vendor on standby | No vendor intervention needed for a week |

## 7. Handover checklist

- [ ] Platform team has run the getting-started steps and the verification
- [ ] InfoSec owns the Vault policies and has rotated the key once
- [ ] Alerts from [monitoring.md](monitoring.md) are set up in the customer's tools
- [ ] Both incident drills passed
- [ ] RACI agreed and contacts filled in
- [ ] Vendor access removed; L3 support agreement signed
