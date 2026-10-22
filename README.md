# AI Lead Qualifier — n8n Automation

An importable n8n workflow for B2B lead qualification. It validates webhook input, asks OpenAI for a structured 0–100 score, returns JSON, appends qualified leads to Google Sheets, upserts HubSpot contacts by email, and sends Slack plus internal Gmail alerts when a score is at least 75.

> **Status:** Workflow and setup files are committed; live integrations still require your own credentials and account-specific configuration. No secrets are included, and no live end-to-end execution has been claimed.

## Workflow

```text
POST /ai-lead-qualifier
  → Normalize and validate input
  → Invalid? return HTTP 400
  → OpenAI lead scoring
  → Parse structured JSON
       ├─ Return JSON to caller
       ├─ Append row to Google Sheets
       ├─ Upsert HubSpot contact by email
       └─ If score >= 75: Slack message + internal email
```

## Included files

- `ai_lead_qualifier_workflow.json` — import into n8n.
- `sample_payload.json` — test lead payload.
- `leads_sheet_template.csv` — exact header row for the Google Sheets tab.
- `docker-compose.yml` — optional local n8n setup.
- `.gitignore` — excludes local secrets/configuration.

## Quick start

1. Start local n8n with Docker Compose (optional): `docker compose up -d`, then open http://localhost:5678.
2. In n8n, import `ai_lead_qualifier_workflow.json` and save the workflow.
3. Configure the **OpenAI** HTTP Request node with an n8n Header Auth credential: header `Authorization`, value `Bearer YOUR_REAL_OPENAI_API_KEY`. Remove the placeholder Authorization header from the node when using the credential. Keep `Content-Type: application/json`.
4. In **Save Lead to Google Sheets**, select an OAuth2 credential, replace `YOUR_GOOGLE_SPREADSHEET_ID`, and use a tab named `Leads` with the headers in `leads_sheet_template.csv`.
5. In **Upsert Contact in HubSpot**, select a Bearer Auth credential for a HubSpot private app with contact read/write permissions. Create custom contact properties with internal names `lead_score`, `lead_qualification`, `lead_need`, `lead_source`, and `ai_summary`.
6. Select credentials and the destination channel for **Notify Slack - High Priority**. Select Gmail OAuth and replace `YOUR_TEAM_EMAIL@example.com` in **Send Email - High Priority**.
7. Test the workflow using the Webhook node's **Test URL**, then activate the workflow and use its **Production URL** only after verifying the full flow.

## Test

With the webhook listening for a test event, send:

```bash
curl -X POST "YOUR_N8N_TEST_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  --data-binary @sample_payload.json
```

Valid requests require `name`, `email`, `company`, and `need`. The webhook returns HTTP 400 for invalid payloads. All valid leads are routed to Sheets and HubSpot; Slack/Gmail alerts fire only for scores `>= 75`.

## Security and production notes

- Do not put real API keys or OAuth tokens in workflow exports, source control, or screenshots. Store credentials in n8n Credentials.
- Add webhook authentication and rate limiting before exposing a production webhook.
- Configure retries/error workflows, retention policies, and monitoring.
- AI scores are triage suggestions; have a human review consequential decisions.
- An unconfigured downstream node may fail even if the webhook response was already returned. Test each integration individually and end-to-end.

## References

- [n8n Webhook node](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/)
- [n8n Google Sheets node](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.googlesheets/)
- [n8n Slack node](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.slack/)
- [n8n Gmail node](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.gmail/)
- [OpenAI Chat Completions API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
