from nexus_a2a_protocol.interop.contracts import (
    ActorContext,
    ArtifactPart,
    NexusEnvelope,
    NexusProblem,
)


def test_nexus_envelope_serialization() -> None:
    envelope = NexusEnvelope(
        envelope_version="1.0.0",
        task_id="task-001",
        correlation_id="corr-001",
        actor=ActorContext(sub="svc://fhir-agent", actor_type="service", scopes=["fhir.write"]),
        requested_profile="health.fhir.r4.core",
        parts=[
            ArtifactPart(
                part_id="part-1",
                kind="fhir.resource",
                content_type="application/fhir+json",
                inline_payload={"resourceType": "Patient", "id": "p1"},
            )
        ],
    )

    payload = envelope.to_dict()

    assert payload["envelopeVersion"] == "1.0.0"
    assert payload["actor"]["type"] == "service"
    assert payload["parts"][0]["kind"] == "fhir.resource"


def test_nexus_problem_serialization() -> None:
    problem = NexusProblem(
        code="unsupported_profile",
        message="No adapter registered",
        retryable=False,
        correlation_id="corr-404",
    )

    payload = problem.to_dict()

    assert payload["code"] == "unsupported_profile"
    assert payload["retryable"] is False
    assert payload["correlationId"] == "corr-404"
