from __future__ import annotations

from tools.traffic_generator import select_bounded_scenarios, stable_scenario_key


def _scenario_ids(rows: list[dict]) -> list[str]:
    ids: list[str] = []
    for row in rows:
        ids.append(
            str(
                row.get("scenario_id")
                or row.get("id")
                or row.get("name")
                or ""
            )
        )
    return ids


def _sample_scenarios() -> list[dict]:
    return [
        {"scenario_id": "scn-c", "input_payload": {"task": {"id": "3"}}},
        {"scenario_id": "scn-a", "input_payload": {"task": {"id": "1"}}},
        {"scenario_id": "scn-f", "input_payload": {"task": {"id": "6"}}},
        {"scenario_id": "scn-b", "input_payload": {"task": {"id": "2"}}},
        {"scenario_id": "scn-e", "input_payload": {"task": {"id": "5"}}},
        {"scenario_id": "scn-d", "input_payload": {"task": {"id": "4"}}},
    ]


def test_select_bounded_scenarios_deterministic_same_seed_is_stable() -> None:
    scenarios = _sample_scenarios()
    selected_a = select_bounded_scenarios(
        scenarios,
        deterministic=True,
        seed=1729,
        max_scenarios=4,
    )
    selected_b = select_bounded_scenarios(
        scenarios,
        deterministic=True,
        seed=1729,
        max_scenarios=4,
    )
    assert _scenario_ids(selected_a) == _scenario_ids(selected_b)


def test_select_bounded_scenarios_deterministic_rotation_matches_seed() -> None:
    scenarios = _sample_scenarios()
    seed = 11
    max_scenarios = 3
    ordered = sorted(scenarios, key=stable_scenario_key)
    start = seed % len(ordered)
    expected = (ordered[start:] + ordered[:start])[:max_scenarios]

    selected = select_bounded_scenarios(
        scenarios,
        deterministic=True,
        seed=seed,
        max_scenarios=max_scenarios,
    )
    assert _scenario_ids(selected) == _scenario_ids(expected)


def test_select_bounded_scenarios_deterministic_different_seed_changes_selection() -> None:
    scenarios = _sample_scenarios()
    selected_a = select_bounded_scenarios(
        scenarios,
        deterministic=True,
        seed=1,
        max_scenarios=3,
    )
    selected_b = select_bounded_scenarios(
        scenarios,
        deterministic=True,
        seed=2,
        max_scenarios=3,
    )
    assert _scenario_ids(selected_a) != _scenario_ids(selected_b)


def test_select_bounded_scenarios_nondeterministic_mode_is_seed_stable() -> None:
    scenarios = _sample_scenarios()
    selected_a = select_bounded_scenarios(
        scenarios,
        deterministic=False,
        seed=99,
        max_scenarios=3,
    )
    selected_b = select_bounded_scenarios(
        scenarios,
        deterministic=False,
        seed=99,
        max_scenarios=3,
    )
    assert _scenario_ids(selected_a) == _scenario_ids(selected_b)
