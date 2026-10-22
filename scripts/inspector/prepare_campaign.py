#!/usr/bin/env python3
"""Prepare private, unsent Inspector invitation batches from verified research."""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import subprocess
from pathlib import Path

SAMPLE = "https://github.com/founder-sweep/production-readiness-inspector/blob/main/docs/inspector/marketing/AGENCY_QUICKSTART.md"
PRODUCT = "https://inspector.contentsweep.ai/inspector#workspace"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
    runtime = root / ".mcp-products/inspector/marketing"
    destination = runtime / "campaign.private.json"
    if destination.exists():
        raise RuntimeError("Campaign already exists; preserve manual updates rather than regenerate it")
    curated = json.loads((runtime / "curation.private.json").read_text())
    assert len(curated) == 40 and len({row[0] for row in curated}) == 40
    records = []
    for index, (identifier, opening, fit, contact) in enumerate(curated):
        research = json.loads((runtime / "research" / (identifier[1:] + ".private.json")).read_text())
        service = research.get("service", {})
        contact_page = research.get("contact", {})
        if research.get("error") and identifier not in {"I06", "I30"}:
            raise ValueError("Unverified primary source: " + identifier)
        # QTEC and SoftFormance were read via web.open when direct HTTP was blocked.
        fallback = {"I06": "FastAPI API development, integration, documentation, monitoring and ongoing support; info@qtecsolution.com appears in the official service-page footer.",
                    "I30": "The official homepage describes Python/Django client platforms and shows a Contact Us inquiry form."}
        if identifier in fallback:
            research["web_verified_source"] = {"url": research["url_requested"], "checked_on": "2026-10-22", "method": "web.open", "paraphrase": fallback[identifier], "direct_http_blocked": True}
            source = research["url_requested"]
        else:
            source = service["url"]
        observed = service.get("text", "") + "\n" + contact_page.get("text", "")
        emails = {value.lower() for value in service.get("emails", []) + contact_page.get("emails", [])}
        if "@" in contact and contact.lower() not in emails and identifier != "I06":
            raise ValueError("Contact email not observed on official page: " + identifier)
        if "@" not in contact and identifier not in {"I22", "I27", "I30"}:
            assert contact in {contact_page.get("url"), *service.get("contact_links", [])}
        framework = "FastAPI stated" if "fastapi" in observed.lower() or identifier == "I06" else "Python stated; confirm FastAPI fit"
        if framework.startswith("Python"):
            opening += " If your current client work includes a FastAPI service, this may be relevant."
        batch = index // 10 + 1
        planned = dt.date(2026, 10, 26) + dt.timedelta(days=(batch - 1) * 7)
        body = (f"Hello {research['company']} team,\n\n{opening}\n\n"
                "I'm inviting a few Python agencies to try Inspector: a free local FastAPI, Docker and Actions checker, with optional private release comparisons and HTML handoffs. "
                "It runs on Python 3.12/Linux, and application source stays local.\n\n"
                f"Synthetic example and setup: {SAMPLE}\n\n"
                "Three hosted reports are free; continued hosted use is $19 USD for 100 reports, with no subscription. "
                "Do you have an upcoming client release where your team could try the comparison?\n\n"
                "Content Sweep LLC\nfounder@contentsweep.ai\n"
                "If this isn't relevant, let me know and I won't follow up.\n")
        followup = (f"Hello {research['company']} team,\n\nOne follow-up on the Inspector trial invitation. "
                    "Would a local FastAPI release check and an exported change report be useful on an upcoming client release? "
                    "There are three free hosted reports, then $19 USD for 100. If timing or fit is wrong, I'll leave it here.\n\n"
                    "Content Sweep LLC\nfounder@contentsweep.ai\n")
        if "@" in contact:
            contact_source = contact_page.get("url", source) if contact.lower() in {value.lower() for value in contact_page.get("emails", [])} else source
        else:
            contact_source = contact
        record = {"id": identifier, "batch": batch, "company": research["company"], "planned_invitation_date": planned.isoformat(),
                  "service_url": source, "service_note": opening, "fit_reason": fit, "framework_fit": framework,
                  "contact": contact, "contact_method": "email" if "@" in contact else "public inquiry form",
                  "contact_source_url": contact_source,
                  "source_checked_on": "2026-10-22", "size_note": "Firm size not independently verified; prioritize relevant delivery teams.",
                  "subject": "A static change report for your next Python client release", "body": body, "followup": followup,
                  "status": "Draft", "sent_date": None, "interested": "", "first_report_date": None, "second_report_date": None,
                  "paid_date": None, "refund_usd": 0, "support_minutes": 0, "objection": "", "followup_sent_date": None}
        records.append(record)
        path = runtime / "research" / (identifier[1:] + ".private.json")
        path.write_text(json.dumps(research, indent=2))
        path.chmod(0o600)
    args.output.mkdir(parents=True, exist_ok=True)
    campaign = {"start": "2026-10-22", "end": "2026-11-20", "budget_usd": 0, "goal_independent_buyers": 5,
                "price_usd": 19, "offer_reports": 100, "owner_minutes_per_week": 60, "records": records,
                "messages_sent_by_agent": 0, "manual_tracking_authority": "Inspector-campaign.xlsx",
                "review_dates": ["2026-10-29", "2026-11-05", "2026-11-12", "2026-11-19", "2026-11-20"]}
    destination.write_text(json.dumps(campaign, indent=2))
    destination.chmod(0o600)
    for batch in range(1, 5):
        lines = [f"Inspector invitation batch {batch} — review and send manually", "", "Status: ALL DRAFTS UNSENT. Planned dates are not invitation dates.",
                 "Review the firm's current fit and business-contact source before sending. Do not pose as a prospective client in an inquiry form.",
                 "Send at most one follow-up after seven days, and stop after a decline. Record actual dates and responses in Inspector-campaign.xlsx.", ""]
        for record in records:
            if record["batch"] != batch:
                continue
            lines += ["=" * 70, f"{record['id']} — {record['company']}", f"Planned: {record['planned_invitation_date']}",
                      f"Source: {record['service_url']}", f"Contact source: {record['contact_source_url']}", f"Why it might fit: {record['fit_reason']}",
                      f"Framework: {record['framework_fit']}", f"To / inquiry form: {record['contact']}", f"Subject: {record['subject']}", "", record["body"],
                      "ONE FOLLOW-UP — only if actually invited at least seven days ago and no decline:", "", record["followup"], ""]
        (args.output / f"Batch-{batch}-invitations.txt").write_text("\n".join(lines))
    lines = ["Inspector campaign — October 22 to November 20, 2026", "", "Goal: five independent agency buyers. $19/100 reports. $0 new spend. All 40 invitations are unsent drafts.",
             "", "Start with Batch-1-invitations.txt. Its proposed send date is October 26. Review and send personally; then enter actual dates in Inspector-campaign.xlsx.",
             "The workbook is the authoritative manual tracker. Keep one row per firm, and confirm company attribution voluntarily without asking for a workspace key.",
             "Do not rebuild or overwrite the workbook after entering results. Research JSON is the preparation snapshot, not live customer activity.",
             "", "Weekly hour: 15 minutes reviewing/sending invitations, 20 replying, 10 reviewing feedback, 15 checking results. Use asynchronous support.",
             "Batches 2–4 are proposed for November 2, 9, and 16. Reviews: October 29, November 5, 12, 19, and final November 20.",
             "After 20 sent invitations with fewer than 2 interested replies, revise targeting/opening copy before continuing.",
             "After 10 completed trials and no buying companies, interview 3 trial participants before expanding promotion or changing pricing.",
             "", "Positive reply: send the quickstart; ask for the first complete hosted report and then a second release comparison. Ask for feedback on setup and usefulness, not private source or keys.",
             "After a useful comparison: explain that continued hosted use is the existing $19/100 pack. Local scanning and local baselines remain free. Never imply a purchase is required to keep using the CLI.",
             "Trial interview: What did you use the comparison for? What was confusing? What, if anything, would make hosted history worth $19 compared with keeping local files?",
             "Request permission before publishing a customer's name, logo, quote, or project evidence. No customer case study exists yet.",
             "", f"Quickstart and sample: {SAMPLE}", f"Product: {PRODUCT}",
             "", "The three guides and synthetic screenshots are public. Prospect research, invitations, campaign tracking, and operational measurements stay private."]
    (args.output / "START-HERE.txt").write_text("\n".join(lines) + "\n")
    # A private, readable review index. It has no message-sending or tracking scripts.
    cards = []
    for record in records:
        cards.append("<article><h2>" + html.escape(f"Batch {record['batch']} · {record['company']}") + "</h2><p>" + html.escape(record["fit_reason"]) +
                     "</p><p>" + html.escape(record["contact"]) + "</p><a href='" + html.escape(record["service_url"], quote=True) + "'>Official service source</a><pre>" + html.escape(record["body"]) + "</pre></article>")
    page = "<!doctype html><meta charset='utf-8'><title>Inspector private invitation review</title><style>body{max-width:950px;margin:40px auto;font:17px/1.55 system-ui;padding:20px;color:#18303b;background:#f6f7f9}article{background:white;border:1px solid #d8dee4;padding:24px;margin:24px 0;border-radius:9px}pre{white-space:pre-wrap;font:15px/1.6 system-ui}a{color:#205c45}</style><h1>Inspector private invitation review</h1><p>40 researched firms. Four batches. All drafts remain unsent. Use the workbook for actual dates and responses.</p>" + "".join(cards)
    (args.output / "Invitation-review.html").write_text(page)
    print(json.dumps({"qualified_firms": len(records), "batches": 4, "drafts_prepared": len(records), "followup_drafts": len(records), "messages_sent": 0, "new_spend_usd": 0}))


if __name__ == "__main__":
    main()
