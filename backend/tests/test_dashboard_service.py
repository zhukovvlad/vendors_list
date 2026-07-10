from app.services.dashboard import normalize_vendor_name


def test_normalize_collapses_case_space_punct() -> None:
    assert normalize_vendor_name("  Grundfos ") == "grundfos"
    assert normalize_vendor_name("Wilo-Pumpen") == normalize_vendor_name("wilo pumpen")


def test_normalize_strips_native_tail() -> None:
    assert normalize_vendor_name("WILO (Native)") == normalize_vendor_name("wilo")
