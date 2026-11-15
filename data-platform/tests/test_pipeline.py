from data_platform.demo import run


def test_medallion_smoke(tmp_path):
    result = run(output_dir=tmp_path)
    assert result == {"bronze": 4, "silver": 4, "gold": 4}
    assert all((tmp_path / f"{layer}.parquet").exists() for layer in result)
