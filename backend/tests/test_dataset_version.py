import hashlib

from app.research.dataset_version import DatasetVersion, build_dataset_id, compute_file_sha256


def test_build_dataset_id_format():
    assert build_dataset_id("EUR/USD", "1h", 2012, 2022) == "EURUSD_1H_2012_2022_v1"
    assert build_dataset_id("EUR/USD", "1h", 2012, 2022, version=2) == "EURUSD_1H_2012_2022_v2"


def test_compute_file_sha256_matches_hashlib(tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("Date,open,high,low,close\n2024-01-01,1.1,1.1,1.1,1.1\n")
    expected = hashlib.sha256(f.read_bytes()).hexdigest()
    assert compute_file_sha256(str(f)) == expected


def test_dataset_version_to_dict_is_json_safe():
    import json
    dv = DatasetVersion(
        dataset_id="EURUSD_1H_2012_2022_v1", source="test", license="Apache-2.0",
        symbol="EUR/USD", timeframe="1h", period_start="2012-01-01", period_end="2022-01-01",
        candle_count=1000, import_version="v1", sha256="abc123",
    )
    json.dumps(dv.to_dict())
