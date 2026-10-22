#!/usr/bin/env python3
"""Offline structural checks for the n8n workflow; no external dependencies."""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / "ai_lead_qualifier_workflow.json"
SHEET_TEMPLATE_PATH = ROOT / "leads_sheet_template.csv"

errors: list[str] = []

def check(condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)

try:
    workflow = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
except Exception as exc:
    print(f"FAIL: workflow JSON could not be parsed: {exc}", file=sys.stderr)
    raise SystemExit(1)

nodes = workflow.get("nodes", [])
connections = workflow.get("connections", {})
by_name = {node.get("name"): node for node in nodes}
check(bool(nodes), "workflow must contain nodes")
check(len(by_name) == len(nodes), "node names must be unique")
check(len({node.get("id") for node in nodes}) == len(nodes), "node IDs must be unique")

for source, ports in connections.items():
    check(source in by_name, f"connection source does not exist: {source}")
    for output_name, output_groups in ports.items():
        if not isinstance(output_groups, list):
            errors.append(f"{source}.{output_name} must be a list")
            continue
        for group in output_groups:
            if not isinstance(group, list):
                errors.append(f"{source}.{output_name} contains a malformed connection group")
                continue
            for edge in group:
                check(edge.get("node") in by_name, f"connection target does not exist: {edge.get('node')}")
                check(edge.get("type") == "main", f"unexpected connection type from {source}: {edge.get('type')}")

def node(name: str) -> dict:
    found = by_name.get(name)
    check(found is not None, f"required node missing: {name}")
    return found or {}

def targets(source: str, output_index: int = 0) -> list[str]:
    try:
        return [edge["node"] for edge in connections[source]["main"][output_index]]
    except (KeyError, IndexError, TypeError):
        return []

webhook = node("Lead Intake Webhook")
check(webhook.get("parameters", {}).get("authentication") == "headerAuth",
      "webhook must require Header Auth")
normalize = node("Normalize and Validate Lead")
normalize_js = normalize.get("parameters", {}).get("jsCode", "")
check(all(field in normalize_js for field in ("name", "email", "company", "need")),
      "validation must require name, email, company, and need")
check("isValid" in normalize_js and "validationError" in normalize_js,
      "validation must expose isValid and validationError")

openai = node("Score Lead with OpenAI")
openai_params = openai.get("parameters", {})
check(openai_params.get("authentication") == "genericCredentialType",
      "OpenAI request must use an n8n credential, not an inline key")
check(openai_params.get("genericAuthType") == "httpHeaderAuth",
      "OpenAI request must use HTTP Header Auth credential")
header_rows = openai_params.get("headerParameters", {}).get("parameters", [])
check(not any(h.get("name", "").lower() == "authorization" for h in header_rows),
      "OpenAI Authorization must not be hard-coded in the workflow")
body = openai_params.get("jsonBody", "")
check("json_schema" in body and "strict: true" in body,
      "OpenAI request should use strict JSON-schema output")
check("YOUR_OPENAI_API_KEY" not in json.dumps(workflow),
      "workflow must not contain the old inline OpenAI key placeholder")

parse = node("Parse Qualification Result")
parse_js = parse.get("parameters", {}).get("jsCode", "")
for term in ("$('Normalize and Validate Lead').first().json", "need_clarity_score",
             "role_fit_score", "buying_intent_score", "budget_timing_score",
             "const score =", "score >= 75 ? 'high'"):
    check(term in parse_js, f"parser/scoring node missing expected logic: {term}")
check("$node[" not in parse_js, "parser should use documented $('Node').first().json previous-node syntax")

sheets = node("Save Lead to Google Sheets")
sheet_mapping = sheets.get("parameters", {}).get("columns", {}).get("value", {})
check(all(k in sheet_mapping for k in ("Lead Score", "Need Clarity Score", "Role Fit Score",
                                         "Buying Intent Score", "Budget Timing Score")),
      "Google Sheets mapping must include total and component scores")
try:
    with SHEET_TEMPLATE_PATH.open(newline="", encoding="utf-8") as handle:
        csv_headers = next(csv.reader(handle))
    check(set(csv_headers) == set(sheet_mapping.keys()),
          "Google Sheets mapping keys must match leads_sheet_template.csv headers")
except Exception as exc:
    errors.append(f"cannot read Google Sheets header template: {exc}")

hubspot = node("Upsert Contact in HubSpot")
check("/crm/v3/objects/contacts/batch/upsert" in hubspot.get("parameters", {}).get("url", ""),
      "HubSpot should use the contact batch upsert endpoint")
check("idProperty: 'email'" in hubspot.get("parameters", {}).get("jsonBody", ""),
      "HubSpot upsert must identify contacts by email")
gmail_params = node("Send Email - High Priority").get("parameters", {})
check(bool(gmail_params.get("sendTo")), "Gmail sendTo must be at the top level of node parameters")
check("sendTo" not in gmail_params.get("options", {}),
      "Gmail sendTo must not be nested in options")
check("YOUR_TEAM_EMAIL@example.com" in gmail_params.get("sendTo", ""),
      "Gmail recipient should remain an obvious unconfigured placeholder")

# Flow order / response safety: no 200 response is wired before core integrations.
check(targets("Lead Intake Webhook") == ["Normalize and Validate Lead"],
      "webhook must first normalize input")
check(targets("Normalize and Validate Lead") == ["Is Lead Valid?"],
      "validation node must feed the validation IF")
check(targets("Is Lead Valid?", 0) == ["Score Lead with OpenAI"],
      "valid input must go to OpenAI")
check(targets("Is Lead Valid?", 1) == ["Return Validation Error"],
      "invalid input must return the validation error")
check(targets("Score Lead with OpenAI") == ["Parse Qualification Result"],
      "OpenAI response must be parsed")
check(targets("Parse Qualification Result") == ["Save Lead to Google Sheets"],
      "score result must be saved to Sheets before further steps")
check(targets("Save Lead to Google Sheets") == ["Upsert Contact in HubSpot"],
      "HubSpot must run after Sheets")
check(targets("Upsert Contact in HubSpot") == ["Score at Least 75?"],
      "priority condition must run after required persistence")
check(targets("Score at Least 75?", 0) == ["Notify Slack - High Priority"],
      "high-priority branch must go to Slack")
check(targets("Score at Least 75?", 1) == ["Return Qualification Result"],
      "lower-priority branch must respond without notifications")
check(targets("Notify Slack - High Priority") == ["Send Email - High Priority"],
      "high-priority branch must send email after Slack")
check(targets("Send Email - High Priority") == ["Return Qualification Result"],
      "high-priority success response must wait for notifications")
response_expr = node("Return Qualification Result").get("parameters", {}).get("responseBody", "")
check("Parse Qualification Result" in response_expr and "googleSheets: 'succeeded'" in response_expr,
      "success response should include lead result and be downstream of persistence")
check(workflow.get("active") is False, "workflow should import inactive until credentials are configured")

serialized = json.dumps(workflow)
check(not re.search(r"\bsk-[A-Za-z0-9]{20,}\b", serialized), "possible OpenAI secret detected")
check(not re.search(r"Bearer\s+[A-Za-z0-9._-]{30,}", serialized), "possible hard-coded bearer token detected")

if errors:
    print("Workflow validation FAILED:")
    for error in errors:
        print(f" - {error}")
    raise SystemExit(1)

print(f"Workflow validation passed: {len(nodes)} nodes, {sum(len(g) for p in connections.values() for groups in p.values() for g in groups)} connection groups/edges inspected.")
