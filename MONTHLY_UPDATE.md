# Monthly evidence update

The `Monthly evidence update` GitHub Actions workflow runs on the 28th day of
each month and screens PubMed records published during the previous calendar
month. It uses `gpt-5.6-sol`, preserves candidate and exclusion audit records,
retrieves PMC full text when required, updates only Good/poolable conventional
studies, keeps Mendelian-randomization evidence separate, and regenerates the
affected workbook and paper plots. The same regenerated, disease-specific PDFs
power the Summary page, including the combined and dietary forest plots,
Egger's-test-versus-heterogeneity plot, and effect-size-versus-heterogeneity
plot, so the public summary stays synchronized with changed analyses.

When an included analysis changes, the workflow also refreshes the saved-study
cancer-subcategory layer. It EFetches PubMed metadata only for newly included
PMIDs, uses `gpt-5.6-terra` for newly added or context-changed abstracts, uses
`gpt-5.6-luna` only for eligible PMCID full-text fallbacks, and rebuilds the
subcategory forest, funnel, Baujat, and Summary plots. Current source hashes are
checkpointed, so unchanged articles are not sent to either model again unless
an operator deliberately invokes the enrichment script with `--force`.
The action validates and commits the refreshed subtype source ledger,
annotations, result JSON, and generated plots together, so a newly classified
subcategory cannot be published without its corresponding analysis artifacts.

Terra input is costed at **$2 per million input tokens**. The append-only
annotation ledger stores the exact input token count and calculated Terra input
cost for each completed call; `Plot/subcategories/build_manifest.json` reports
the current-source totals used by the generated outputs.

Each run writes a permanent dated directory under `data/monthly_reports/`.
That directory contains `summary.txt`, every unsaved candidate PMID in
`newCandidatePMIDs.txt`, every first-/second-/full-text exclusion with its
one-sentence reason in `newStudyExclusions.txt`, the final new-study report,
the separate MR report, and `cost.txt`. Machine-readable screening packets are
retained under the matching date range in `data/monthly_updates/`.

## Required GitHub Secrets

Add these under **Repository Settings → Secrets and variables → Actions**:

- `NCBI_API_KEY`
- `NCBI_EMAIL`
- `CORNELL_API_KEY`
- `CORNELL_API_BASE_URL`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM`
- `SMTP_USE_SSL` (`true` or `false`)
- `SMTP_USE_TLS` (`true` or `false`)

Do not commit `mykey.env`, an NCBI key, a Cornell key, or an SMTP password. The
workflow treats a missing or rejected NCBI key as a failure instead of silently
using the public endpoint.

Failure alerts are sent to `margauxdelporte@gmail.com` and
`shiyushu2006@gmail.com`. The message includes the GitHub Actions run link and
the end of the diagnostic log.

## Scheduling requirement

GitHub runs scheduled workflows only when the workflow file exists on the
repository's default branch. The repository default is currently `main`, while
the evidence updates target `YSClose2Submission`. Therefore this workflow file
must also be merged or copied to `main`; it deliberately checks out, commits,
and pushes the resulting evidence changes to `YSClose2Submission`.

Use **Actions → Monthly evidence update → Run workflow** for a manual test after
the secrets are configured. The workflow has write permission for repository
contents; branch protection must allow `github-actions[bot]` to push to
`YSClose2Submission`.
