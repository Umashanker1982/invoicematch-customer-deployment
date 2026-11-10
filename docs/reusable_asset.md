# Reusable asset proposal: the "Customer Environment Kit"

## The problem it solves

Every customer deployment of an AI agent repeats the same work: a private network, an egress allow-list for the AI gateway, secrets in the customer's vault, least-privilege identities, and proof for the security team that all of it holds. In this engagement that took most of the deployment effort, and **none of it is specific to InvoiceMatch**.

## The asset

A small, reusable kit extracted from this repository:

| Part | What it is | Reuse as-is? |
|---|---|---|
| **Egress allow-list proxy** ([`proxy.py`](../customer-env/egress-proxy/proxy.py)) | Standard-library CONNECT proxy: allow-list file, JSON decision log, unit tests | Yes: change only `allowlist.txt` |
| **Vault start-up wrapper** ([`vault_entrypoint.py`](../customer-env/app/vault_entrypoint.py)) | Logs in with AppRole, loads secrets into process memory, revokes its token, never prints keys, then starts any command | Yes: change the secret path and start command |
| **Vault bootstrap** ([`init.sh`](../customer-env/vault/init.sh), [policy](../customer-env/vault/policies/invoicematch-app.hcl)) | Audit device, one least-privilege policy, AppRole, credentials handover | Template: rename the app and paths |
| **Hardened compose template** ([`docker-compose.yml`](../customer-env/docker-compose.yml)) | Internal network, ingress, non-root, read-only, no capabilities | Template: swap the app image |
| **Control verification suite** ([`verify_environment.sh`](../scripts/verify_environment.sh) + CI workflow) | 22 PASS/FAIL checks that turn the security design into evidence | Mostly as-is: 4 app-specific checks to adapt |

## Why it is worth productizing

| Benefit | Detail |
|---|---|
| **Time saved** | The next deployment starts from a working, tested environment instead of a blank page: an estimated 3–5 days of FDE time per engagement |
| **Faster security approval** | The customer's security team gets the verification output as evidence on day one |
| **Consistency** | Every deployment has the same baseline controls; drift is caught by the same checks |
| **Low risk** | Standard library only (no third-party code on the network boundary); small enough to review in an hour |

## Who else can use it

Any agent that calls an AI gateway and needs a secret: the next InvoiceMatch customer, the support-ticket triage agent, the logistics dispatch agent from earlier modules (for example the [SwiftParcel multi-agent system](https://github.com/Umashanker1982/logistics-support-multi-agent)).

## Plan

| Step | Work | Effort |
|---|---|---|
| 1 | Move the five parts into a separate `customer-environment-kit` repository with a parameter file (app name, image, secret paths, allowed hosts) | 2 days |
| 2 | Add variants for AWS Secrets Manager and cloud IAM auth alongside Vault | 3 days |
| 3 | Publish the verification suite as a reusable CI workflow | 1 day |
| 4 | Pilot it on the next customer deployment; record the time saved | Next engagement |

**Owner:** FDE platform team · **Success measure:** the next deployment passes the same 22 checks in its first week.
