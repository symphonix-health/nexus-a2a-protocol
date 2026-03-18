"""Integration bridge — wires PersonalisedPathway output to BulletTrain agents.

This package converts the clinical-pathways personalisation engine output
(PersonalisedPathway, DeviationRegister, ExplainabilityReport) into the
input contracts expected by each downstream BulletTrain agent:

  - DiagnosticReasoningAgent  → strategy selection + context enrichment
  - TreatmentRecommendationAgent → contraindication-aware treatment plans
  - SafePrescribingAgent → excluded-medication guards
  - ReferralAgent → capability-driven referral routing
  - InvestigationPlannerAgent → guideline-linked investigation orders
  - ImagingAgent → contraindication-checked imaging requests
  - DischargeAgent → follow-up-adapted discharge plans
  - ContinuityAgent → monitoring schedule from pathway modifications
  - ChatAssistant → pathway-aware conversational context
  - APEX risk stratification → confidence feedback loop
"""
