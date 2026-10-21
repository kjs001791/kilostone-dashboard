import pandas as pd

from pipeline.make_dummy import SETTINGS, inject


def test_inject_with_units_override_accepts_vehicle_ids():
    """run_real passes per-vehicle units for vehicle ids (V02...), which are not in SETTINGS."""
    clean = pd.DataFrame({
        "vehicle": ["V03"] * 6,
        "date": pd.date_range("2020-01-01", periods=6).date,
        "distance": [210.0, 220.0, 230.0, 240.0, 250.0, 260.0],
        "cumulative_distance": [1000.0, 1220.0, 1450.0, 1690.0, 1940.0, 2200.0],
    })
    clean["row_id"] = range(1, len(clean) + 1)
    dirty, truth = inject(clean, 1, "dev", error_rate=0.5, spacing=1, units_override={"V03": (1.0, 0.1)},
                          mix=dict(SETTINGS["dev"]["mix"]))
    assert len(dirty) == len(clean)
