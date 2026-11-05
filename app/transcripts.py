"""Turn pasted or uploaded transcript text into a list of {"speaker", "text"} lines."""
import json
import re

MAX_LINES = 300
MAX_LINE_CHARS = 1000
MAX_TOTAL_CHARS = 100_000

AGENT_WORDS = {"agent", "rep", "representative", "advisor", "support", "csr", "operator", "assistant"}
CUSTOMER_WORDS = {"customer", "caller", "client", "cust", "user"}

# "Agent: hello", "[agent] hello", "AGENT - hello"
LABELLED = re.compile(r"^\s*\[?\s*([A-Za-z]+)\s*\]?\s*[:\-]\s*(.*\S)\s*$|^\s*\[\s*([A-Za-z]+)\s*\]\s*(.*\S)\s*$")


class TranscriptError(ValueError):
    """The text could not be understood. The message is safe to show to the user."""


def speaker_of(word: str) -> str | None:
    word = word.lower()
    if word in AGENT_WORDS:
        return "agent"
    if word in CUSTOMER_WORDS:
        return "customer"
    return None


def _clean(lines: list[dict]) -> list[dict]:
    if len(lines) < 2:
        raise TranscriptError("A transcript needs at least 2 lines.")
    if len(lines) > MAX_LINES:
        raise TranscriptError(f"A transcript can have at most {MAX_LINES} lines.")
    for i, ln in enumerate(lines, 1):
        if len(ln["text"]) > MAX_LINE_CHARS:
            raise TranscriptError(f"Line {i} is longer than {MAX_LINE_CHARS} characters.")
    return lines


def _from_json(data) -> list[dict]:
    items = data.get("lines") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise TranscriptError('JSON must be a list of {"speaker", "text"} or an object with a "lines" list.')
    out = []
    for i, item in enumerate(items, 1):
        if not isinstance(item, dict) or not isinstance(item.get("text"), str) or not item["text"].strip():
            raise TranscriptError(f"Line {i} needs a text.")
        speaker = speaker_of(str(item.get("speaker", "")))
        if speaker is None:
            raise TranscriptError(f'Line {i} needs a speaker of "agent" or "customer".')
        out.append({"speaker": speaker, "text": item["text"].strip()})
    return out


def _from_text(text: str) -> list[dict]:
    out: list[dict] = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        m = LABELLED.match(raw)
        label = (m.group(1) or m.group(3)) if m else None
        speaker = speaker_of(label) if label else None
        if speaker:
            out.append({"speaker": speaker, "text": (m.group(2) or m.group(4)).strip()})
        elif out:  # no label: it continues what the same person was saying
            out[-1]["text"] += " " + raw.strip()
        else:
            raise TranscriptError('Each line should start with "Agent:" or "Customer:".')
    return out


def parse_transcript(text: str) -> list[dict]:
    if len(text) > MAX_TOTAL_CHARS:
        raise TranscriptError("That transcript is too long.")
    stripped = text.strip()
    if stripped[:1] in "[{":
        try:
            return _clean(_from_json(json.loads(stripped)))
        except json.JSONDecodeError:
            pass  # not JSON after all, a line like "[agent] hello" starts with "[" too
    return _clean(_from_text(text))
