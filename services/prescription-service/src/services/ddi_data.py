"""Bundled high-priority drug-drug interaction table.

The NLM/RxNav Drug Interaction API was discontinued 2024-01-02 (confirmed;
no official REST replacement). This module replaces it with a local check
against a curated subset of the ONC High-Priority DDI list — the same
source RxNav used for those alerts — expressed as drug-class pair rules so
free-text medication names match by ingredient.

Scope: high-priority pairs only; NOT a comprehensive interaction database.
Coverage gaps are a known limitation, prefer silence to false confidence.
"""

from __future__ import annotations

# (class_a terms, class_b terms, severity, description)
# Matching: any term appears as a substring of the normalized drug name.
INTERACTION_RULES: list[tuple[list[str], list[str], str, str]] = [
    (["warfarin"], ["ibuprofen", "naproxen", "ketorolac", "diclofenac", "indomethacin"],
     "major",
     "Warfarin + NSAID: increased risk of serious bleeding (antiplatelet effect, GI mucosal injury, INR perturbation)."),
    (["warfarin"], ["aspirin", "acetylsalicylic"],
     "major",
     "Warfarin + aspirin: additive anticoagulation; major bleeding risk increases substantially."),
    (["warfarin"], ["amiodarone"],
     "major",
     "Warfarin + amiodarone: CYP2C9 inhibition raises INR; major bleed risk. Warfarin dose reduction typically required."),
    (["warfarin"], ["ciprofloxacin", "levofloxacin", "moxifloxacin"],
     "major",
     "Warfarin + fluoroquinolone: INR elevation via CYP inhibition and gut-flora vitamin K changes."),
    (["warfarin"], ["erythromycin", "clarithromycin"],
     "major",
     "Warfarin + macrolide: CYP3A4/1A2 inhibition can sharply raise INR."),
    (["warfarin"], ["sulfamethoxazole", "trimethoprim", "co-trimoxazole", "bactrim", "septra"],
     "major",
     "Warfarin + TMP-SMX: strong CYP2C9 inhibition; marked INR elevation and bleeding risk."),
    (["methotrexate"], ["ibuprofen", "naproxen", "ketorolac", "diclofenac", "indomethacin"],
     "major",
     "Methotrexate + NSAID: reduced renal clearance of methotrexate; risk of severe myelosuppression and nephrotoxicity."),
    (["methotrexate"], ["sulfamethoxazole", "trimethoprim", "co-trimoxazole", "bactrim", "septra"],
     "major",
     "Methotrexate + TMP-SMX: additive antifolate effect; risk of pancytopenia."),
    (["fluoxetine", "sertraline", "paroxetine", "citalopram", "escitalopram", "fluvoxamine",
      "venlafaxine", "duloxetine"],
     ["phenelzine", "tranylcypromine", "isocarboxazid", "selegiline", "linezolid"],
     "contraindicated",
     "Serotonergic agent + MAOI: risk of life-threatening serotonin syndrome; combination contraindicated."),
    (["fluoxetine", "sertraline", "paroxetine", "citalopram", "escitalopram", "fluvoxamine"],
     ["sumatriptan", "rizatriptan", "zolmitriptan", "naratriptan", "eletriptan"],
     "moderate",
     "SSRI + triptan: additive serotonergic effect; monitor for serotonin syndrome."),
    (["digoxin"], ["amiodarone"],
     "major",
     "Digoxin + amiodarone: P-gp inhibition raises digoxin levels ~70%; digoxin dose reduction required."),
    (["digoxin"], ["verapamil", "diltiazem"],
     "major",
     "Digoxin + calcium-channel blocker: elevated digoxin levels plus additive AV-nodal depression."),
    (["digoxin"], ["clarithromycin", "erythromycin"],
     "major",
     "Digoxin + macrolide: elevated digoxin levels via P-gp inhibition; toxicity risk."),
    (["lisinopril", "enalapril", "ramipril", "losartan", "valsartan", "candesartan"],
     ["spironolactone", "eplerenone", "amiloride", "triamterene"],
     "major",
     "ACEi/ARB + potassium-sparing diuretic: risk of severe hyperkalemia; monitor K+ closely."),
    (["sildenafil", "tadalafil", "vardenafil"],
     ["nitroglycerin", "isosorbide", "nitroprusside"],
     "contraindicated",
     "PDE5 inhibitor + nitrate: risk of profound hypotension; combination contraindicated."),
    (["theophylline"], ["ciprofloxacin"],
     "major",
     "Theophylline + ciprofloxacin: CYP1A2 inhibition raises theophylline levels; toxicity risk (narrow therapeutic index)."),
    (["cyclosporine", "tacrolimus"], ["clarithromycin", "erythromycin"],
     "major",
     "Calcineurin inhibitor + macrolide: CYP3A4/P-gp inhibition raises immunosuppressant levels; nephrotoxicity risk."),
]


def _normalize(name: str) -> str:
    return " ".join(name.lower().split())


def _matches(terms: list[str], name: str) -> bool:
    return any(t in name for t in terms)


def find_interactions(drug_names: list[str]) -> list[dict[str, object]]:
    """Match a list of medication names pairwise against the rule table."""
    names = [_normalize(n) for n in drug_names]
    out: list[dict[str, object]] = []
    seen: set[tuple[int, int]] = set()
    for i, a in enumerate(names):
        for j, b in enumerate(names):
            if j <= i:
                continue
            for terms_a, terms_b, severity, desc in INTERACTION_RULES:
                hit = ((_matches(terms_a, a) and _matches(terms_b, b))
                       or (_matches(terms_b, a) and _matches(terms_a, b)))
                if hit and (i, j) not in seen:
                    seen.add((i, j))
                    out.append({
                        "severity": severity,
                        "description": desc,
                        "drugs": sorted([drug_names[i], drug_names[j]]),
                        "source": "local ONC high-priority DDI subset (RxNav API discontinued 2024-01)",
                    })
    return out
