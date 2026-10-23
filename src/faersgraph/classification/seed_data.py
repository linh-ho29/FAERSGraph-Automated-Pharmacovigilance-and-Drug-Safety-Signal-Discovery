"""Curated classification seed data for FAERSGraph's four focus drug classes.

These dictionaries back BOTH `drug_class.classify()` (client-side ground truth, applied to
every fetched report) and `openfda.query_builder` (server-side openFDA `search=` narrowing to
conserve the keyless daily quota) -- single source of truth, do not duplicate these lists
elsewhere.

Deliberately kept tight and high-precision: false negatives (falling through to UNKNOWN or the
small-molecule default) are preferred over false positives. Extend these sets as new drugs are
identified, but verify each addition against a real FAERS/openFDA record first.

Known false-positive traps intentionally EXCLUDED from any suffix list below:
  - "-nib" (kinase inhibitors, e.g. imatinib, erlotinib) is a classic SMALL MOLECULE stem, not protein.
  - "-parin" (heparins, e.g. enoxaparin) is a small-molecule/polysaccharide stem, not peptide.
"""

from .types import DrugClass

# siRNA therapeutics approved/named as of this writing -- an exhaustive, unambiguous list (the
# USAN "-siran" stem is unique to this class, so exact substance-name matches are high confidence).
SIRNA_SUBSTANCE_NAMES: frozenset[str] = frozenset(
    {
        "patisiran",
        "givosiran",
        "lumasiran",
        "inclisiran",
        "vutrisiran",
        "nedosiran",
        "fitusiran",
        "tivanisiran",
    }
)
SIRNA_NAME_SUFFIXES: tuple[str, ...] = ("siran",)

# Monoclonal antibodies ("-mab") and fusion proteins ("-cept") are large-molecule biologics.
PROTEIN_NAME_SUFFIXES: tuple[str, ...] = ("mab", "cept")

# Peptide hormone / peptide-drug USAN stems. Kept intentionally short and unambiguous.
PEPTIDE_NAME_SUFFIXES: tuple[str, ...] = (
    "relin",  # gonadorelin, goserelin, triptorelin
    "pressin",  # desmopressin, vasopressin
    "tide",  # octreotide, teriparatide, liraglutide, semaglutide
    "tropin",  # somatropin, corticotropin
)

# Checked, in this order, against both openfda.pharm_class_cs and openfda.pharm_class_epc.
PHARM_CLASS_KEYWORDS: tuple[tuple[DrugClass, frozenset[str]], ...] = (
    (DrugClass.SIRNA, frozenset({"small interfering rna", "sirna"})),
    (
        DrugClass.PROTEIN,
        frozenset(
            {
                "monoclonal antibody",
                "fusion protein",
                "recombinant protein",
                "immunoglobulin",
            }
        ),
    ),
    (DrugClass.PEPTIDE, frozenset({"peptide hormone", "peptide"})),
)
