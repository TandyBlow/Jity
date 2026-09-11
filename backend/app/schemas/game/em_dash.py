"""Em dash (—) replacement shared by all player-facing text."""

# U+2014 em dash — replaced in all player-facing text
# Chinese 破折号 is "——" (two em dashes together); treat it as one unit → "，"
# Stray single "—" also → "，"
_EM_DASH = "—"
_DOUBLE_EM_DASH = "——"
_EM_DASH_REPLACEMENT = "，"


def replace_em_dash(text: str) -> str:
    """Replace Chinese 破折号 (——) and single em dashes (—) with commas (，) in *text*."""
    if not text:
        return text
    # Replace "——" first so it maps to a single comma, not "，，"
    text = text.replace(_DOUBLE_EM_DASH, _EM_DASH_REPLACEMENT)
    text = text.replace(_EM_DASH, _EM_DASH_REPLACEMENT)
    return text
