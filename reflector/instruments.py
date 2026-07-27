"""
Validated, public-domain self-assessment instruments.

PHQ-9 and GAD-7 wording matches the standard public-domain text
(Spitzer/Kroenke/Williams, Pfizer Inc. — no permission required to
reproduce). PCL-5 wording follows the standard published 20-item list
(Weathers et al. 2013, National Center for PTSD, public domain) —
reconstructed from training knowledge rather than a freshly-fetched
source this session, so verify item wording against the official PDF
(https://www.ptsd.va.gov/professional/assessment/documents/PCL5_Standard_form.pdf)
before treating this as clinically precise.

These are self-report screening tools, not diagnostic instruments —
framed throughout this project as input to self-reflection, not a
substitute for evaluation by a licensed clinician.
"""

PHQ9 = {
    "id": "phq9",
    "name": "PHQ-9",
    "full_name": "Patient Health Questionnaire-9 (Depression)",
    "instructions": "Over the last 2 weeks, how often have you been bothered by any of the following problems?",
    "scale": [
        (0, "Not at all"),
        (1, "Several days"),
        (2, "More than half the days"),
        (3, "Nearly every day"),
    ],
    "items": [
        "Little interest or pleasure in doing things",
        "Feeling down, depressed, or hopeless",
        "Trouble falling or staying asleep, or sleeping too much",
        "Feeling tired or having little energy",
        "Poor appetite or overeating",
        "Feeling bad about yourself — or that you are a failure, or have let yourself or your family down",
        "Trouble concentrating on things, such as reading the newspaper or watching television",
        "Moving or speaking so slowly that other people could have noticed? Or the opposite — being so "
        "fidgety or restless that you have been moving around a lot more than usual",
        "Thoughts that you would be better off dead, or of hurting yourself in some way",
    ],
    "risk_item_index": 8,
    "severity_cutoffs": [
        (0, 4, "Minimal"),
        (5, 9, "Mild"),
        (10, 14, "Moderate"),
        (15, 19, "Moderately severe"),
        (20, 27, "Severe"),
    ],
}

GAD7 = {
    "id": "gad7",
    "name": "GAD-7",
    "full_name": "Generalized Anxiety Disorder-7",
    "instructions": "Over the last 2 weeks, how often have you been bothered by the following problems?",
    "scale": [
        (0, "Not at all"),
        (1, "Several days"),
        (2, "More than half the days"),
        (3, "Nearly every day"),
    ],
    "items": [
        "Feeling nervous, anxious, or on edge",
        "Not being able to stop or control worrying",
        "Worrying too much about different things",
        "Trouble relaxing",
        "Being so restless that it is hard to sit still",
        "Becoming easily annoyed or irritable",
        "Feeling afraid, as if something awful might happen",
    ],
    "risk_item_index": None,
    "severity_cutoffs": [
        (0, 4, "Minimal"),
        (5, 9, "Mild"),
        (10, 14, "Moderate"),
        (15, 21, "Severe"),
    ],
}

PCL5 = {
    "id": "pcl5",
    "name": "PCL-5",
    "full_name": "PTSD Checklist for DSM-5",
    "instructions": "In the past month, how much were you bothered by:",
    "scale": [
        (0, "Not at all"),
        (1, "A little bit"),
        (2, "Moderately"),
        (3, "Quite a bit"),
        (4, "Extremely"),
    ],
    "items": [
        "Repeated, disturbing, and unwanted memories of the stressful experience?",
        "Repeated, disturbing dreams of the stressful experience?",
        "Suddenly feeling or acting as if the stressful experience were actually happening again "
        "(as if you were actually back there reliving it)?",
        "Feeling very upset when something reminded you of the stressful experience?",
        "Having strong physical reactions when something reminded you of the stressful experience "
        "(for example, heart pounding, trouble breathing, sweating)?",
        "Avoiding memories, thoughts, or feelings related to the stressful experience?",
        "Avoiding external reminders of the stressful experience (for example, people, places, "
        "conversations, activities, objects, or situations)?",
        "Trouble remembering important parts of the stressful experience?",
        "Having strong negative beliefs about yourself, other people, or the world (for example, "
        "having thoughts such as: I am bad, there is something seriously wrong with me, no one can "
        "be trusted, the world is completely dangerous)?",
        "Blaming yourself or someone else for the stressful experience or what happened after it?",
        "Having strong negative feelings such as fear, horror, anger, guilt, or shame?",
        "Loss of interest in activities that you used to enjoy?",
        "Feeling distant or cut off from other people?",
        "Trouble experiencing positive feelings (for example, being unable to feel happiness or "
        "have loving feelings for people close to you)?",
        "Irritable behavior, angry outbursts, or acting aggressively?",
        "Taking too many risks or doing things that could cause you harm?",
        "Being 'superalert' or watchful or on guard?",
        "Feeling jumpy or easily startled?",
        "Having difficulty concentrating?",
        "Trouble falling or staying asleep?",
    ],
    "risk_item_index": None,
    "severity_cutoffs": [
        (0, 32, "Below typical research cutoff"),
        (33, 80, "At or above typical research cutoff (≥ 33)"),
    ],
}

INSTRUMENTS = {i["id"]: i for i in (PHQ9, GAD7, PCL5)}


def score(instrument: dict, responses: list[int]) -> tuple[int, str, bool]:
    total = sum(responses)
    severity = next(
        (label for lo, hi, label in instrument["severity_cutoffs"] if lo <= total <= hi),
        "Unknown",
    )
    risk_idx = instrument["risk_item_index"]
    risk_flag = risk_idx is not None and responses[risk_idx] > 0
    return total, severity, risk_flag
