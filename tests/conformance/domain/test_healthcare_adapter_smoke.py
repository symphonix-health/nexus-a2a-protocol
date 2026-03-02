from shared.nexus_common.interop_healthcare import (
    classify_x12_transaction,
    validate_minimal_fhir_resource,
    validate_minimal_ncpdp_claim,
    validate_minimal_x12,
)


def test_minimal_fhir_patient_validates() -> None:
    ok, details = validate_minimal_fhir_resource(
        {
            "resourceType": "Patient",
            "id": "pat-001",
            "name": [{"family": "Doe", "given": ["Jane"]}],
            "birthDate": "1987-10-16",
            "gender": "female",
        }
    )
    assert ok is True
    assert details == "Patient"


def test_minimal_x12_270_validates_and_classifies() -> None:
    edi = (
        "ISA*00*          *00*          *ZZ*SENDER*ZZ*RECV*260101*1200*^*00501*000000001*0*T*:~"
        "GS*HS*SENDER*RECV*20260101*1200*1*X*005010X279A1~"
        "ST*270*0001~SE*2*0001~GE*1*1~IEA*1*000000001~"
    )

    ok, tx = validate_minimal_x12(edi)

    assert ok is True
    assert tx == "270"
    assert classify_x12_transaction(edi) == "270"


def test_minimal_ncpdp_required_fields() -> None:
    payload = {
        "BIN": "012345",
        "PCN": "ABC123",
        "Group": "GRP1",
        "CardholderID": "M000000001",
        "RxNumber": "RX1",
        "FillNumber": "0",
        "NDC": "00093015001",
        "Quantity": 30,
        "DaysSupply": 30,
        "PrescriberID": "1234567890",
        "PharmacyNPI": "1098765432",
    }

    ok, missing = validate_minimal_ncpdp_claim(payload)

    assert ok is True
    assert missing == []
