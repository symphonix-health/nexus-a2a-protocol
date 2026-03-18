from __future__ import annotations

from typing import Any

SOCRATES_KEYS = [
    "site",
    "onset",
    "character",
    "radiation",
    "associations",
    "time_course",
    "exacerbating_relieving",
    "severity",
]


STAGE_PROMPTS: dict[str, str] = {
    "site": (
        "Explore the exact location of the symptom.\n"
        "KEY QUESTIONS: Where exactly do you feel it? Can you point to the spot? "
        "Is it in one place or spread over an area? Is it superficial or deep?\n"
        "DECISION CRITERIA TO ADVANCE: Move on once the patient has localised the symptom "
        "to a specific anatomical region. If they are vague, ask them to point or use "
        "anatomical landmarks to narrow it down."
    ),
    "onset": (
        "Determine when and how the symptom started.\n"
        "KEY QUESTIONS: When did it first start? Did it come on suddenly or gradually? "
        "What were you doing when it started? Have you had it before?\n"
        "DECISION CRITERIA TO ADVANCE: Move on once you know the onset timing (acute vs "
        "chronic), whether it was sudden or gradual, and any precipitating activity or event."
    ),
    "character": (
        "Characterise the nature and quality of the symptom.\n"
        "KEY QUESTIONS: Can you describe what it feels like? Is it sharp, dull, burning, "
        "crushing, stabbing, or aching? Is it constant or does it throb/pulse?\n"
        "DECISION CRITERIA TO ADVANCE: Move on once the patient has described the quality "
        "in their own words. Avoid leading questions; let them choose descriptors freely "
        "before offering options."
    ),
    "radiation": (
        "Determine whether the symptom spreads to other areas.\n"
        "KEY QUESTIONS: Does it go anywhere else? Does it spread to your arm, back, jaw, "
        "or leg? Is the spread constant or does it come and go?\n"
        "DECISION CRITERIA TO ADVANCE: Move on once radiation pattern is established "
        "(present with direction, or confirmed absent). Radiation patterns are diagnostically "
        "important (e.g., left arm/jaw in cardiac pain, dermatome in radiculopathy)."
    ),
    "associations": (
        "Identify any associated symptoms accompanying the main complaint.\n"
        "KEY QUESTIONS: Have you noticed anything else along with this? Any nausea, vomiting, "
        "sweating, shortness of breath, dizziness, or visual changes? Any fever or weight loss?\n"
        "DECISION CRITERIA TO ADVANCE: Move on once relevant system-specific associated symptoms "
        "have been screened. Use the site and character to guide which associations to ask about "
        "(e.g., cardiac associations for chest pain, neurological associations for headache)."
    ),
    "time_course": (
        "Establish the temporal pattern of the symptom.\n"
        "KEY QUESTIONS: Is it there all the time or does it come and go? How long does each "
        "episode last? Is it getting better, worse, or staying the same? "
        "How often does it happen?\n"
        "DECISION CRITERIA TO ADVANCE: Move on once you understand the temporal pattern "
        "(constant vs intermittent, progression, frequency, and duration of episodes)."
    ),
    "exacerbating_relieving": (
        "Identify factors that worsen or improve the symptom.\n"
        "KEY QUESTIONS: Is there anything that makes it worse? Anything that makes it better? "
        "Does movement, rest, food, medication, position, or breathing affect it?\n"
        "DECISION CRITERIA TO ADVANCE: Move on once aggravating and relieving factors are "
        "documented. These are critical for differential diagnosis (e.g., pleuritic pain "
        "worse on inspiration, musculoskeletal pain worse with movement)."
    ),
    "severity": (
        "Quantify the severity and functional impact of the symptom.\n"
        "KEY QUESTIONS: On a scale of 0 to 10, where 0 is no pain and 10 is the worst "
        "you can imagine, how bad is it? Does it stop you from doing your normal activities? "
        "Does it wake you at night? Is this the worst it has ever been?\n"
        "DECISION CRITERIA TO ADVANCE: Move on once severity is quantified (numeric scale "
        "and/or functional impact). Compare to previous episodes if applicable. "
        "Severity helps determine urgency of investigation and treatment."
    ),
}


def stage_prompt_context(stage: str) -> str:
    """Return the prompt guidance for a SOCRATES assessment dimension."""
    return STAGE_PROMPTS.get(stage, STAGE_PROMPTS["site"])


def initial_progress() -> dict[str, Any]:
    return {"completed": [], "remaining": list(SOCRATES_KEYS)}


def update_progress(progress: dict[str, Any], patient_message: str) -> dict[str, Any]:
    msg = patient_message.lower()
    completed = list(progress.get("completed", []))
    remaining = [k for k in SOCRATES_KEYS if k not in completed]

    keyword_map = {
        "severity": ["/10", "pain scale", "severe", "mild"],
        "onset": ["started", "since", "sudden", "gradual"],
        "site": ["left", "right", "chest", "abdomen", "head"],
        "radiation": ["radiat", "spread", "to my arm", "to my back"],
        "character": ["sharp", "dull", "pressure", "burning", "crushing"],
        "associations": ["nausea", "sweat", "shortness of breath", "vomit"],
        "time_course": ["constant", "comes and goes", "intermittent"],
        "exacerbating_relieving": ["worse", "better", "relieved", "aggravated"],
    }
    for key in remaining:
        hints = keyword_map.get(key, [])
        if any(h in msg for h in hints):
            completed.append(key)

    completed = [k for k in SOCRATES_KEYS if k in completed]
    return {
        "completed": completed,
        "remaining": [k for k in SOCRATES_KEYS if k not in completed],
    }
