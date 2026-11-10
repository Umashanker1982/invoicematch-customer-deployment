#!/usr/bin/env bash
# Fetch the InvoiceMatch application at the exact version that is being deployed.
# Pinning a commit means the customer deploys a reviewed, tested release, not "whatever is on main".
set -euo pipefail
APP_REPO="${APP_REPO:-https://github.com/Umashanker1982/invoicematch.git}"
APP_COMMIT="${APP_COMMIT:-743d96e}"
cd "$(dirname "$0")/.."
rm -rf app-src
git clone --quiet "$APP_REPO" app-src
git -C app-src checkout --quiet "$APP_COMMIT"
echo "Fetched InvoiceMatch at commit $(git -C app-src rev-parse --short HEAD)"
