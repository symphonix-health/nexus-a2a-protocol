"""Clinical Pathways — Individualised pathway personalisation engine.

This package implements a four-layer architecture for personalising
nationally approved clinical pathways using patient context:

    Layer 1 — Standard Pathway (knowledge repository)
    Layer 2 — Patient Context (FHIR-aligned context assembly)
    Layer 3 — Decision (pathway personalisation engine)
    Layer 4 — Governance (audit, explainability, consent)
"""

__version__ = "0.1.0"
