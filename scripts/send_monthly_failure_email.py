#!/usr/bin/env python3
"""Send a concise GitHub Actions failure alert for the monthly update."""

from __future__ import annotations

import argparse
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path


RECIPIENTS = ("margauxdelporte@gmail.com", "shiyushu2006@gmail.com")
MAX_LOG_CHARACTERS = 16000


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path)
    parser.add_argument("--workflow-url", default="Not available")
    parser.add_argument("--run-label", default="Monthly MetaFemina evidence update")
    args = parser.parse_args()

    smtp_host = os.getenv("SMTP_HOST")
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM") or smtp_username
    if not smtp_host or not smtp_from:
        raise RuntimeError("SMTP_HOST and SMTP_FROM (or SMTP_USERNAME) are required for failure alerts")
    try:
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
    except ValueError as exc:
        raise RuntimeError("SMTP_PORT must be an integer") from exc

    log_text = "No workflow log was available."
    if args.log and args.log.exists():
        log_text = args.log.read_text(encoding="utf-8", errors="replace")[-MAX_LOG_CHARACTERS:]

    message = EmailMessage()
    message["Subject"] = "MetaFemina monthly update failed"
    message["From"] = smtp_from
    message["To"] = ", ".join(RECIPIENTS)
    message.set_content(
        f"{args.run_label} failed and requires developer attention.\n\n"
        f"GitHub Actions run: {args.workflow_url}\n\n"
        "The final section of the workflow log follows. It should identify issues such as "
        "an invalid/expired NCBI or Cornell key, NCBI/PMC retrieval failure, screening failure, "
        "plot-generation error, or Git push problem.\n\n"
        "----- LOG TAIL -----\n"
        f"{log_text}\n"
    )

    use_ssl = os.getenv("SMTP_USE_SSL", "false").lower() == "true"
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    with smtp_class(smtp_host, smtp_port, timeout=30) as server:
        if use_tls and not use_ssl:
            server.starttls()
        if smtp_username and smtp_password:
            server.login(smtp_username, smtp_password)
        server.send_message(message)
    print(f"Failure alert sent to {', '.join(RECIPIENTS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
