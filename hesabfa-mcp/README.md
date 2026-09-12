# Hesabfa Read-Only MCP Bridge

A private, read-only MCP bridge for Hesabfa accounting data.

## Security status

- No Hesabfa credentials are stored in this repository.
- No write/delete/save/payment endpoints are exposed.
- `MCP_ENABLED` defaults to `false` so `/mcp` stays disabled until proper user authentication is configured.
- Do not enable the public MCP endpoint without OAuth-based access control.

## Required Render environment variables

Set these directly in Render Environment; never commit them:

- `HESABFA_API_KEY`
- `HESABFA_LOGIN_TOKEN`
- `MCP_ENABLED=false` (keep false until OAuth is configured)

Optional:

- `HESABFA_API_BASE=https://api.hesabfa.com/v1`
- `PUBLIC_BASE_URL=https://hesabfa-readonly-mcp.onrender.com` must be an HTTPS
  origin only. A malformed value falls back to this service's default origin
  and is never reflected in public health checks, OAuth metadata or logs.
  Store a copied report request only in `HESABFA_USER_LOG_CURL`.

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
- user activity logs (`hesabfa_user_logs`)
- user log connection status (`hesabfa_user_logs_status`)

## User activity logs: separate website session

The public API at `https://api.hesabfa.com/v1` does **not** provide
`report/getUserLog` (POST returned 404 on 2026-09-11). The website uses
`POST https://core.hesabfa.com/api/report/getUserLog`, which returned 401
without a website session. The API key and API login token are not substitutes.

The deployed official app source was inspected on 2026-09-11:
`https://app.hesabfa.com/main.5ba1dd6eb4fd43949670.js`.
Its report service sends `start`, `end`, `userId`, `loadOptions`, the business
key header, XSRF header and session cookies. Its response is `{data,totalCount}`.
This is an internal website endpoint and may change without public API notice.

### One-time setup, and renewal when the session expires

1. In your own browser sign in to Hesabfa, select **پالیز**, then open
   **گزارش‌ها → لاگ کاربران**. Confirm that the report is visible.
2. Open Developer Tools → Network, refresh the report, and find `getUserLog`.
   Right-click that request → Copy → **Copy as cURL (bash)**.
3. Open the existing service's environment page:
   `https://dashboard.render.com/web/srv-da81t60ae00c73afvjg0/env`.
   Add **HESABFA_USER_LOG_CURL** and paste the copied request directly as its
   value. Save and deploy. Do not change existing API or OAuth secrets.
4. Refresh the Hesabfa Paliz app's tool list in ChatGPT. Check
   `hesabfa_user_logs_status`, then request an actual recent day using
   `hesabfa_user_logs`. A configured status alone does not verify the session.

The copied request contains private session credentials. Never paste it into
chat, source control, issues, screenshots, logs, or documents. Only put it in
the private environment value of this existing service. The server parses
the copy as data; it never runs cURL, shell commands, substitutions, or files.
Only cookie, XSRF and business key headers are accepted, and they can only be
sent to the fixed report endpoint. Redirects are rejected. Captured dates,
filters and payloads are ignored; each tool call supplies a fresh bounded query.

The website session may expire or be revoked on sign-out. When this happens,
renew it with the steps above. This is **not** a permanent API credential and
does not guarantee unattended daily reporting indefinitely. The integration
does not store a Hesabfa account password or automate sign-in. It does not
send or schedule emails.

### Query contract and verification

- Input dates are Gregorian `YYYY-MM-DD` or ISO timestamps. Date-only values
  and timestamps without offsets use Iran time (UTC+03:30, from 2023 onward).
  Earlier dates require an explicit offset. Date-only `end` includes the full day.
- At most 31 days per request; `take` is 1–100, default 50. Follow `nextSkip`
  until it is null. Preserve the source `dateTime` without guessing its offset.
- Credentials and the business cannot be overridden by tool arguments.
- 401/403, invalid JSON and inconsistent response structure are explicit
  errors, never successful empty reports. A zero count is returned only when
  the authenticated report provides a valid empty result.
- OAuth protection and the existing public API tools remain in place.
- Run `npm test` for credential isolation, calendar boundaries, pagination
  and error handling. Synthetic fixtures do not prove live authentication;
  a real configured report is the final acceptance check.

## Notes

The bridge throttles Hesabfa calls to approximately one request per 1.1 seconds based on historical API guidance. The Hesabfa API contract should be verified against the live account before higher-level reporting tools are added.
