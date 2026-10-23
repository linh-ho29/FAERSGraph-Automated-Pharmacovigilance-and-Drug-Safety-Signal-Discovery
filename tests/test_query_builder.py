from datetime import date

import pytest

from faersgraph.classification.types import DrugClass
from faersgraph.openfda.query_builder import (
    build_date_range_fragment,
    build_search_fragment,
    combine_fragments,
)


def test_sirna_fragment_contains_substance_names_and_cs_field() -> None:
    fragment = build_search_fragment(DrugClass.SIRNA)
    assert "patisiran" in fragment
    assert "pharm_class_cs" in fragment
    assert "substance_name" in fragment


def test_protein_fragment_contains_mab_and_cept_wildcards() -> None:
    fragment = build_search_fragment(DrugClass.PROTEIN)
    assert "*mab" in fragment
    assert "*cept" in fragment


def test_peptide_fragment_contains_peptide_suffixes() -> None:
    fragment = build_search_fragment(DrugClass.PEPTIDE)
    assert "*pressin" in fragment
    assert "*tide" in fragment


def test_small_molecule_fragment_is_empty() -> None:
    assert build_search_fragment(DrugClass.SMALL_MOLECULE) == ""


def test_unknown_class_raises() -> None:
    with pytest.raises(ValueError):
        build_search_fragment(DrugClass.UNKNOWN)


def test_date_range_fragment_format() -> None:
    fragment = build_date_range_fragment(date(2024, 1, 1), date(2024, 3, 31))
    assert fragment == "receivedate:[20240101 TO 20240331]"


def test_combine_fragments_joins_with_and() -> None:
    combined = combine_fragments(
        build_search_fragment(DrugClass.SIRNA),
        build_date_range_fragment(date(2024, 1, 1), date(2024, 3, 31)),
    )
    assert " AND " in combined
    assert combined.startswith("(")
    assert combined.endswith("]")


def test_combine_fragments_skips_empty() -> None:
    combined = combine_fragments("", build_date_range_fragment(date(2024, 1, 1), date(2024, 3, 31)))
    assert combined == "receivedate:[20240101 TO 20240331]"
