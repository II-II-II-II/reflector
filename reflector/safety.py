"""
Coarse keyword safety net for free-text input (chat messages), separate
from the PHQ-9 structured risk item. This is deliberately dumb — a regex
pass, not clinical judgment — because it needs to be something we can
trust completely rather than something an LLM might paraphrase around.
It will have false negatives and false positives; it's a supplementary
net, not a replacement for the model noticing context, and not a
diagnostic tool.
"""

import re

_CRISIS_PATTERNS = [
    r"\bkill(ing)?\s+myself\b",
    r"\bsuicid(e|al)\b",
    r"\bend(ing)?\s+my\s+life\b",
    r"\bwant(ed)?\s+to\s+die\b",
    r"\bbetter\s+off\s+dead\b",
    r"\bno\s+(reason|point)\s+(to|in)\s+(live|living|going\s+on)\b",
    r"\bhurt(ing)?\s+myself\b",
    r"\bself[\s-]?harm\b",
    r"\bdon'?t\s+want\s+to\s+(be\s+alive|live\s+anymore|exist)\b",
]
_CRISIS_RE = re.compile("|".join(_CRISIS_PATTERNS), re.IGNORECASE)


def contains_crisis_language(text: str) -> bool:
    return bool(_CRISIS_RE.search(text))
