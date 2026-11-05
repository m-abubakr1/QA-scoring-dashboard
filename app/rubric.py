"""What a good support call looks like. Change this file to change how calls are judged."""
from dataclasses import dataclass

VERSION = "support-v1"


@dataclass(frozen=True)
class Criterion:
    id: str
    name: str
    weight: float
    description: str
    critical: bool = False  # a low score here raises an alert on its own


RUBRIC = [
    Criterion("greeting", "Greeting", 0.10,
              "Greets the customer, says who they are and the company name, and offers to help."),
    Criterion("empathy", "Empathy", 0.20,
              "Recognises how the customer feels and says so, without sounding scripted."),
    Criterion("resolution", "Resolution", 0.25,
              "Understands the real problem and gives a correct, complete answer or a clear next step."),
    Criterion("compliance", "Compliance", 0.25,
              "Checks who the customer is before sharing or changing account details, makes no promises "
              "it cannot keep (for example guaranteed refunds), and does not read out sensitive data.",
              critical=True),
    Criterion("professionalism", "Professionalism", 0.10,
              "Polite and clear. No rudeness, slang, blaming or talking over the customer."),
    Criterion("closing", "Closing", 0.10,
              "Sums up what was done, asks if there is anything else, and thanks the customer."),
]

SCALE = (
    "1 = very poor or harmful, 2 = poor, 3 = acceptable, 4 = good, 5 = excellent."
)

BY_ID = {c.id: c for c in RUBRIC}


def overall(scores: dict[str, int | None]) -> float | None:
    """Weighted score from 0 to 100. Criteria not seen yet (None) are left out, not counted as zero."""
    seen = [(BY_ID[i].weight, s) for i, s in scores.items() if s is not None and i in BY_ID]
    if not seen:
        return None
    total = sum(w for w, _ in seen)
    return round(sum(w * s for w, s in seen) / total / 5 * 100, 1)
