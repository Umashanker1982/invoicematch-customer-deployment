# Least privilege for the InvoiceMatch application:
# read one secret, nothing else. No list, no write, no other paths.
path "secret/data/invoicematch/llm" {
  capabilities = ["read"]
}
