# Hesabfa Read-Only MCP Bridge

A private, read-only MCP bridge for Hesabfa accounting data.

## Security status

- No Hesabfa credentials are stored in this repository.
- No write/delete/save/payment endpoints are exposed.
- `MCP_ENABLED` defaults to `false` so `/mcp` stays disabled until proper user authentication is configured.
- Do not enable the public MCP endpoint without OAuth-based access control.

## Required Railway variables

Set these directly in Railway Variables / Secrets; never commit them:

- `HESABFA_API_KEY`
- `HESABFA_LOGIN_TOKEN`
- `MCP_ENABLED=false` (keep false until OAuth is configured)

Optional:

- `HESABFA_API_BASE=https://api.hesabfa.com/v1`

## Health endpoint

`GET /health` returns only bridge status and whether credentials are configured; it never returns credential values.

## Read-only tools

- business info
- fiscal year
- warehouses
- banks
- projects
- salespeople
- currency
- get item by code or barcode
- get warehouse stock quantity
- get invoice by number
- get contact by code
- list items
- list invoices
- list contacts

## Notes

The bridge throttles Hesabfa calls to approximately one request per 1.1 seconds based on historical API guidance. The Hesabfa API contract should be verified against the live account before higher-level reporting tools are added.
