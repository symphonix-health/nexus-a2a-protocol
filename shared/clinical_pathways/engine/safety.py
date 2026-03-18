"""Safety guardrails for pathway personalisation.

Cross-checks personalised pathways against allergies, drug interactions,
contraindications, and critical lab values.  Any violation produces a
safety warning or blocks the activity.
"""

from __future__ import annotations

from ..context.models import PatientContext
from ..models import Activity, PathwayDefinition
from .models import ModificationType, PathwayModification


class SafetyGuardrails:
    """Validates personalised pathway activities against patient safety constraints."""

    def check_all(
        self,
        pathway: PathwayDefinition,
        ctx: PatientContext,
    ) -> list[PathwayModification]:
        """Run all safety checks and return modifications/warnings."""
        mods: list[PathwayModification] = []
        for node in pathway.nodes:
            for activity in node.activities:
                mods.extend(self._check_contraindications(activity, ctx, node.node_id))
                mods.extend(self._check_allergy_conflicts(activity, ctx, node.node_id))
        mods.extend(self._check_critical_lab_values(ctx))
        mods.extend(self._check_drug_interactions(ctx))
        return mods

    def _check_contraindications(
        self,
        activity: Activity,
        ctx: PatientContext,
        node_id: str,
    ) -> list[PathwayModification]:
        """Check activity-level contraindications against patient context."""
        mods: list[PathwayModification] = []
        for ci in activity.contraindications:
            if self._criterion_matches(ci, ctx):
                mods.append(
                    PathwayModification(
                        modification_type=ModificationType.CONTRAINDICATION_FLAGGED,
                        node_id=node_id,
                        activity_id=activity.activity_id,
                        description=f"Contraindication for '{activity.name}': {ci.description}",
                        reason=ci.description,
                        context_factors=[ci.field, f"operator:{ci.operator.value}", f"value:{ci.value}"],
                        evidence_reference="Activity-level contraindication",
                    )
                )
        return mods

    def _check_allergy_conflicts(
        self,
        activity: Activity,
        ctx: PatientContext,
        node_id: str,
    ) -> list[PathwayModification]:
        """Check if any activity involves a known allergen."""
        mods: list[PathwayModification] = []
        if activity.fhir_resource_type != "MedicationRequest":
            return mods
        # Check if activity name or description references known allergens
        activity_text = f"{activity.name} {activity.description}".lower()
        for allergy in ctx.allergies:
            substance = allergy.substance.lower()
            if substance in activity_text:
                mods.append(
                    PathwayModification(
                        modification_type=ModificationType.SAFETY_OVERRIDE,
                        node_id=node_id,
                        activity_id=activity.activity_id,
                        description=f"ALLERGY ALERT: '{activity.name}' references '{allergy.substance}' — patient has documented allergy",
                        reason=f"Patient allergic to {allergy.substance} (reaction: {allergy.reaction}, severity: {allergy.severity.value})",
                        context_factors=["allergy", f"substance:{allergy.substance}", f"severity:{allergy.severity.value}"],
                    )
                )
        return mods

    def _check_critical_lab_values(self, ctx: PatientContext) -> list[PathwayModification]:
        """Flag critical lab values that require immediate attention."""
        mods: list[PathwayModification] = []

        # Potassium
        potassium = ctx.observation_value("potassium")
        if potassium is not None:
            if potassium > 6.0:
                mods.append(
                    PathwayModification(
                        modification_type=ModificationType.SAFETY_OVERRIDE,
                        description=f"CRITICAL: Hyperkalaemia (K+ = {potassium} mmol/L). Immediate management required.",
                        reason=f"Potassium {potassium} > 6.0 mmol/L — life-threatening if untreated",
                        context_factors=["critical_lab", f"potassium:{potassium}"],
                    )
                )
            elif potassium < 3.0:
                mods.append(
                    PathwayModification(
                        modification_type=ModificationType.SAFETY_OVERRIDE,
                        description=f"CRITICAL: Hypokalaemia (K+ = {potassium} mmol/L). Replacement required before proceeding.",
                        reason=f"Potassium {potassium} < 3.0 mmol/L — risk of arrhythmia",
                        context_factors=["critical_lab", f"potassium:{potassium}"],
                    )
                )

        # eGFR
        egfr = ctx.observation_value("egfr")
        if egfr is not None and egfr < 15:
            mods.append(
                PathwayModification(
                    modification_type=ModificationType.SAFETY_OVERRIDE,
                    description=f"CRITICAL: Severe renal failure (eGFR = {egfr}). Nephrology review required.",
                    reason=f"eGFR {egfr} < 15 — stage 5 CKD, may need renal replacement therapy",
                    context_factors=["critical_lab", f"egfr:{egfr}", "renal_failure"],
                )
            )

        # Lactate (sepsis relevant)
        lactate = ctx.observation_value("lactate")
        if lactate is not None and lactate > 4.0:
            mods.append(
                PathwayModification(
                    modification_type=ModificationType.URGENCY_ELEVATED,
                    description=f"CRITICAL: Severely elevated lactate ({lactate} mmol/L). Septic shock pathway.",
                    reason=f"Lactate {lactate} > 4.0 mmol/L — indicates severe tissue hypoperfusion",
                    context_factors=["critical_lab", f"lactate:{lactate}", "septic_shock"],
                )
            )

        return mods

    def _check_drug_interactions(self, ctx: PatientContext) -> list[PathwayModification]:
        """Check for known dangerous drug interactions in current medications."""
        mods: list[PathwayModification] = []
        active_meds = ctx.active_medication_codes()

        # ACEi/ARB + MRA + NSAID = triple whammy (renal risk)
        has_raas = any(m in active_meds for m in ("ace_inhibitor", "arb", "ramipril", "enalapril", "losartan", "candesartan"))
        has_mra = any(m in active_meds for m in ("spironolactone", "eplerenone", "mra"))
        has_nsaid = any(m in active_meds for m in ("nsaid", "ibuprofen", "naproxen", "diclofenac"))
        if has_raas and has_mra and has_nsaid:
            mods.append(
                PathwayModification(
                    modification_type=ModificationType.SAFETY_OVERRIDE,
                    description="DRUG INTERACTION: Triple whammy (ACEi/ARB + MRA + NSAID) — acute kidney injury risk",
                    reason="Combination of RAAS inhibitor, MRA, and NSAID significantly increases AKI risk",
                    context_factors=["drug_interaction", "triple_whammy", "aki_risk"],
                    evidence_reference="BNF interactions, NICE CG182",
                )
            )

        # Metformin + severe renal impairment
        has_metformin = "metformin" in active_meds
        egfr = ctx.observation_value("egfr")
        if has_metformin and egfr is not None and egfr < 30:
            mods.append(
                PathwayModification(
                    modification_type=ModificationType.CONTRAINDICATION_FLAGGED,
                    description="Metformin should be stopped — eGFR < 30",
                    reason=f"Patient is on metformin but eGFR is {egfr} (< 30). Lactic acidosis risk.",
                    context_factors=["metformin", f"egfr:{egfr}", "contraindication"],
                    evidence_reference="NICE NG28, BNF",
                )
            )

        return mods

    @staticmethod
    def _criterion_matches(criterion, ctx: PatientContext) -> bool:
        """Evaluate a single Criterion against the patient context."""
        from ..models import ComparisonOperator

        field = criterion.field
        op = criterion.operator
        expected = criterion.value

        # Resolve field value from context
        actual = _resolve_field(ctx, field)
        if actual is None:
            return op == ComparisonOperator.EXISTS and expected is False

        # When the field resolves to a list (e.g. observations[].potassium),
        # we need special handling depending on the operator.
        if isinstance(actual, list):
            if op == ComparisonOperator.CONTAINS:
                return any(str(expected).lower() in str(v).lower() for v in actual)
            if op == ComparisonOperator.EXISTS:
                return len(actual) > 0
            if op == ComparisonOperator.IN:
                return any(v in expected for v in actual) if isinstance(expected, list) else any(str(v) in str(expected) for v in actual)
            if op == ComparisonOperator.NOT_IN:
                return all(v not in expected for v in actual) if isinstance(expected, list) else True
            # For numeric comparisons on lists, check if ANY element satisfies
            numeric_vals = []
            for v in actual:
                try:
                    numeric_vals.append(float(v))
                except (TypeError, ValueError):
                    pass
            if not numeric_vals:
                return False
            if op == ComparisonOperator.GT:
                return any(v > float(expected) for v in numeric_vals)
            if op == ComparisonOperator.GE:
                return any(v >= float(expected) for v in numeric_vals)
            if op == ComparisonOperator.LT:
                return any(v < float(expected) for v in numeric_vals)
            if op == ComparisonOperator.LE:
                return any(v <= float(expected) for v in numeric_vals)
            if op == ComparisonOperator.EQ:
                return any(v == expected for v in actual)
            if op == ComparisonOperator.NE:
                return all(v != expected for v in actual)
            return False

        # Scalar value handling
        if op == ComparisonOperator.EXISTS:
            return actual is not None
        if op == ComparisonOperator.EQ:
            return actual == expected
        if op == ComparisonOperator.NE:
            return actual != expected
        if op == ComparisonOperator.GT:
            return float(actual) > float(expected)
        if op == ComparisonOperator.GE:
            return float(actual) >= float(expected)
        if op == ComparisonOperator.LT:
            return float(actual) < float(expected)
        if op == ComparisonOperator.LE:
            return float(actual) <= float(expected)
        if op == ComparisonOperator.IN:
            return actual in expected if isinstance(expected, list) else str(actual) in str(expected)
        if op == ComparisonOperator.NOT_IN:
            return actual not in expected if isinstance(expected, list) else str(actual) not in str(expected)
        if op == ComparisonOperator.CONTAINS:
            if isinstance(actual, list):
                return expected in actual
            return str(expected).lower() in str(actual).lower()
        return False


def _resolve_field(ctx: PatientContext, field: str) -> object:
    """Resolve a dot-path field against the patient context."""
    # Handle array lookups like conditions[].code
    if "[]." in field:
        collection_name, sub_field = field.split("[].", 1)
        collection = getattr(ctx, collection_name, None)
        if collection is None:
            return None
        values = [getattr(item, sub_field, None) for item in collection]
        return [v for v in values if v is not None]

    # Handle dot-path like demographics.age
    parts = field.split(".")
    obj: object = ctx
    for part in parts:
        if obj is None:
            return None
        obj = getattr(obj, part, None)
    return obj
