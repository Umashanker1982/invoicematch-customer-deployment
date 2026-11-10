#!/bin/sh
# One-time Vault setup for the simulated customer environment.
# In production the customer's security team does these steps through their own
# Vault change process; here a short-lived init container does them at start-up.
set -eu

until vault status >/dev/null 2>&1; do sleep 1; done

# 1. Audit device: every secret read is logged (who, which path, when; values are hashed).
vault audit list 2>/dev/null | grep -q "^file/" || vault audit enable file file_path=/vault/logs/audit.log

# 2. The application's policy (read one path only) and its machine identity (AppRole).
vault policy write invoicematch-app /init/policies/invoicematch-app.hcl
vault auth enable approle >/dev/null 2>&1 || true
vault write auth/approle/role/invoicematch-app \
    token_policies=invoicematch-app token_ttl=15m token_max_ttl=1h \
    secret_id_ttl=24h secret_id_num_uses=0 >/dev/null

# 3. The secrets. The AI gateway key comes from the operator (never from the repository).
#    Without one, a clearly fake placeholder is stored so the environment can still be verified.
KEY="${SEED_SHAREDLLM_KEY:-}"
[ -n "$KEY" ] || KEY="sk-sharedllm-placeholder-not-a-real-key-0000"
vault kv put secret/invoicematch/llm SHAREDLLM_KEY="$KEY" >/dev/null
# Another team's secret in the same Vault: used to prove the app cannot read it.
vault kv put secret/finance/erp ERP_PASSWORD="belongs-to-the-erp-team" >/dev/null

# 4. Hand the app its AppRole credentials through a private volume, readable only by the app user.
vault read -field=role_id auth/approle/role/invoicematch-app/role-id > /creds/role_id
vault write -f -field=secret_id auth/approle/role/invoicematch-app/secret-id > /creds/secret_id
chown 10001:10001 /creds/role_id /creds/secret_id
chmod 0400 /creds/role_id /creds/secret_id
echo '{"event": "vault_init_done", "policy": "invoicematch-app", "secret_path": "secret/data/invoicematch/llm"}'
