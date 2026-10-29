"""Tests for festival normalization, regional applicability, and deduplication."""

from datetime import UTC, date, datetime

import pytest

from demand_ingestion.festival_models import FestivalRecord
from demand_ingestion.normalization.common import QuarantineErrorCategory
from demand_ingestion.normalization.festivals import (
    NormalizedFestivalRecord,
    compute_festival_content_hash,
    normalize_festival_batch,
    normalize_festival_record,
)


@pytest.fixture
def sample_festival_record():
    return FestivalRecord(
        country_code="IN",
        event_name="Durga Puja",
        event_date=date(2026, 10, 20),
        description="Celebration of Durga Puja in West Bengal",
        event_types=["Festival", "Observance"],
        primary_type="Festival",
        canonical_url="https://calendarific.com/holiday/india/durga-puja",
        locations="West Bengal",
        states="West Bengal",
        source="calendarific",
        retrieved_at_utc=datetime(2026, 10, 29, 12, 0, tzinfo=UTC),
    )


def test_valid_festival_normalization_from_record(sample_festival_record):
    normalized, quar = normalize_festival_record(sample_festival_record)

    assert quar is None
    assert normalized is not None
    assert normalized.schema_version == "v1"
    assert normalized.country_code == "IN"
    assert normalized.event_name == "Durga Puja"
    assert normalized.event_date == date(2026, 10, 20)
    assert normalized.target_year == 2026
    assert normalized.record_id == sample_festival_record.event_key
    assert normalized.regional_applicability == "regional"
    assert normalized.event_types == ["Festival", "Observance"]
    assert normalized.source == "calendarific"


def test_valid_festival_normalization_from_raw_dict():
    raw_payload = {
        "country_code": "in",
        "event_name": "  Diwali  ",
        "event_date": "2026-11-08",
        "description": "  Festival of Lights  ",
        "event_types": ["National holiday", "Festival"],
        "primary_type": "National holiday",
        "canonical_url": "https://calendarific.com/holiday/india/diwali",
        "locations": "All",
        "states": "",
        "source": "calendarific",
        "retrieved_at_utc": "2026-10-29T12:00:00Z",
    }
    normalized, quar = normalize_festival_record(raw_payload)

    assert quar is None
    assert normalized is not None
    assert normalized.country_code == "IN"
    assert normalized.event_name == "Diwali"
    assert normalized.description == "Festival of Lights"
    assert normalized.regional_applicability == "national"
    assert normalized.states is None


def test_country_code_normalized_and_validated():
    rec = NormalizedFestivalRecord(
        record_id="test_key_001",
        country_code="in",
        event_name="Republic Day",
        event_date=date(2026, 1, 26),
        retrieved_at_utc=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
    )
    assert rec.country_code == "IN"

    with pytest.raises(ValueError, match="two-letter country code"):
        NormalizedFestivalRecord(
            record_id="test_key_002",
            country_code="IND",
            event_name="Republic Day",
            event_date=date(2026, 1, 26),
            retrieved_at_utc=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
        )


def test_event_types_deduplicated_and_casefold_sorted():
    rec = NormalizedFestivalRecord(
        record_id="test_key_003",
        country_code="IN",
        event_name="Holi",
        event_date=date(2026, 3, 4),
        event_types=["seasonal", "Hindu", "Festival", "  Festival  "],
        retrieved_at_utc=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
    )
    # Deduplicated exact strings and sorted casefold
    assert rec.event_types == ["Festival", "Hindu", "seasonal"]


def test_regional_applicability_governance():
    # 1. National by locations="All"
    rec_nat1 = NormalizedFestivalRecord(
        record_id="test_key_nat1",
        country_code="IN",
        event_name="Independence Day",
        event_date=date(2026, 8, 15),
        locations="All",
        retrieved_at_utc=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
    )
    assert rec_nat1.regional_applicability == "national"

    # 2. National by primary_type containing 'national'
    rec_nat2 = NormalizedFestivalRecord(
        record_id="test_key_nat2",
        country_code="IN",
        event_name="Gandhi Jayanti",
        event_date=date(2026, 10, 2),
        primary_type="National holiday",
        retrieved_at_utc=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
    )
    assert rec_nat2.regional_applicability == "national"

    # 3. Regional by states or locations
    rec_reg = NormalizedFestivalRecord(
        record_id="test_key_reg",
        country_code="IN",
        event_name="Poila Boishakh",
        event_date=date(2026, 4, 15),
        states="West Bengal",
        retrieved_at_utc=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
    )
    assert rec_reg.regional_applicability == "regional"

    # 4. Unknown when no regional cues provided
    rec_unk = NormalizedFestivalRecord(
        record_id="test_key_unk",
        country_code="IN",
        event_name="Local Fair",
        event_date=date(2026, 5, 1),
        retrieved_at_utc=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
    )
    assert rec_unk.regional_applicability == "unknown"


