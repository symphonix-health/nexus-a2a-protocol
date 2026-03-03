"""
HL7 V2 Gateway Agent
Port: 8065
Job Profile: Integration Engine Operator (Interop)

Handles legacy HL7 Version 2.x message translation to/from FHIR resources.
Supports ADT, ORU, ORM, SIU, and other common V2 message types.

Market Context:
- 95% of US healthcare organizations use HL7 V2.x
- 35+ countries with V2 implementations
- Primary interface standard for hospital systems (EHR, Lab, Radiology, ADT)

Typical message types:
- ADT (A01-A60): Admission, Discharge, Transfer patient events
- ORU (R01): Observation results from lab/radiology
- ORM (O01): Orders for procedures, tests, medications
- SIU (S12-S26): Scheduling information unsolicited
- DFT (P03): Detailed financial transactions
"""

from pathlib import Path

from fastapi import FastAPI

from shared.nexus_common.generic_demo_agent import build_generic_demo_app

APP_DIR = str(Path(__file__).resolve().parent.parent)
app: FastAPI = build_generic_demo_app(
    default_name="HL7 V2 Gateway Agent",
    app_dir=APP_DIR,
)
