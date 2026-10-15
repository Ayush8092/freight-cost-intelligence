import pytest

from conftest import HEADER, ship
from freight_watch.errors import DataValidationError
from freight_watch.loader import load_notes, load_shipments


def test_malformed_and_missing_values_are_quarantined_and_reported(make_shipments):
    df, rep = make_shipments(
        ship("OK1"),
        ship("BADDATE", date="2024-13-45"),
        ship("NODATE", date=""),
        ship("NOQTY", qty=""),
        ship("TXTCOST", cost="abc"),
        ship("ZEROQTY", qty=0),
        ship("NEGKM", km=-5),
        ship("ZEROCOST", cost=0),
    )
    assert list(df["shipment_id"]) == ["OK1"]
    assert rep.rows_quarantined == 7 and rep.rows_used == 1 and rep.rows_read == 8
    assert rep.quarantined["missing_or_malformed_date"] == 2
    assert rep.quarantined["non_positive_quantity_or_distance"] == 2


def test_strict_mode_raises_on_bad_rows(make_shipments):
    with pytest.raises(DataValidationError):
        make_shipments(ship("OK1"), ship("BAD", qty=0), strict=True)


def test_missing_column_raises(tmp_path):
    p = tmp_path / "s.csv"
    p.write_text("shipment_id,origin\nS1,A\n")
    with pytest.raises(DataValidationError, match="missing columns"):
        load_shipments(p)


def test_missing_file_raises(tmp_path):
    with pytest.raises(DataValidationError, match="not found"):
        load_shipments(tmp_path / "nope.csv")


def test_notes_validation(tmp_path):
    p = tmp_path / "n.csv"
    p.write_text("note_id,date,applies_to,note\nN1,2025-01-01,All Routes,hello\nN1,2025-01-02,All Routes,again\n")
    with pytest.raises(DataValidationError, match="duplicate"):
        load_notes(p)
    p.write_text("note_id,date,applies_to,note\nN1,not-a-date,All Routes,hello\n")
    with pytest.raises(DataValidationError, match="malformed note dates"):
        load_notes(p)


def test_whitespace_is_trimmed(make_shipments):
    df, _ = make_shipments("S1, Mumbai , Pune ,Short,Steel,1,1,1,2024-01-01,T\n")
    assert df.loc[0, "route"] == "Mumbai-Pune"
