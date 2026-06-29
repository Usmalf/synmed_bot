RED_FLAG_KEYWORDS = {
    "chest pain",
    "difficulty breathing",
    "shortness of breath",
    "severe bleeding",
    "bleeding heavily",
    "unconscious",
    "seizure",
    "stroke",
    "slurred speech",
    "suicidal",
    "fainted",
}


def detect_emergency(text: str):
    lowered = (text or "").lower()
    matches = [keyword for keyword in RED_FLAG_KEYWORDS if keyword in lowered]
    return {
        "is_emergency": bool(matches),
        "matches": matches,
    }
