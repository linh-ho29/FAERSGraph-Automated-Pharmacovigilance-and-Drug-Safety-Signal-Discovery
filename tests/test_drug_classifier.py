import pytest

from faersgraph.classification.drug_class import DrugClass, classify


def _drug(
    medicinalproduct: str | None = None,
    generic_name: list[str] | None = None,
    substance_name: list[str] | None = None,
    pharm_class_cs: list[str] | None = None,
    pharm_class_epc: list[str] | None = None,
    application_number: list[str] | None = None,
) -> dict:
    openfda = {}
    if generic_name is not None:
        openfda["generic_name"] = generic_name
    if substance_name is not None:
        openfda["substance_name"] = substance_name
    if pharm_class_cs is not None:
        openfda["pharm_class_cs"] = pharm_class_cs
    if pharm_class_epc is not None:
        openfda["pharm_class_epc"] = pharm_class_epc
    if application_number is not None:
        openfda["application_number"] = application_number
    entry: dict = {}
    if medicinalproduct is not None:
        entry["medicinalproduct"] = medicinalproduct
    if openfda:
        entry["openfda"] = openfda
    return entry


CASES = [
    pytest.param(
        _drug(medicinalproduct="ONPATTRO", substance_name=["PATISIRAN"]),
        DrugClass.SIRNA,
        "substance_name_exact",
        id="patisiran_sirna",
    ),
    pytest.param(
        _drug(medicinalproduct="LEQVIO", substance_name=["INCLISIRAN"]),
        DrugClass.SIRNA,
        "substance_name_exact",
        id="inclisiran_sirna",
    ),
    pytest.param(
        _drug(
            medicinalproduct="HUMIRA",
            substance_name=["ADALIMUMAB"],
            pharm_class_cs=["Monoclonal Antibody [EPC]"],
            application_number=["BLA125057"],
        ),
        DrugClass.PROTEIN,
        "pharm_class_keyword",
        id="adalimumab_protein_mab",
    ),
    pytest.param(
        _drug(
            medicinalproduct="ENBREL",
            substance_name=["ETANERCEPT"],
            pharm_class_cs=["Fusion Protein [EPC]"],
        ),
        DrugClass.PROTEIN,
        "pharm_class_keyword",
        id="etanercept_protein_cept",
    ),
    pytest.param(
        _drug(
            medicinalproduct="DDAVP",
            substance_name=["DESMOPRESSIN"],
            pharm_class_epc=["Vasopressin Analog [EPC]"],
        ),
        DrugClass.PEPTIDE,
        "name_suffix:pressin",
        id="desmopressin_peptide",
    ),
    pytest.param(
        _drug(
            medicinalproduct="SANDOSTATIN",
            substance_name=["OCTREOTIDE"],
            pharm_class_cs=["Peptide Hormone [EPC]"],
        ),
        DrugClass.PEPTIDE,
        "pharm_class_keyword",
        id="octreotide_peptide",
    ),
    pytest.param(
        _drug(
            medicinalproduct="GLEEVEC",
            substance_name=["IMATINIB"],
            application_number=["NDA021588"],
        ),
        DrugClass.SMALL_MOLECULE,
        "default_small_molecule_fallback",
        id="imatinib_small_molecule_fallback_not_nib_stem",
    ),
    pytest.param(
        {},
        DrugClass.UNKNOWN,
        "no_identifying_fields",
        id="empty_entry_unknown",
    ),
]


@pytest.mark.parametrize("drug_entry,expected_class,expected_rule_prefix", CASES)
def test_classify(drug_entry: dict, expected_class: DrugClass, expected_rule_prefix: str) -> None:
    result = classify(drug_entry)
    assert result.drug_class == expected_class
    assert result.matched_rule.startswith(expected_rule_prefix)


def test_imatinib_is_not_misclassified_via_nib_stem() -> None:
    # Guards against accidentally seeding "-nib" as a protein/peptide suffix later.
    result = classify(_drug(medicinalproduct="GLEEVEC", substance_name=["IMATINIB"]))
    assert result.drug_class == DrugClass.SMALL_MOLECULE


def test_heparin_is_not_misclassified_as_peptide_via_parin_stem() -> None:
    # Guards against accidentally seeding "-parin" as a peptide suffix later.
    result = classify(_drug(medicinalproduct="LOVENOX", substance_name=["ENOXAPARIN"]))
    assert result.drug_class != DrugClass.PEPTIDE
