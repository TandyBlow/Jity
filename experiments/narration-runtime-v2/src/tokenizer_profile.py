# -*- coding: utf-8 -*-
"""YuYan character-tokenizer profile and OOV / whitespace checks.

The YuYan vocabulary is a character list (`dict.txt`, one entry per line,
followed by a frequency).  It has no ordinary space, tab or newline entry.
The v2 serializer refuses those characters before this check; this module is
the second line of defence and the place where the tokenizer identity is
recorded.

Only the vocabulary file is committed (119,884 bytes).  Weights and
checkpoints stay on the cluster and are referenced by hash in the manifest.
"""

from __future__ import annotations

import hashlib
import io
import os
from typing import Any, Dict, Set

from v2_render import NarrationSerializeError


EXPECTED_YUYAN_DICT_SHA256 = "20287a9d1a2ec9d82b2a13f02c10c7b81e8bb015f114134bca6b06e5c8d376b4"
EXPECTED_YUYAN_VOCAB_SIZE = 13668


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_vocab(path: str) -> Set[str]:
    entries: Set[str] = set()
    with io.open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if not line:
                continue
            entries.add(line.split(" ")[0])
    return entries


def load_tokenizer_profile(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise SystemExit(f"tokenizer dict not found: {path}")
    digest = sha256_file(path)
    vocab = load_vocab(path)
    profile = {
        "name": "yuyan-char-v1",
        "source": "hpc:~/narr_rows/dict.txt",
        "path": "tokenizers/yuyan-v1/dict.txt",
        "sha256": digest,
        "bytes": os.path.getsize(path),
        "vocabSize": len(vocab),
        "specialTokens": [token for token in ("<s>", "<pad>", "</s>", "<unk>", "<end>",
                                               "<mask>", "<sep>", "<hold>")
                          if token in vocab],
        "hasSpaceToken": " " in vocab,
        "hasTabToken": "\t" in vocab,
        "hasNewlineToken": "\n" in vocab,
        "vocab": vocab,
    }
    if os.path.basename(path) == "dict.txt" and digest != EXPECTED_YUYAN_DICT_SHA256:
        raise SystemExit(
            f"tokenizer hash {digest} != registered {EXPECTED_YUYAN_DICT_SHA256}; "
            "do not silently train on a different tokenizer")
    if len(vocab) != EXPECTED_YUYAN_VOCAB_SIZE:
        raise SystemExit(
            f"tokenizer vocab size {len(vocab)} != registered {EXPECTED_YUYAN_VOCAB_SIZE}")
    return profile


def public_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    """The manifest-safe view: no 13k-entry set in JSON."""
    return {key: value for key, value in profile.items() if key != "vocab"}


def validate_tokenizer_text(text: str, profile: Dict[str, Any]) -> None:
    vocab = profile["vocab"]
    if not isinstance(text, str):
        raise NarrationSerializeError("expected_string", "text is not a string", "text")
    for index, char in enumerate(text):
        if char in "\r\n" or char.isspace():
            raise NarrationSerializeError(
                "tokenizer_whitespace",
                f"character U+{ord(char):04X} at index {index} is whitespace and "
                "has no YuYan vocabulary entry",
                f"index {index}")
        if char not in vocab:
            raise NarrationSerializeError(
                "tokenizer_oov",
                f"character {char!r} (U+{ord(char):04X}) at index {index} is not "
                "in the YuYan vocabulary",
                f"index {index}")


def validate_chars(text: str, vocab: Set[str]) -> Dict[str, Any]:
    """Non-raising audit helper used by the checks and goldens."""
    missing = []
    for index, char in enumerate(text):
        if char not in vocab:
            missing.append({"index": index, "char": char, "codepoint": f"U+{ord(char):04X}"})
    return {"ok": not missing, "missing": missing, "chars": len(text)}
