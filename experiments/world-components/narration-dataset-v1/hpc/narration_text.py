# -*- coding: utf-8 -*-
"""One place for how a narrative is turned into tokens and back.

The T5 tokenizer used here loses two things on the round trip:

  "。\\n\\n下"  decodes as  "。 下"      the paragraph break is gone
  "，"          encodes as  [259, 261]  the same ids as ",", so it decodes as ","

Both are fixed outside the model: a paragraph break is written as the marker
"||" (one token, id 2108, survives the round trip) and half-width punctuation
next to Chinese characters is turned back into full-width after decoding.
"""

PARA = "||"

CJK_RANGE = ((0x3000, 0x303F), (0x4E00, 0x9FFF), (0xFF00, 0xFFEF), (0x3400, 0x4DBF))
HALF_TO_FULL = {",": "，", "?": "？", "!": "！", ":": "：", ";": "；", "(": "（", ")": "）"}


def is_cjk(char):
    code = ord(char)
    return any(low <= code <= high for low, high in CJK_RANGE)


def encode_target(text):
    """Text as the model should see it: paragraph breaks become PARA."""
    normalised = text.replace("\r\n", "\n").strip("\n")
    while "\n\n\n" in normalised:
        normalised = normalised.replace("\n\n\n", "\n\n")
    return normalised.replace("\n\n", PARA).replace("\n", " ")


def decode_output(text):
    """Model output as a reader should see it."""
    text = text.replace(PARA, "\n\n").replace("</s>", "").replace("<pad>", "")
    for mark in ("。", "，", "、", "；", "：", "？", "！", "」", "》"):
        text = text.replace(" " + mark, mark)
    for mark in ("「", "《"):
        text = text.replace(mark + " ", mark)
    out = []
    for index, char in enumerate(text):
        if char in HALF_TO_FULL:
            before = text[index - 1] if index else ""
            after = text[index + 1] if index + 1 < len(text) else ""
            if is_cjk(before) or is_cjk(after) or char in "()":
                out.append(HALF_TO_FULL[char])
                continue
        out.append(char)
    text = "".join(out)
    while "  " in text:
        text = text.replace("  ", " ")
    return text.strip()
