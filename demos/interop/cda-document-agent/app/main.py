"""
CDA Document Agent
Port: 8066
Job Profile: Health Records Officer (Interop)

Handles Clinical Document Architecture (CDA R2) document generation, validation, and exchange.
Supports C-CDA (Consolidated CDA) templates mandated for US Meaningful Use and HIE.

Market Context:
- Billions of CDA documents exchanged annually in US HIE (Sequoia/eHealthExchange)
- C-CDA is US Meaningful Use mandate for document exchange
- Global adoption: EU (myhealth@eu), Australia, New Zealand, many national HIE programs

Typical document types:
- Continuity of Care Document (CCD)
- Discharge Summary
- Consultation Note
- Operative Note
- Diagnostic Imaging Report
- Progress Note
- Care Plan
"""

from pathlib import Path

from fastapi import FastAPI

from shared.nexus_common.generic_demo_agent import build_generic_demo_app

APP_DIR = str(Path(__file__).resolve().parent.parent)
app: FastAPI = build_generic_demo_app(
    default_name="CDA Document Agent",
    app_dir=APP_DIR,
)
