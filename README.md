# AI Lead Qualifier — n8n Automation

An n8n workflow for qualifying inbound B2B leads, recording results, updating HubSpot, and notifying the team about high-priority leads.

> **Current status:** The workflow and static workflow checks are committed. Account-specific credentials and IDs must be configured in n8n. No live end-to-end execution has been verified in this repository, so complete the smoke test below before using it for real leads.

## Workflow

```text
POST /ai-lead-qualifier (Header Auth)
  → Normalize and validate input
  → Invalid? HTTP 400 JSON response
  → OpenAI JSON-schema scoring (four bounded components)
  → Code validates components and calculates total/category
  → Append complete lead + scoring breakdown to Google Sheets
  → Upsert HubSpot contact by email
  → Score >= 75? Slack notification → Gmail notification
  → Return HTTP 200 only after required steps succeed
```

For scores below 75, the workflow skips notifications and returns the result after Sheets and HubSpot succeed. If a required downstream node fails, n8n should mark the execution failed instead of returning the workflow's success response. Configure an error workflow/monitoring path for production.

## Files

- `ai_lead_qualifier_workflow.json` — importable workflow.
- `sample_payload.json` — sample request.
- `leads_sheet_template.csv` — required Google Sheets headers, including the score breakdown.
- `docker-compose.yml` — optional local n8n deployment.
- `scripts/validate_workflow.py` — offline structural and configuration checks.
- `.github/workflows/validate.yml` — run the validator on pushes and pull requests.

## Setup

### 1. Run n8n locally (optional)

Install Docker Desktop, then run from the repository directory:

```bash
docker compose up -d
```

Open http://localhost:5678 and complete the initial n8n owner setup. The Compose file uses a persistent named volume for the n8n data directory. For production, pin a specific tested n8n image version instead of relying on `latest`, set up TLS/reverse proxy and backups, and restrict access to the editor.

### 2. Import the workflow

In n8n, import `ai_lead_qualifier_workflow.json`. Keep the workflow inactive until all credentials and destination settings are configured.

### 3. Secure the webhook

The imported workflow requires Header Auth. Open **Lead Intake Webhook**, create/select a **Header Auth** credential and use a long, random secret with a header name such as `X-Lead-Qualifier-Token`. Your calling client must send the same header. Do not commit that secret or paste it into the workflow JSON. Add proxy/API-gateway rate limiting and request-size limits before making the endpoint public.

### 4. Configure OpenAI

Open **Score Lead with OpenAI** and select an n8n **HTTP Header Auth** credential:
- Header name: `Authorization`
- Header value: `Bearer YOUR_REAL_OPENAI_API_KEY`

Use a real key only in the n8n credential store. The workflow asks for structured JSON with four bounded scoring components. The Code node validates the component ranges and computes the total:
- Need clarity: 0–35
- Role fit: 0–25
- Buying intent: 0–25
- Budget/timing evidence: 0–15

Total score is the sum (0–100); category is derived in code as high (75–100), medium (45–74), or low (0–44). Model scores are subjective triage signals, not facts or an objective measure of a person's value.

### 5. Configure Google Sheets

In **Save Lead to Google Sheets**:
- Select your Google Sheets OAuth2 credential.
- Replace `YOUR_GOOGLE_SPREADSHEET_ID` with your spreadsheet ID.
- Create a worksheet/tab named `Leads`.
- Copy the exact header row from `leads_sheet_template.csv`.

The workflow appends one row per request. Duplicate detection/idempotency is not yet implemented, so retries from a client can create duplicate rows.

### 6. Configure HubSpot

In **Upsert Contact in HubSpot**, select a Bearer Auth credential for a HubSpot private app with contact read/write access. Create these custom contact properties with the listed internal names before testing:

- `lead_score`
- `lead_qualification`
- `lead_need`
- `lead_source`
- `ai_summary`

The request uses email as the upsert key. Confirm the private app scopes and custom property types match your HubSpot account.

### 7. Configure Slack and Gmail

- In **Notify Slack - High Priority**, select a Slack API credential and destination channel.
- In **Send Email - High Priority**, select Gmail OAuth2 and replace the top-level **To / sendTo** field with your internal team email address.

Both run only for scores at least 75. These integration destinations and credentials are account-specific and cannot be preconnected in a portable JSON export.

## Test before activation

1. Start a webhook **Test URL** listener in n8n.
2. Use the sample request below and include the configured authentication header.
3. Test invalid input (for example, omit `email`) and confirm HTTP 400.
4. Test a valid low/medium lead and confirm Sheets row, HubSpot contact, and response.
5. Test a high-priority lead and confirm Sheets, HubSpot, Slack, Gmail, and final response.
6. Disable or misconfigure a downstream integration in a test environment and confirm the execution is marked failed rather than returning the workflow's success response.
7. Only then activate the workflow and use the **Production URL**.

Example request:

```bash
curl -X POST "YOUR_N8N_TEST_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -H "X-Lead-Qualifier-Token: YOUR_TEST_WEBHOOK_TOKEN" \
  --data-binary @sample_payload.json
```

## Offline validation

Requires Python 3.11+ and no third-party packages:

```bash
python scripts/validate_workflow.py
```

This validates the JSON, connection targets, critical node configuration, sequential response paths, and Google Sheets column mapping. It does **not** emulate n8n or prove that credentials, node-version compatibility, external APIs, or account permissions work.

## Production hardening still recommended

- Add a stable idempotency key/deduplication store so retried webhooks do not create duplicate records or alerts.
- Configure retries with bounded backoff, error workflows, and a status store for each integration.
- Consider responding with HTTP 202 and a job ID if caller latency should not depend on the CRM and notification APIs.
- Define a labeled lead dataset and measure agreement between the AI's score and sales-reviewed outcomes.
- Apply data minimization, retention rules, restricted sharing, and human review for consequential decisions.
- Avoid treating free-text fields as instructions; the prompt explicitly treats them as untrusted input, but prompt injection and score variation still require evaluation.

## References

- [n8n Webhook node](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/)
- [n8n Code node](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.code/)
- [n8n Respond to Webhook node](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.respondtowebhook/)
- [n8n Google Sheets node](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.googlesheets/)
- [n8n Gmail node](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.gmail/)
- [OpenAI Chat Completions API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
- [HubSpot Contacts API](https://developers.hubspot.com/docs/api-reference/crm-contacts-v3/guide)
