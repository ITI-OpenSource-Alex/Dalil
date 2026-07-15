from app.core.content_hash import compute_content_hash


def test_same_input_produces_same_hash():
    record = {"university": "ETH Zurich", "country": "Switzerland", "min_ects": 150}
    assert compute_content_hash(record) == compute_content_hash(dict(record))


def test_key_order_does_not_affect_hash():
    record_a = {"a": 1, "b": 2}
    record_b = {"b": 2, "a": 1}
    assert compute_content_hash(record_a) == compute_content_hash(record_b)


def test_changing_a_field_changes_the_hash():
    record = {"university": "ETH Zurich", "min_ects": 150}
    changed = {"university": "ETH Zurich", "min_ects": 120}
    assert compute_content_hash(record) != compute_content_hash(changed)


def test_hash_is_a_sha256_hex_digest():
    record = {"provider": "DAAD", "name": "Helmut-Schmidt-Programme"}
    result = compute_content_hash(record)
    assert isinstance(result, str)
    assert len(result) == 64
    int(result, 16)  # raises ValueError if not valid hex


def test_non_string_values_are_serialized_via_default_str():
    from datetime import date
    record = {"deadline": date(2026, 11, 3)}
    # default=str in json.dumps must handle non-JSON-native types without raising.
    result = compute_content_hash(record)
    assert isinstance(result, str)
