from nexus_a2a_protocol.interop.profile_registry import InMemoryProfileRegistry, ProfileRecord


def test_resolve_exact_versioned_request() -> None:
    registry = InMemoryProfileRegistry()
    registry.create_profile(
        ProfileRecord(
            profile_id="health.fhir.r4.core",
            version="1.0.0",
            adapter_endpoint="http://localhost:9001",
        )
    )

    resolved = registry.resolve(requested_profile="health.fhir.r4.core@1.0.0")

    assert resolved is not None
    assert resolved.profile_id == "health.fhir.r4.core"
    assert resolved.version == "1.0.0"


def test_resolve_falls_back_highest_semver() -> None:
    registry = InMemoryProfileRegistry()
    registry.create_profile(
        ProfileRecord(
            profile_id="health.x12.5010.270",
            version="1.0.0",
            adapter_endpoint="http://localhost:9002",
        )
    )
    registry.create_profile(
        ProfileRecord(
            profile_id="health.x12.5010.270",
            version="1.2.0",
            adapter_endpoint="http://localhost:9002",
        )
    )

    resolved = registry.resolve(requested_profile="health.x12.5010.270")

    assert resolved is not None
    assert resolved.version == "1.2.0"


def test_resolve_acceptable_profile_range() -> None:
    registry = InMemoryProfileRegistry()
    registry.create_profile(
        ProfileRecord(
            profile_id="health.ncpdp.telecom.d0",
            version="2.0.0",
            adapter_endpoint="http://localhost:9003",
        )
    )

    resolved = registry.resolve(
        requested_profile="health.unknown",
        acceptable_profiles=[{"profileId": "health.ncpdp.telecom.d0", "versionRange": "2.x"}],
    )

    assert resolved is not None
    assert resolved.profile_id == "health.ncpdp.telecom.d0"
    assert resolved.version == "2.0.0"
    assert resolved.version == "2.0.0"
