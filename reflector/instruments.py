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

ACE wording follows the standard CDC-Kaiser 10-item Adverse Childhood
Experiences Questionnaire (Felitti et al. 1998), public domain —
reconstructed from training knowledge, verify against
https://www.cdc.gov/violence-prevention/aces/ before treating as precise.

Big Five wording follows Goldberg's (1992) 50-item IPIP Big-Five Factor
Markers, public domain via the International Personality Item Pool
(https://ipip.ori.org) — also reconstructed from training knowledge,
same caveat: verify item wording and reverse-scored keying against the
IPIP source before treating as psychometrically precise. Unlike the
symptom screeners above, this is a stable-trait instrument, not scored
as time-varying symptom severity.

Holmes-Rahe wording and Life Change Unit weights follow the original
Social Readjustment Rating Scale (Holmes & Rahe, 1967, Journal of
Psychosomatic Research), long-established public domain — reconstructed
from training knowledge, same verify-before-trusting caveat as above.
Note some item wording is dated (e.g. specific 1967 dollar amounts) —
reproduced faithfully rather than modernized, since altering item
wording would make it a different, unvalidated instrument.

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

ACE = {
    "id": "ace",
    "name": "ACE",
    "full_name": "Adverse Childhood Experiences Questionnaire",
    "instructions": (
        "The following asks about experiences during your first 18 years of life. This can be a heavy "
        "topic to revisit — answer at your own pace. Support is available if it brings anything difficult "
        "up: 988 Suicide & Crisis Lifeline (call/text 988), Crisis Text Line (text HOME to 741741)."
    ),
    "scale": [
        (0, "No"),
        (1, "Yes"),
    ],
    "items": [
        "Did a parent or other adult in the household often or very often swear at you, insult you, put "
        "you down, or humiliate you? Or act in a way that made you afraid that you might be physically hurt?",
        "Did a parent or other adult in the household often or very often push, grab, slap, or throw "
        "something at you? Or ever hit you so hard that you had marks or were injured?",
        "Did an adult or person at least 5 years older than you ever touch or fondle you, or have you "
        "touch their body in a sexual way? Or attempt or actually have oral, anal, or vaginal intercourse "
        "with you?",
        "Did you often or very often feel that no one in your family loved you or thought you were "
        "important or special? Or your family didn't look out for each other, feel close to each other, "
        "or support each other?",
        "Did you often or very often feel that you didn't have enough to eat, had to wear dirty clothes, "
        "and had no one to protect you? Or your parents were too drunk or high to take care of you or "
        "take you to the doctor if you needed it?",
        "Were your parents ever separated or divorced?",
        "Was your mother or stepmother often or very often pushed, grabbed, slapped, or had something "
        "thrown at her? Or sometimes, often, or very often kicked, bitten, hit with a fist, or hit with "
        "something hard? Or ever repeatedly hit for at least a few minutes, or threatened with a gun or "
        "knife?",
        "Did you live with anyone who was a problem drinker or alcoholic, or who used street drugs?",
        "Was a household member depressed or mentally ill, or did a household member attempt suicide?",
        "Did a household member go to prison?",
    ],
    "risk_item_index": None,
    "severity_cutoffs": [
        (0, 0, "No reported ACEs"),
        (1, 3, "Some reported ACEs"),
        (4, 10, "ACE score ≥ 4 — research literature associates this range with meaningfully higher "
                "long-term health risk; not a diagnosis, but may be worth discussing with a professional"),
    ],
}

BIG5 = {
    "id": "big5",
    "name": "Big Five",
    "full_name": "IPIP Big-Five Factor Markers (50-item)",
    "instructions": (
        "Describe yourself as you generally are now, not as you wish to be in the future. Describe "
        "yourself as you honestly see yourself, in relation to other people you know of the same sex "
        "and roughly your same age. There are no right or wrong answers."
    ),
    "scale": [
        (1, "Very Inaccurate"),
        (2, "Moderately Inaccurate"),
        (3, "Neither Accurate Nor Inaccurate"),
        (4, "Moderately Accurate"),
        (5, "Very Accurate"),
    ],
    "items": [
        # Extraversion (0-9)
        "Am the life of the party.",
        "Feel comfortable around people.",
        "Start conversations.",
        "Talk to a lot of different people at parties.",
        "Don't mind being the center of attention.",
        "Don't talk a lot.",
        "Keep in the background.",
        "Have little to say.",
        "Don't like to draw attention to myself.",
        "Am quiet around strangers.",
        # Agreeableness (10-19)
        "Feel little concern for others.",
        "Am interested in people.",
        "Insult people.",
        "Sympathize with others' feelings.",
        "Am not interested in other people's problems.",
        "Have a soft heart.",
        "Am not really interested in others.",
        "Take time out for others.",
        "Feel others' emotions.",
        "Make people feel at ease.",
        # Conscientiousness (20-29)
        "Am always prepared.",
        "Pay attention to details.",
        "Get chores done right away.",
        "Like order.",
        "Follow a schedule.",
        "Am exacting in my work.",
        "Leave my belongings around.",
        "Make a mess of things.",
        "Often forget to put things back in their proper place.",
        "Shirk my duties.",
        # Emotional Stability (30-39)
        "Get stressed out easily.",
        "Worry about things.",
        "Am easily disturbed.",
        "Get upset easily.",
        "Change my mood a lot.",
        "Have frequent mood swings.",
        "Get irritated easily.",
        "Often feel blue.",
        "Am relaxed most of the time.",
        "Seldom feel blue.",
        # Intellect/Imagination (40-49)
        "Have a rich vocabulary.",
        "Have a vivid imagination.",
        "Have excellent ideas.",
        "Am quick to understand things.",
        "Use difficult words.",
        "Spend time reflecting on things.",
        "Am full of ideas.",
        "Am not interested in abstract ideas.",
        "Do not have a good imagination.",
        "Have difficulty understanding abstract ideas.",
    ],
    "risk_item_index": None,
    "subscales": [
        {"name": "Extraversion", "items": list(range(0, 10)), "reverse": [5, 6, 7, 8, 9]},
        {"name": "Agreeableness", "items": list(range(10, 20)), "reverse": [10, 12, 14, 16]},
        {"name": "Conscientiousness", "items": list(range(20, 30)), "reverse": [26, 27, 28, 29]},
        {"name": "Emotional Stability", "items": list(range(30, 40)), "reverse": [30, 31, 32, 33, 34, 35, 36, 37]},
        {"name": "Intellect/Imagination", "items": list(range(40, 50)), "reverse": [47, 48, 49]},
    ],
}

HOLMES_RAHE = {
    "id": "holmesrahe",
    "name": "Holmes-Rahe",
    "full_name": "Social Readjustment Rating Scale (Life Events)",
    "instructions": (
        "Which of the following have you experienced in the past 12 months? This covers work, family, "
        "finances, and other life changes — including ones that might feel positive (marriage, a big "
        "achievement) as well as difficult ones. Change itself is what's being measured here, not just hardship."
    ),
    "scale": [
        (0, "No"),
        (1, "Yes"),
    ],
    "items": [
        "Death of spouse", "Divorce", "Marital separation", "Jail term",
        "Death of a close family member", "Personal injury or illness", "Marriage", "Fired at work",
        "Marital reconciliation", "Retirement", "Change in health of a family member", "Pregnancy",
        "Sex difficulties", "Gain of a new family member", "Business readjustment",
        "Change in financial state", "Death of a close friend", "Change to a different line of work",
        "Change in number of arguments with spouse", "Mortgage over $10,000",
        "Foreclosure of mortgage or loan", "Change in responsibilities at work",
        "Son or daughter leaving home", "Trouble with in-laws", "Outstanding personal achievement",
        "Spouse begins or stops work", "Begin or end school", "Change in living conditions",
        "Revision of personal habits", "Trouble with boss", "Change in work hours or conditions",
        "Change in residence", "Change in schools", "Change in recreation",
        "Change in church activities", "Change in social activities", "Mortgage or loan less than $10,000",
        "Change in sleeping habits", "Change in number of family get-togethers",
        "Change in eating habits", "Vacation", "Christmas", "Minor violations of the law",
    ],
    "weights": [
        100, 73, 65, 63,
        63, 53, 50, 47,
        45, 45, 44, 40,
        39, 39, 39,
        38, 37, 36,
        35, 31,
        30, 29,
        29, 29, 28,
        26, 26, 25,
        24, 23, 20,
        20, 20, 19,
        19, 18, 17,
        16, 15,
        15, 13, 12, 11,
    ],
    "risk_item_index": None,
    "severity_cutoffs": [
        (0, 149, "Low — lower likelihood of stress-related health impact over the next year, per the scale's original research"),
        (150, 299, "Moderate — roughly 50% likelihood of stress-related health impact over the next year, per the scale's original research"),
        (300, 2000, "High — roughly 80% likelihood of stress-related health impact over the next year, per the scale's original research"),
    ],
}

INSTRUMENTS = {i["id"]: i for i in (PHQ9, GAD7, PCL5, ACE, BIG5, HOLMES_RAHE)}


def score(instrument: dict, responses: list[int]) -> tuple[int, str, bool]:
    if "weights" in instrument:
        # e.g. Holmes-Rahe: responses are 0/1 (didn't/did happen), each
        # endorsed item contributes its own fixed weight, not its response
        # value, to the total.
        total = sum(w * r for w, r in zip(instrument["weights"], responses))
    else:
        total = sum(responses)
    if "severity_cutoffs" in instrument:
        severity = next(
            (label for lo, hi, label in instrument["severity_cutoffs"] if lo <= total <= hi),
            "Unknown",
        )
    else:
        severity = "Not applicable — see subscale breakdown"
    risk_idx = instrument["risk_item_index"]
    risk_flag = risk_idx is not None and responses[risk_idx] > 0
    return total, severity, risk_flag


def score_subscales(instrument: dict, responses: list[int]) -> list[tuple[str, int]]:
    """For instruments with a 'subscales' key (e.g. Big Five) — a single
    summed total isn't psychometrically meaningful, so score each trait
    independently instead, applying reverse-keying (6 - response on this
    1-5 scale) for items in that subscale's 'reverse' list."""
    results = []
    for sub in instrument["subscales"]:
        total = sum(
            (6 - responses[i]) if i in sub["reverse"] else responses[i]
            for i in sub["items"]
        )
        results.append((sub["name"], total))
    return results
