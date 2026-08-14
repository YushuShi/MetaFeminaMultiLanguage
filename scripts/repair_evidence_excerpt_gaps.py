#!/usr/bin/env python3
"""Quarantine unsupported cache rows and repair source-backed excerpts.

This is intentionally a context-level curation, not a PMID-global rewrite.
The 2026-08 audit found that nearly every blank excerpt came from a study row
placed under the wrong exposure or endpoint.  Copying text into those rows
would make the UI nonblank while preserving scientifically invalid evidence.
Instead, this script archives and removes those exact rows from every cache
variant in the affected context.  The one recoverable row is repaired from its
official full text.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CACHE_ROOT = ROOT / "Cached_results"
QUARANTINE_PATH = ROOT / "data" / "evidence_review_quarantine.json"


# (exposure directory, disease cache prefix, PMID, reason code, audit note)
QUARANTINE_TARGETS = (
    ("bcaas", "breast_cancer", "38652345", "wrong_outcome", "Valine estimate concerns breast-cancer recurrence, not incidence."),
    ("bcaas", "breast_cancer", "41189935", "wrong_outcome", "BCAA estimate concerns radiotherapy skin toxicity, not cancer incidence."),
    ("black_cohosh", "breast_cancer", "17416109", "postdiagnosis", "Endpoint is recurrence-free survival after diagnosis."),
    ("cannabidiol", "breast_cancer", "40751295", "wrong_outcome", "Displayed value is a pain-response proportion in an AIMSS trial."),
    ("coenzyme_q10", "breast_cancer", "29781707", "wrong_exposure", "Source estimate is for whole-grain intake."),
    ("coenzyme_q10", "breast_cancer", "32369545", "wrong_exposure", "Source estimate is for dietary-fiber intake."),
    ("coenzyme_q10", "breast_cancer", "34558660", "wrong_exposure", "Source estimate is for fish-oil supplementation."),
    ("copper", "uterine_cancer", "1800424", "wrong_outcome", "Source concerns copper IUD use and cervical cancer."),
    ("dehydroepiandrosterone", "breast_cancer", "10070957", "wrong_exposure", "Source estimate is for a CYP17 genotype, not DHEA exposure."),
    ("dehydroepiandrosterone", "breast_cancer", "24669750", "postdiagnosis", "Estimate is a postdiagnosis tumor-biomarker change."),
    ("dehydroepiandrosterone", "breast_cancer", "2971432", "wrong_outcome", "Source is breast-cyst biochemistry and does not report the stored risk ratio."),
    ("dehydroepiandrosterone", "breast_cancer", "30892712", "wrong_outcome", "Estimate concerns chemotherapy-related cognitive impairment."),
    ("dehydroepiandrosterone", "breast_cancer", "31694190", "wrong_exposure", "Source estimate is flavonoid intake versus circulating DHEA."),
    ("dehydroepiandrosterone", "breast_cancer", "41482078", "nonhuman", "Source is an in-vitro steroidal compound experiment."),
    ("fermented_foods", "breast_cancer", "29574860", "wrong_exposure", "Source estimate is a composite estrogen-related dietary pattern."),
    ("fish_oil", "breast_cancer", "18756015", "wrong_exposure", "Source estimate is cod-liver-oil/vitamin-D exposure."),
    ("fish_oil", "breast_cancer", "21178081", "postdiagnosis", "Endpoint is additional events after breast-cancer diagnosis."),
    ("fish_oil", "breast_cancer", "22894640", "wrong_outcome", "Endpoint is paclitaxel-induced peripheral neuropathy."),
    ("fish_oil", "breast_cancer", "26137879", "wrong_outcome", "Displayed ratio is a breast-tissue fatty-acid biomarker difference."),
    ("flaxseed", "breast_cancer", "24669750", "wrong_metric", "Stored RR is a postdiagnosis biomarker regression coefficient."),
    ("flaxseed", "breast_cancer", "30375890", "wrong_outcome", "Stored ratio concerns circulating sex hormones, not cancer incidence."),
    ("folic_acid", "breast_cancer", "40890881", "wrong_exposure", "Source estimate is for folate-receptor-alpha protein, not folic-acid intake."),
    ("glutamine", "breast_cancer", "26315396", "wrong_outcome", "Endpoint is overall survival from an EMT metabolite signature."),
    ("grape", "breast_cancer", "2766288", "wrong_exposure", "Source estimate is alcohol/wine consumption, not grape exposure."),
    ("isoleucine", "breast_cancer", "41189935", "wrong_outcome", "Endpoint is radiotherapy skin toxicity."),
    ("lutein", "breast_cancer", "41830449", "nonhuman", "Source is an in-vitro nanoparticle study and reports no human incidence estimate."),
    ("lycopene", "uterine_cancer", "33350944", "wrong_outcome", "Endpoint is benign uterine leiomyomata, not uterine cancer."),
    ("manganese", "breast_cancer", "30760301", "wrong_outcome", "Endpoint is mammographic density for a mixed air-toxic index."),
    ("mediterranean_diet", "breast_cancer", "41960842", "secondary_research", "Systematic-review estimate is excluded from the primary-study cache."),
    ("omega-3_fatty_acids", "breast_cancer", "22894640", "wrong_outcome", "Endpoint is paclitaxel-induced peripheral neuropathy."),
    ("omega-3_fatty_acids", "breast_cancer", "26137879", "wrong_outcome", "Endpoint is a breast-tissue fatty-acid biomarker."),
    ("omega-3_fatty_acids", "breast_cancer", "30415629", "wrong_exposure", "Stored breast-cancer HR is from the vitamin-D trial comparison."),
    ("omega-6_fatty_acids", "breast_cancer", "9508101", "wrong_exposure", "Estimate is for a long-chain omega-3:total omega-6 ratio, not isolated omega-6."),
    ("omega-6_fatty_acids", "breast_cancer", "33543354", "wrong_outcome", "Stored coefficient concerns a lifestyle biomarker, not cancer incidence."),
    ("vitamin_e", "breast_cancer", "11319174", "wrong_exposure", "Source estimate is for serum enterolactone."),
    ("vitamin_e", "breast_cancer", "11713032", "wrong_exposure", "Source estimate is for total fat intake."),
    ("vitamin_e", "breast_cancer", "15329916", "wrong_outcome", "Source concerns chemotherapy toxicity and does not report the stored RR."),
    ("vitamin_e", "breast_cancer", "18056435", "wrong_exposure", "Source estimate is for cysteinylglycine in a vitamin-E stratum."),
    ("vitamin_e", "breast_cancer", "20929592", "postdiagnosis", "Endpoint is recurrence after adjuvant tocotrienol treatment."),
    ("vitamin_e", "breast_cancer", "8681441", "postdiagnosis", "Endpoint is tumor progression among patients with cancer."),
    ("vitamin_e", "breast_cancer", "9498489", "wrong_metric", "8.6% (-0.4% to 17.5%) is population-attributable risk, not an odds ratio."),
    ("vitamin_e", "breast_cancer", "19358284", "wrong_exposure", "Stored estimate is for total vegetable intake."),
    ("vitamin_e", "breast_cancer", "19089916", "wrong_exposure", "Stored ratio is the reciprocal of a telomere-length estimate in a vitamin-E subgroup."),
    ("zinc", "breast_cancer", "37299574", "postdiagnosis", "Endpoint is all-cause mortality after cancer diagnosis."),
    ("zinc", "uterine_cancer", "22952183", "wrong_exposure", "Source estimate is for heme-iron intake."),
    ("zinc", "uterine_cancer", "31599404", "wrong_exposure", "Source estimate is for a ZNRD1-AS1 genetic variant, not zinc exposure."),
)


PHOSPHORUS_REPAIR = {
    "exposure": "phosphorus",
    "disease": "breast_cancer",
    "pmid": "37686766",
    "sample_size": (
        "each of the 74 breast cancer cases ... were matched with four controls "
        "randomly selected from the cohort, totaling 296 controls"
    ),
    "source": "https://pmc.ncbi.nlm.nih.gov/articles/PMC10490459/",
}


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}-",
            suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, indent=4, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def _cache_variants(exposure: str, disease: str) -> list[Path]:
    directory = CACHE_ROOT / exposure
    return sorted(directory.glob(f"{disease}_incidence_*.json")) if directory.is_dir() else []


def main() -> int:
    existing_archive = {}
    if QUARANTINE_PATH.is_file():
        payload = json.loads(QUARANTINE_PATH.read_text(encoding="utf-8"))
        existing_archive = {
            (item["cache"], item["pmid"]): item
            for item in payload.get("records", [])
        }

    archive = dict(existing_archive)
    changed_files: set[Path] = set()
    removed = 0

    for exposure, disease, pmid, reason_code, note in QUARANTINE_TARGETS:
        for cache_path in _cache_variants(exposure, disease):
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            studies = payload.get("studies")
            if not isinstance(studies, list):
                continue
            retained = []
            for study in studies:
                if str(study.get("PMID") or "") != pmid:
                    retained.append(study)
                    continue
                key = (str(cache_path.relative_to(ROOT)), pmid)
                archive[key] = {
                    "cache": key[0],
                    "exposure": exposure,
                    "disease": disease,
                    "pmid": pmid,
                    "reason_code": reason_code,
                    "note": note,
                    "study": study,
                }
                removed += 1
            if len(retained) != len(studies):
                payload["studies"] = retained
                _write_json_atomic(cache_path, payload)
                changed_files.add(cache_path)

    repaired = 0
    for cache_path in _cache_variants(
        PHOSPHORUS_REPAIR["exposure"], PHOSPHORUS_REPAIR["disease"]
    ):
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        dirty = False
        for study in payload.get("studies", []):
            if str(study.get("PMID") or "") != PHOSPHORUS_REPAIR["pmid"]:
                continue
            support = study.setdefault("extraction_supporting_text", {})
            if not str(support.get("sample_size") or "").strip():
                support["sample_size"] = PHOSPHORUS_REPAIR["sample_size"]
                study["evidence_excerpt_source"] = PHOSPHORUS_REPAIR["source"]
                dirty = True
                repaired += 1
        if dirty:
            _write_json_atomic(cache_path, payload)
            changed_files.add(cache_path)

    quarantine_payload = {
        "schema_version": 1,
        "audit_date": "2026-08-14",
        "policy": (
            "Rows are removed from served caches only when the primary source "
            "does not support the selected exposure, incidence endpoint, or ratio metric."
        ),
        "records": [archive[key] for key in sorted(archive)],
    }
    _write_json_atomic(QUARANTINE_PATH, quarantine_payload)

    print(
        f"Removed {removed} cache records, repaired {repaired} records, "
        f"changed {len(changed_files)} cache files; archived {len(archive)} records."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