def test_requested_year_boundary_mismatch_is_quarantined(sample_festival_record):
    # Event is for 2026, but requested_year is 2025
    normalized, quar = normalize_festival_record(
        sample_festival_record,
        requested_year=2025,
        ingestion_run_id="run_fest_001",
    )

    assert normalized is None
    assert quar is not None
    assert quar.error_category == QuarantineErrorCategory.DATE_OUT_OF_RANGE
    assert "does not match requested year 2025" in quar.error_message
    assert quar.ingestion_run_id == "run_fest_001"


def test_annual_event_keys_do_not_collide():
    rec_2025 = FestivalRecord(
        country_code="IN",
        event_name="Durga Puja",
        event_date=date(2025, 10, 1),
        canonical_url="https://calendarific.com/holiday/india/durga-puja",
        retrieved_at_utc=datetime(2025, 1, 1, 0, 0, tzinfo=UTC),
    )
    rec_2026 = FestivalRecord(
        country_code="IN",
        event_name="Durga Puja",
        event_date=date(2026, 10, 20),
        canonical_url="https://calendarific.com/holiday/india/durga-puja",
        retrieved_at_utc=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
    )

    norm_2025, _ = normalize_festival_record(rec_2025)
    norm_2026, _ = normalize_festival_record(rec_2026)

    assert norm_2025.record_id != norm_2026.record_id


def test_festival_content_hash_deterministic(sample_festival_record):
    h1 = compute_festival_content_hash(sample_festival_record)
    h2 = compute_festival_content_hash(sample_festival_record)
    assert h1 == h2

    # Modified description produces different hash
    mod_rec = sample_festival_record.model_copy(
        update={"description": "Different description"}
    )
    h3 = compute_festival_content_hash(mod_rec)
    assert h1 != h3


def test_batch_normalization_identical_duplicates_collapsed(sample_festival_record):
    # Two identical records
    rec1 = sample_festival_record
    rec2 = sample_festival_record.model_copy()

    accepted, quar, report = normalize_festival_batch([rec1, rec2])

    assert len(accepted) == 1
    assert len(quar) == 0
    assert report.input_records == 2
    assert report.accepted_records == 1
    assert report.identical_duplicates == 1
    assert report.conflicting_duplicates == 0
    assert report.rejected_records == 0


def test_batch_normalization_conflicting_duplicates_quarantined(
    sample_festival_record,
):
    rec1 = sample_festival_record
    # Same canonical event key, but differing description
    rec2 = sample_festival_record.model_copy(
        update={"description": "Conflicting description variant"}
    )

    accepted, quar, report = normalize_festival_batch([rec1, rec2])

    # Both must be quarantined
    assert len(accepted) == 0
    assert len(quar) == 2
    assert report.input_records == 2
    assert report.accepted_records == 0
    assert report.conflicting_duplicates == 2
    assert report.rejected_records == 2
    assert all(
        q.error_category == QuarantineErrorCategory.CONFLICTING_DUPLICATE
        for q in quar
    )


def test_batch_normalization_deterministic_sorting():
    rec_b = FestivalRecord(
        country_code="IN",
        event_name="B Event",
        event_date=date(2026, 5, 10),
        retrieved_at_utc=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
    )
    rec_a = FestivalRecord(
        country_code="IN",
        event_name="A Event",
        event_date=date(2026, 5, 10),
        retrieved_at_utc=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
    )
    rec_earlier = FestivalRecord(
        country_code="IN",
        event_name="Z Event",
        event_date=date(2026, 1, 1),
        retrieved_at_utc=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
    )

    accepted, _, _ = normalize_festival_batch([rec_b, rec_earlier, rec_a])

    assert len(accepted) == 3
    assert accepted[0].event_date == date(2026, 1, 1)
    assert accepted[1].event_name == "A Event"
    assert accepted[2].event_name == "B Event"
