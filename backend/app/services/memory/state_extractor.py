"""A deterministic, LLM-independent state extractor for Chinese narrative text.

This module is deliberately conservative.  It is an LLM-independent NLP
baseline: it uses sentence segmentation, a Chinese dependency parser,
document-level evidence, generic proposition extraction, and optional
domain-specific state projection rules.  A proposition is retained even when
it cannot yet be projected into a persistent state.

The important storage rule is independent of the extraction rules:

* source text is retained as immutable evidence;
* a context frame separates facts that belong to different narrative or
  document scopes;
* a state is addressed by ``(frame, entity, attribute)``;
* a new observation first resolves that address against the existing world
  model;
* a changed value appends a new version to the history;
* an unchanged value creates no duplicate version;
* an unresolved or ambiguous reference remains explicit until later evidence
  resolves it;
* the current world model is the latest version for every scoped address.

The append-only history makes it possible to inspect how the current state was
produced, while ``WorldModel.current_state()`` exposes only the latest state.
"""

import json
import re
import logging
import warnings
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping


_SENTENCE_TERMINATORS = set("。！？!?；")
_QUOTE_PAIRS = {
    "“": "”",
    "‘": "’",
    "「": "」",
    "『": "』",
    "（": "）",
    "(": ")",
    "【": "】",
    "[": "]",
    "《": "》",
}

_HEADING_RE = re.compile(
    r"^(?:(?:序章|楔子|引子|前言|后记|尾声|终章|附录)(?:\s+.*)?|"
    r"第[0-9一二三四五六七八九十百千万零〇两]+[章节回卷部篇](?:\s+.*)?|"
    r"(?:chapter|prologue|epilogue|appendix)\b.*)$",
    re.IGNORECASE,
)
_METADATA_RE = re.compile(
    r"^(?:作者|作者简介|译者|出版社|出版信息|版权|免责声明|声明|来源|网址|链接|ISBN)"
    r"\s*[:：]?\s*.*$",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"^(?:https?://|www\.)\S+$", re.IGNORECASE)
_ATTRIBUTION_RE = re.compile(r"^(?:——|――|—{2,}|--+)\s*[\w\u4e00-\u9fff· .]+$")
_TITLE_RE = re.compile(r"^《[^》]{1,100}》$")
_DEDICATION_RE = re.compile(r"^(?:谨以|特以).*(?:献给|赠给).*[！!。.]?$")
_OPENABLE_SUFFIXES = (
    "门",
    "窗",
    "盒",
    "盒子",
    "箱",
    "箱子",
    "戒指",
    "信封",
    "手机",
    "瓶盖",
    "盖子",
    "眼睛",
    "墙壁",
    "屏幕",
    "电梯",
    "房间",
    "锁",
)
_NON_OPENING_PREFIXES = set("推离展分睁张裂绽揭")

# These are leading subordinate clauses and discourse connectors.  A sentence
# beginning with one of them is treated as lacking an independent subject.
# This implements the user's look-ahead rule for a first sentence such as
# "在你最孤单最无望的时候，有一扇门会在你身边打开。".
_CONTINUATION_PREFIXES = (
    "在",
    "当",
    "如果",
    "只有",
    "只要",
    "因为",
    "由于",
    "虽然",
    "即使",
    "于是",
    "随后",
    "然后",
    "然而",
    "但是",
    "而且",
    "并且",
    "因此",
    "此时",
    "这时",
    "那时",
    "当时",
    "其中",
    "直到",
    "除非",
    "一旦",
    "后来",
    "这么",
    "那么",
    "如此",
    "这样",
    "那样",
    "真",
    "好",
    "鬼扯",
    "喂",
    "唉",
    "哼",
    "忽然",
    "突然",
    "原来",
    "果然",
    "只是",
    "不过",
    "可是",
    "可惜",
    "难道",
    "为什么",
    "怎么",
    "不如",
    "与其",
)

_PERSON_PRONOUNS = {"我", "你", "他", "她", "我们", "你们", "他们", "她们", "自己"}
_OBJECT_PRONOUNS = {"它", "其", "它们"}
_PRONOUNS = _PERSON_PRONOUNS | _OBJECT_PRONOUNS
# A demonstrative object pronoun can be linked to a single recent object.
# First/second-person and human third-person pronouns require discourse
# evidence; recency alone is not enough to turn “你” into “我” or “他” into
# whichever person happened to be mentioned last.
_AUTO_RESOLVE_PRONOUNS = {"它", "其", "它们"}

# Universal Dependencies relations used by the Chinese Stanza model.  The
# segmentation rule needs to know whether the beginning of the sentence is a
# subject phrase; it does not treat every noun at the beginning as a subject.
_SUBJECT_RELATIONS = {"nsubj", "csubj", "nsubj:pass", "csubj:pass"}
_SUBJECT_SPAN_RELATIONS = {
    "amod",
    "clf",
    "compound",
    "det",
    "flat",
    "flat:name",
    "fixed",
    "name",
    "nmod",
    "nummod",
    "mark",
    "case",
}

_PREDICATE_UPOS = {"VERB", "AUX", "ADJ"}
_PREDICATE_RELATIONS = {"root", "advcl", "ccomp", "xcomp", "conj", "acl", "parataxis", "dep"}
_NOMINAL_UPOS = {"NOUN", "PROPN", "PRON"}
_SUBJECT_ARGUMENT_RELATIONS = {"nsubj", "csubj", "nsubj:pass", "csubj:pass"}
_OBJECT_ARGUMENT_RELATIONS = {"obj", "dobj", "obl:patient", "nmod:patient"}
_INDIRECT_ARGUMENT_RELATIONS = {"iobj", "obl:arg"}
_CLAUSE_ARGUMENT_RELATIONS = {"obl", "advcl", "ccomp", "xcomp", "conj"}
_MENTION_RELATIONS = _SUBJECT_ARGUMENT_RELATIONS | _OBJECT_ARGUMENT_RELATIONS | {
    "nmod",
    "obl",
    "obl:arg",
    "obl:patient",
    "nmod:patient",
    "obl:loc",
    "obl:tmod",
    "iobj",
}
_QUESTION_MARKERS = ("吗", "么", "谁", "什么", "哪个", "哪里", "哪儿", "为什么", "怎么", "难道", "是否")
_NEGATION_MARKERS = ("不", "没", "没有", "未", "无", "别", "莫")
_CONDITIONAL_MARKERS = ("如果", "只有", "只要", "当", "在", "除非", "一旦", "之前", "之后", "时")
_PREDICTION_MARKERS = ("会", "将", "要", "可能", "应该", "仍会")
_REPORTING_MARKERS = ("据说", "听说", "传说", "据传", "有人说")
_SPEECH_PREDICATES = {"说", "道", "喊", "呼喊", "呼唤", "叫", "问", "回答", "低语", "喃喃", "嘀咕"}
_TRANSFER_PREDICATES = {"给", "交给", "递给", "送给", "还给", "交还", "归还"}
_OPEN_PREDICATES = {"打开", "开启", "开"}
_CLOSE_PREDICATES = {"关闭", "关上", "合上", "关"}
_PLACE_PREDICATES = {"放", "放置", "摆放", "置于", "放在"}
_ENTER_PREDICATES = {"进入", "走进", "到达", "抵达"}


@dataclass(frozen=True, slots=True)
class StateProjectionRule:
    """A declarative mapping from a proposition to a persistent state value.

    Dependency parsing and state semantics are deliberately separate.  A
    project can add a verb meaning here without changing segmentation,
    reference resolution, or proposition storage.  ``predicates`` contains
    canonical predicate prefixes, while the raw proposition remains attached
    to every emitted ``StateVersion``.
    """

    name: str
    predicates: tuple[str, ...]
    effect: str
    attribute: str | None = None
    value: str | None = None
    entity_role: str | None = None
    value_role: str | None = None
    fallback_entity_roles: tuple[str, ...] = ()
    fallback_value_roles: tuple[str, ...] = ()
    entity_kind: str = "entity"
    state_kind: str = "property"
    allowed_kinds: tuple[str, ...] = ("event", "speech")
    allowed_modalities: tuple[str, ...] = ("asserted",)
    allowed_polarities: tuple[str, ...] = ("affirmed",)
    predicate_suffix_entity: bool = False
    value_is_entity: bool = False
    value_from_predicate: bool = False
    normalize_location_value: bool = False
    normalize_condition_value: bool = False
    confidence: float = 0.8

    def __post_init__(self) -> None:
        if not self.predicates:
            raise ValueError("a state projection rule needs at least one predicate")
        if self.effect not in {"property", "relation"}:
            raise ValueError(f"unsupported state projection effect: {self.effect}")
        if not self.attribute:
            raise ValueError("a state projection rule needs an attribute")


DEFAULT_STATE_PROJECTION_RULES = (
    StateProjectionRule(
        name="transfer_holder",
        predicates=tuple(sorted(_TRANSFER_PREDICATES)),
        effect="relation",
        attribute="holder",
        entity_role="object",
        value_role="indirect_object",
        entity_kind="object",
        state_kind="relation",
        value_is_entity=True,
        confidence=0.95,
    ),
    StateProjectionRule(
        name="open_status",
        predicates=tuple(sorted(_OPEN_PREDICATES)),
        effect="property",
        attribute="status",
        value="已打开",
        entity_role="object",
        fallback_entity_roles=("clause", "subject"),
        entity_kind="object",
        predicate_suffix_entity=True,
        confidence=0.9,
    ),
    StateProjectionRule(
        name="close_status",
        predicates=tuple(sorted(_CLOSE_PREDICATES)),
        effect="property",
        attribute="status",
        value="已关闭",
        entity_role="object",
        fallback_entity_roles=("clause", "subject"),
        entity_kind="object",
        predicate_suffix_entity=True,
        confidence=0.9,
    ),
    StateProjectionRule(
        name="place_location",
        predicates=tuple(sorted(_PLACE_PREDICATES)),
        effect="relation",
        attribute="location",
        entity_role="object",
        value_role="location",
        fallback_entity_roles=("indirect_object", "subject"),
        fallback_value_roles=("indirect_object",),
        entity_kind="object",
        state_kind="relation",
        normalize_location_value=True,
        confidence=0.85,
    ),
    StateProjectionRule(
        name="enter_location",
        predicates=tuple(sorted(_ENTER_PREDICATES)),
        effect="relation",
        attribute="location",
        entity_role="subject",
        value_role="location",
        fallback_value_roles=("object",),
        entity_kind="person",
        state_kind="relation",
        normalize_location_value=True,
        confidence=0.85,
    ),
    StateProjectionRule(
        name="conditional_opening_requirement",
        predicates=tuple(sorted(_OPEN_PREDICATES)),
        effect="property",
        attribute="opening_condition",
        entity_role="subject",
        fallback_entity_roles=("object",),
        value_role="condition",
        entity_kind="object",
        state_kind="rule",
        allowed_kinds=("event", "property"),
        allowed_modalities=("conditional",),
        normalize_condition_value=True,
        confidence=0.85,
    ),
    StateProjectionRule(
        name="conditional_expected_event",
        predicates=tuple(sorted(_OPEN_PREDICATES)),
        effect="property",
        attribute="expected_event",
        entity_role="subject",
        fallback_entity_roles=("object",),
        value_from_predicate=True,
        entity_kind="object",
        state_kind="event",
        allowed_kinds=("event", "property"),
        allowed_modalities=("conditional",),
        confidence=0.85,
    ),
)


def _compatible_entity_kinds(expected_kind: str | None) -> set[str]:
    if expected_kind == "person":
        return {"person", "entity"}
    if expected_kind == "object":
        return {"object", "entity"}
    if expected_kind == "location":
        return {"location", "entity"}
    if expected_kind:
        return {expected_kind}
    return {"person", "object", "location", "entity"}


def _candidate_entities(
    recent_entities: list[str],
    entity_kinds: dict[str, str],
    expected_kind: str | None,
) -> list[str]:
    compatible = _compatible_entity_kinds(expected_kind)
    if expected_kind in {"person", "object", "location"}:
        preferred = [
            entity
            for entity in recent_entities
            if entity_kinds.get(entity, "entity") == expected_kind
        ]
        if preferred:
            return preferred
    return [
        entity
        for entity in recent_entities
        if entity_kinds.get(entity, "entity") in compatible
    ]


def _pronoun_kind(value: str) -> str:
    if value in _PERSON_PRONOUNS:
        return "person"
    if value in _OBJECT_PRONOUNS:
        return "object"
    return "entity"

_DEPENDENCY_PIPELINE: Any | None = None
_DEPENDENCY_PIPELINE_ERROR: str | None = None
DEFAULT_FRAME_ID = "frame:document"


@dataclass(slots=True, frozen=True)
class DependencyToken:
    """One token and its Universal Dependencies analysis."""

    id: int
    text: str
    lemma: str | None
    upos: str | None
    xpos: str | None
    head: int
    relation: str


def _get_dependency_pipeline() -> Any | None:
    """Load the Stanza Chinese dependency pipeline once, on first use.

    The model is intentionally not loaded at module import time.  This keeps
    API startup and unit tests cheap, while the production path uses the real
    parser whenever its model is installed.  ``download_method=None`` makes a
    missing model visible instead of silently downloading it during a game.
    """

    global _DEPENDENCY_PIPELINE, _DEPENDENCY_PIPELINE_ERROR

    if _DEPENDENCY_PIPELINE is not None:
        return _DEPENDENCY_PIPELINE
    if _DEPENDENCY_PIPELINE_ERROR is not None:
        return None

    try:
        import stanza

        _DEPENDENCY_PIPELINE = stanza.Pipeline(
            lang="zh-hans",
            processors="tokenize,pos,lemma,depparse",
            download_method=None,
            use_gpu=False,
            verbose=False,
        )
    except Exception as exc:  # pragma: no cover - depends on local model installation
        _DEPENDENCY_PIPELINE_ERROR = f"{type(exc).__name__}: {exc}"
        return None

    return _DEPENDENCY_PIPELINE


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", "", value).strip()


def _normalize_entity(value: str) -> str:
    """Normalize simple Chinese noun phrases without requiring a tokenizer."""

    value = _clean_text(value)
    value = value.strip("，。！？!?；：:,、\"“”‘’()（）")
    value = re.sub(r"^(?:后来|随后|然后|这时|此时|现在|当时)", "", value)
    value = re.sub(r"^(?:一个|一位|一件|一把|一扇|一只|一枚|这扇|那扇|这把|那把|这个|那个|这只|那只|该|某)", "", value)
    value = re.sub(r"^(我|你|他|她|它)心$", r"\1", value)
    value = re.sub(r"(?:了|着|过)$", "", value)
    return value or "未知实体"


def _normalize_attribute(value: str) -> str:
    value = _clean_text(value)
    value = value.strip("，。！？!?；：:,、\"“”‘’()（）")
    return value or "未命名属性"


def _looks_like_openable_entity(value: str) -> bool:
    normalized = _normalize_entity(value)
    return normalized.endswith(_OPENABLE_SUFFIXES)


def _split_sentences(text: str) -> list[str]:
    """Split sentences without cutting punctuation inside paired quotes."""

    sentences: list[str] = []
    current: list[str] = []
    quote_stack: list[str] = []
    closing_quotes = set(_QUOTE_PAIRS.values())

    def flush() -> None:
        value = "".join(current).strip()
        if value:
            sentences.append(value)
        current.clear()

    for character in text:
        if character in _QUOTE_PAIRS:
            quote_stack.append(_QUOTE_PAIRS[character])
        elif quote_stack and character == quote_stack[-1]:
            quote_stack.pop()
        elif character in closing_quotes and quote_stack:
            # Keep malformed or mixed quote styles from blocking all later
            # sentence boundaries forever.
            quote_stack.pop()

        if character == "\n" and not quote_stack:
            flush()
            continue

        current.append(character)
        if character in _SENTENCE_TERMINATORS and not quote_stack:
            flush()

    flush()
    return sentences


def _split_extraction_units(text: str) -> list[str]:
    """Split a block into parser-sized units without changing block storage.

    ``_split_sentences`` intentionally keeps dialogue and its attribution in
    one memory block.  A dependency parser still needs smaller units: a
    question inside quoted dialogue must not make the following narration a
    question, and a closing quote before an attribution must not make the
    speaker part of the attribution's subject.  This second pass therefore
    splits on terminal punctuation and completed quoted utterances while the
    original block remains unchanged in the evidence store.
    """

    units: list[str] = []
    current: list[str] = []
    quote_stack: list[str] = []
    closing_quotes = set(_QUOTE_PAIRS.values())
    pending_terminal = False

    def flush() -> None:
        nonlocal pending_terminal
        value = "".join(current).strip()
        if value:
            units.append(value)
        current.clear()
        pending_terminal = False

    for character in text:
        if character in _QUOTE_PAIRS and not quote_stack and current:
            flush()
        if pending_terminal and character not in closing_quotes and not character.isspace():
            flush()

        current.append(character)
        if character in _QUOTE_PAIRS:
            quote_stack.append(_QUOTE_PAIRS[character])
        elif quote_stack and character == quote_stack[-1]:
            quote_stack.pop()
            if not quote_stack:
                flush()
                continue
        elif character in closing_quotes and quote_stack:
            quote_stack.pop()
            if not quote_stack:
                flush()
                continue

        if character in _SENTENCE_TERMINATORS:
            pending_terminal = True
        elif character == "\n" and not quote_stack:
            flush()

    flush()
    return units


@dataclass(slots=True)
class SentenceStartAnalysis:
    """NLP evidence used to decide whether a sentence starts a new block."""

    sentence: str
    first_token: str | None
    first_pos: str | None
    subject: str | None
    has_subject: bool
    reason: str
    dependency_relation: str | None = None
    dependency_head: int | None = None
    parser: str = "fallback"
    tokens: tuple[DependencyToken, ...] = ()


def parse_dependencies(sentence: str, *, pipeline: Any | None = None) -> tuple[DependencyToken, ...]:
    """Return the first sentence's Universal Dependencies parse.

    ``segment_text`` has already made the sentence boundary decision. The
    parser is therefore called for one sentence at a time. An empty tuple
    means that the model is unavailable, so callers can choose an explicit
    degraded fallback.
    """

    stripped = sentence.strip()
    if not stripped:
        return ()

    active_pipeline = pipeline if pipeline is not None else _get_dependency_pipeline()
    if active_pipeline is None:
        return ()

    try:
        document = active_pipeline(stripped)
        parsed_sentences = getattr(document, "sentences", ())
        if not parsed_sentences:
            return ()
        parsed_sentence = parsed_sentences[0]
        parsed_tokens: list[DependencyToken] = []
        for word in getattr(parsed_sentence, "words", ()):
            raw_id = getattr(word, "id", None)
            if isinstance(raw_id, (tuple, list)):
                raw_id = raw_id[0]
            try:
                token_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            parsed_tokens.append(
                DependencyToken(
                    id=token_id,
                    text=str(getattr(word, "text", "")),
                    lemma=getattr(word, "lemma", None),
                    upos=getattr(word, "upos", None),
                    xpos=getattr(word, "xpos", None),
                    head=int(getattr(word, "head", 0) or 0),
                    relation=str(getattr(word, "deprel", "")),
                )
            )
        return tuple(parsed_tokens)
    except Exception:  # pragma: no cover - parser/model failures depend on runtime
        return ()


def _is_subject_relation(relation: str) -> bool:
    return relation in _SUBJECT_RELATIONS


def _subject_span(tokens: tuple[DependencyToken, ...], head_id: int) -> set[int]:
    """Find the nominal modifiers that belong to a dependency subject."""

    span = {head_id}
    changed = True
    while changed:
        changed = False
        for token in tokens:
            if token.head in span and token.id not in span and token.relation in _SUBJECT_SPAN_RELATIONS:
                span.add(token.id)
                changed = True
    return span


def _subject_text(tokens: tuple[DependencyToken, ...], span: set[int], head_id: int) -> str:
    value = "".join(token.text for token in tokens if token.id in span)
    if value:
        return value
    return next((token.text for token in tokens if token.id == head_id), "")


def _dependency_children(tokens: tuple[DependencyToken, ...]) -> dict[int, list[DependencyToken]]:
    children: dict[int, list[DependencyToken]] = {}
    for token in tokens:
        children.setdefault(token.head, []).append(token)
    return children


def _dependency_subtree(
    tokens: tuple[DependencyToken, ...],
    root_id: int,
    *,
    include_punctuation: bool = False,
) -> set[int]:
    """Return a dependency subtree without assuming a particular vocabulary."""

    children = _dependency_children(tokens)
    result: set[int] = set()
    pending = [root_id]
    while pending:
        token_id = pending.pop()
        if token_id in result:
            continue
        token = next((item for item in tokens if item.id == token_id), None)
        if token is None:
            continue
        if include_punctuation or token.upos != "PUNCT":
            result.add(token_id)
        pending.extend(child.id for child in children.get(token_id, ()))
    return result


def _dependency_text(tokens: tuple[DependencyToken, ...], token_ids: set[int]) -> str:
    return "".join(token.text for token in tokens if token.id in token_ids).strip()


def _lexical_fragment_span(
    sentence: str,
    tokens: tuple[DependencyToken, ...],
    token: DependencyToken,
    lexical_spans: tuple[tuple[str, int, int], ...],
) -> tuple[int, int] | None:
    """Return the lexeme that contains a parser token only partially.

    Chinese dependency tokenizers sometimes split ``穿越`` into ``穿`` and
    ``越``-prefixed argument material.  The parser evidence is retained, but
    the overlapping characters must not be copied into the argument as well.
    """

    token_span = _token_surface_spans(sentence, tokens).get(token.id)
    if not token_span:
        return None
    token_start, token_end = token_span
    for _, word_start, word_end in lexical_spans:
        if word_start <= token_start < word_end and word_end > token_end:
            return word_start, word_end
    return None


def _dependency_text_excluding_span(
    sentence: str,
    tokens: tuple[DependencyToken, ...],
    token_ids: set[int],
    excluded_span: tuple[int, int] | None,
) -> tuple[str, bool]:
    """Build dependency text while removing an overlapping predicate lexeme."""

    if excluded_span is None:
        return _dependency_text(tokens, token_ids), False

    token_spans = _token_surface_spans(sentence, tokens)
    parts: list[str] = []
    changed = False
    excluded_start, excluded_end = excluded_span
    for token in tokens:
        if token.id not in token_ids:
            continue
        token_span = token_spans.get(token.id)
        if token_span is None:
            parts.append(token.text)
            continue
        start, end = token_span
        overlap_start = max(start, excluded_start)
        overlap_end = min(end, excluded_end)
        if overlap_start < overlap_end:
            changed = True
            if start < overlap_start:
                parts.append(sentence[start:overlap_start])
            if overlap_end < end:
                parts.append(sentence[overlap_end:end])
        else:
            parts.append(sentence[start:end])
    value = "".join(parts).strip()
    return value or _dependency_text(tokens, token_ids), changed


def _configured_predicate_lexemes() -> tuple[str, ...]:
    configured = {
        predicate
        for rule in DEFAULT_STATE_PROJECTION_RULES
        for predicate in rule.predicates
    }
    return tuple(
        sorted(
            configured | _SPEECH_PREDICATES,
            key=len,
            reverse=True,
        )
    )


def _surface_predicate_candidate(
    sentence: str,
    tokens: tuple[DependencyToken, ...],
    token: DependencyToken,
    lexical_spans: tuple[tuple[str, int, int], ...],
) -> tuple[str, tuple[int, int] | None]:
    """Align a parser token with a visible predicate word when possible."""

    token_span = _token_surface_spans(sentence, tokens).get(token.id)
    if token_span is None:
        return token.lemma or token.text, None
    token_start, token_end = token_span

    for negative_prefix in ("没有", "没", "不", "未", "无"):
        if token.text.startswith(negative_prefix) and token.lemma and token.lemma != token.text:
            predicate_start = token_start + len(negative_prefix)
            if sentence.startswith(token.lemma, predicate_start):
                return token.lemma, (predicate_start, predicate_start + len(token.lemma))

    for candidate in _configured_predicate_lexemes():
        if sentence.startswith(candidate, token_start):
            return candidate, (token_start, token_start + len(candidate))

    if token.relation == "root" and len(token.text) > 1:
        if token.text.endswith(("吧", "啊", "呢", "啦")):
            base = token.text[:-1]
            if base:
                token_span_end = token_end - 1
                return base, (token_start, token_span_end)
        return token.lemma or token.text, None

    for word, word_start, word_end in lexical_spans:
        if word_start == token_start and word_end > word_start:
            if word_end <= token_end or token.text.startswith(word) or word.startswith(token.text):
                return word, (word_start, word_end)

    return token.lemma or token.text, None


def _surface_argument_after(
    sentence: str,
    predicate_span: tuple[int, int] | None,
) -> str:
    if predicate_span is None:
        return ""
    _, predicate_end = predicate_span
    remainder = sentence[predicate_end:]
    remainder = re.split(r"[，,。！？!?；;\n]", remainder, maxsplit=1)[0]
    remainder = remainder.strip(" \t\u3000\"\“\”'‘’（）()")
    remainder = re.sub(r"^[了着过啦啊呢吧]+|[了着过啦啊呢吧]+$", "", remainder)
    return remainder.strip()


def _negative_token(token: DependencyToken) -> bool:
    text = token.text or ""
    return text in _NEGATION_MARKERS or text.startswith(("不", "没", "未", "无"))


def _negative_marker_token(token: DependencyToken) -> bool:
    return (token.text or "") in {"不", "没", "没有", "未", "无", "别", "莫"}


def _predicate_is_negated(
    tokens: tuple[DependencyToken, ...],
    predicate_token: DependencyToken,
) -> bool:
    """Detect negation attached to this predicate, not to its whole sentence."""

    children = _dependency_children(tokens)
    if _negative_token(predicate_token) and predicate_token.text not in {"不如"}:
        return True
    for child in children.get(predicate_token.id, ()):
        if child.relation in {"neg", "advmod", "aux", "mark"} and _negative_token(child):
            return True

    by_id = {token.id: token for token in tokens}
    current = predicate_token
    visited: set[int] = set()
    while current.head and current.head not in visited:
        visited.add(current.head)
        parent = by_id.get(current.head)
        if parent is None:
            break
        if _negative_marker_token(parent) and parent.text not in {predicate_token.text}:
            return True
        current = parent
    return False


def _token_surface_spans(sentence: str, tokens: tuple[DependencyToken, ...]) -> dict[int, tuple[int, int]]:
    """Find character spans for parser tokens when the parser gives no offsets."""

    spans: dict[int, tuple[int, int]] = {}
    cursor = 0
    for token in tokens:
        start = sentence.find(token.text, cursor)
        if start < 0:
            continue
        end = start + len(token.text)
        spans[token.id] = (start, end)
        cursor = end
    return spans


def _lexical_word_spans(sentence: str) -> tuple[tuple[str, int, int], ...]:
    """Use an optional non-LLM word segmenter only for surface normalization."""

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import jieba

        jieba.setLogLevel(logging.ERROR)
        return tuple(
            (word, start, end)
            for word, start, end in jieba.tokenize(sentence, mode="default")
            if word.strip()
        )
    except Exception:  # pragma: no cover - optional tokenizer is environment-dependent
        return ()


def _is_internal_lexical_fragment(
    sentence: str,
    tokens: tuple[DependencyToken, ...],
    token: DependencyToken,
    lexical_spans: tuple[tuple[str, int, int], ...],
) -> bool:
    token_span = _token_surface_spans(sentence, tokens).get(token.id)
    if not token_span:
        return False
    token_start, _ = token_span
    return any(word_start < token_start < word_end for _, word_start, word_end in lexical_spans)


def _normalize_predicate_surface(
    sentence: str,
    tokens: tuple[DependencyToken, ...],
    token: DependencyToken,
    lexical_spans: tuple[tuple[str, int, int], ...] = (),
) -> tuple[str, str, tuple[str, ...]]:
    """Repair common token fragments while preserving the parser's evidence."""

    surface = token.text
    normalized = token.lemma or surface
    diagnostics: list[str] = []
    lexical_spans = lexical_spans or _lexical_word_spans(sentence)
    candidate, candidate_span = _surface_predicate_candidate(
        sentence,
        tokens,
        token,
        lexical_spans,
    )
    if candidate != surface:
        normalized = candidate
        diagnostics.append("predicate_token_fragment")
    if token.relation not in _PREDICATE_RELATIONS:
        diagnostics.append(f"predicate_relation:{token.relation}")
    if not any(child.relation in _SUBJECT_ARGUMENT_RELATIONS for child in _dependency_children(tokens).get(token.id, ())):
        diagnostics.append("implicit_or_unresolved_subject")
    return normalized, surface, tuple(dict.fromkeys(diagnostics))


def _argument_role(token: DependencyToken) -> str | None:
    relation = token.relation
    if relation in _SUBJECT_ARGUMENT_RELATIONS:
        return "subject"
    if relation in _OBJECT_ARGUMENT_RELATIONS:
        return "object"
    if relation in _INDIRECT_ARGUMENT_RELATIONS:
        return "indirect_object"
    if relation in {"obl:loc"}:
        return "location"
    if relation in {"obl:tmod"}:
        return "time"
    if relation in {"obl", "advcl"}:
        return "oblique"
    if relation in {"ccomp", "xcomp"}:
        return "clause"
    if relation == "conj":
        return "conjunct"
    if relation in {"advmod", "amod", "nmod"}:
        return "modifier"
    if relation == "neg":
        return "negation"
    if relation in {"aux", "mark"}:
        return "grammatical_marker"
    return None


def _is_vocative_subject(
    tokens: tuple[DependencyToken, ...],
    candidate: DependencyToken,
    predicate: DependencyToken,
) -> bool:
    """Recognize a noun before a comma as a vocative for existential clauses."""

    spans = _token_surface_spans("".join(token.text for token in tokens), tokens)
    candidate_ids = _dependency_subtree(tokens, candidate.id)
    candidate_spans = [spans[token_id] for token_id in candidate_ids if token_id in spans]
    predicate_span = spans.get(predicate.id)
    if not candidate_spans or predicate_span is None:
        return False
    candidate_end = max(end for _, end in candidate_spans)
    predicate_start = predicate_span[0]
    return any(
        token.upos == "PUNCT"
        and token.text in {"，", ",", "：", ":"}
        and spans.get(token.id, (0, 0))[0] >= candidate_end
        and spans.get(token.id, (0, 0))[1] <= predicate_start
        for token in tokens
    )


def _inherited_subject(
    tokens: tuple[DependencyToken, ...],
    predicate: DependencyToken,
) -> tuple[str, DependencyToken] | None:
    """Inherit a clear subject from a nearby adverbial predicate head."""

    if predicate.relation not in {"advcl", "ccomp", "xcomp", "conj"}:
        return None
    by_id = {token.id: token for token in tokens}
    children = _dependency_children(tokens)
    current = predicate
    visited: set[int] = set()
    while current.head and current.head not in visited:
        visited.add(current.head)
        parent = by_id.get(current.head)
        if parent is None:
            break
        subject = next(
            (child for child in children.get(parent.id, ()) if _is_subject_relation(child.relation)),
            None,
        )
        if subject is not None:
            span = _subject_span(tokens, subject.id)
            return _subject_text(tokens, span, subject.id), subject
        if current.relation not in {"advcl", "ccomp", "xcomp", "conj", "parataxis"}:
            break
        current = parent
    return None


def _is_governing_existential(
    token: DependencyToken,
    children: dict[int, list[DependencyToken]],
) -> bool:
    """Avoid emitting a phantom ``有`` when it only introduces a clause."""

    return token.text in {"有", "没有"} and any(
        child.relation in {"ccomp", "xcomp"} and child.upos in _PREDICATE_UPOS
        for child in children.get(token.id, ())
    )


def _fallback_start_analysis(sentence: str) -> SentenceStartAnalysis:
    stripped = sentence.lstrip()
    if not stripped:
        return SentenceStartAnalysis(sentence, None, None, None, False, "empty sentence", parser="fallback")
    if stripped[0] in _QUOTE_PAIRS:
        return SentenceStartAnalysis(
            sentence,
            stripped[0],
            "quote",
            None,
            True,
            "quoted dialogue is a standalone unit",
            parser="quote-aware",
        )

    for prefix in sorted(_CONTINUATION_PREFIXES, key=len, reverse=True):
        if stripped.startswith(prefix):
            return SentenceStartAnalysis(
                sentence,
                prefix,
                "connector",
                None,
                False,
                "known non-subject connector",
                parser="fallback",
            )

    first_token = stripped[0]
    if first_token in "我你他她它其谁这那哪":
        return SentenceStartAnalysis(
            sentence,
            first_token,
            "pronoun",
            first_token,
            True,
            "pronoun subject candidate",
            parser="fallback",
        )
    return SentenceStartAnalysis(
        sentence,
        first_token,
        "unknown",
        first_token,
        True,
        "conservative subject candidate",
        parser="fallback",
    )


def analyze_sentence_start(sentence: str, *, pipeline: Any | None = None) -> SentenceStartAnalysis:
    """Use Chinese dependency syntax to decide whether a sentence starts with a subject.

    A sentence starts a new block when the first lexical token begins a
    dependency subject phrase. The phrase may contain multiple tokens, such
    as ``楚子航`` or ``一扇门``; checking only the first token would incorrectly
    reject those subjects. If Stanza is unavailable, a clearly labelled
    lexical fallback keeps the rest of the extractor usable.
    """

    stripped = sentence.lstrip()
    if not stripped:
        return SentenceStartAnalysis(sentence, None, None, None, False, "empty sentence", parser="fallback")
    if stripped[0] in _QUOTE_PAIRS:
        return SentenceStartAnalysis(
            sentence,
            stripped[0],
            "quote",
            None,
            True,
            "quoted dialogue is a standalone unit",
            parser="quote-aware",
        )

    tokens = parse_dependencies(sentence, pipeline=pipeline)
    if not tokens:
        return _fallback_start_analysis(sentence)

    lexical_tokens = [token for token in tokens if token.upos != "PUNCT" and token.text.strip()]
    if not lexical_tokens:
        return SentenceStartAnalysis(
            sentence,
            None,
            None,
            None,
            False,
            "no lexical token",
            parser="stanza",
            tokens=tokens,
        )

    first = lexical_tokens[0]
    subject_candidates = [
        token
        for token in tokens
        if _is_subject_relation(token.relation)
        and first.id in _subject_span(tokens, token.id)
    ]
    if subject_candidates:
        subject_head = subject_candidates[0]
        span = _subject_span(tokens, subject_head.id)
        return SentenceStartAnalysis(
            sentence,
            first.text,
            first.upos,
            _subject_text(tokens, span, subject_head.id),
            True,
            "dependency subject phrase begins at first lexical token",
            dependency_relation=subject_head.relation,
            dependency_head=subject_head.head,
            parser="stanza",
            tokens=tokens,
        )

    # A verbless or nominal utterance such as "哥哥？" is represented by the
    # parser as a nominal root rather than an nsubj. Treating that root as a
    # standalone subject preserves the block rule for such dialogue.
    if first.head == 0 and first.upos in {"NOUN", "PROPN", "PRON"}:
        return SentenceStartAnalysis(
            sentence,
            first.text,
            first.upos,
            first.text,
            True,
            "nominal root is the sentence's standalone subject",
            dependency_relation=first.relation,
            dependency_head=first.head,
            parser="stanza",
            tokens=tokens,
        )

    return SentenceStartAnalysis(
        sentence,
        first.text,
        first.upos,
        None,
        False,
        "first lexical token does not begin a dependency subject phrase",
        dependency_relation=first.relation,
        dependency_head=first.head,
        parser="stanza",
        tokens=tokens,
    )


@dataclass(slots=True)
class DocumentStructure:
    """A structural marker retained outside the prose state stream.

    A heading, title, or similar marker can define context without becoming a
    world fact.  The extractor keeps it so later state records can refer to
    the context in which they were observed.
    """

    structure_id: str
    text: str
    role: str
    source_line_index: int
    level: int | None = None


@dataclass(slots=True)
class DocumentContentLine:
    """A retained content line and the structure active when it occurred."""

    source_line_index: int
    text: str
    structure_id: str | None = None


@dataclass(slots=True)
class DocumentLineDecision:
    """The cleaning decision for one source line."""

    index: int
    text: str
    role: str
    confidence: float
    included: bool
    reason: str


@dataclass(slots=True)
class DocumentCleaningResult:
    """The filtered view and the audit trail behind it.

    ``raw_text`` is retained so filtering never destroys the original input.
    """

    raw_text: str
    text: str
    decisions: list[DocumentLineDecision]
    structures: list[DocumentStructure] = field(default_factory=list)
    content_lines: list[DocumentContentLine] = field(default_factory=list)

    @property
    def removed_lines(self) -> list[DocumentLineDecision]:
        return [decision for decision in self.decisions if not decision.included]


def _classify_line(line: str, index: int, first_nonempty_index: int | None) -> tuple[str, float, str]:
    """Classify a line using structural evidence only.

    The function intentionally avoids deciding that an ordinary prose line is
    useless.  A line is classified as a title only near the start of a
    document; the same form later in the document may be content.
    """

    if not line:
        return "blank", 1.0, "empty line"
    if line.startswith("\ufeff"):
        return "formatting", 1.0, "byte-order mark"
    if _HEADING_RE.fullmatch(line):
        return "heading", 0.98, "structural heading pattern"
    if _METADATA_RE.fullmatch(line) or _URL_RE.fullmatch(line):
        return "metadata", 0.98, "explicit metadata pattern"
    if _ATTRIBUTION_RE.fullmatch(line):
        return "attribution", 0.95, "standalone attribution pattern"
    if _DEDICATION_RE.fullmatch(line):
        return "dedication", 0.9, "dedication pattern"
    if first_nonempty_index is not None and index <= first_nonempty_index + 2 and _TITLE_RE.fullmatch(line):
        return "title", 0.95, "standalone title near document start"
    return "content", 0.5, "no high-confidence structural marker"


def clean_document_text(text: str) -> DocumentCleaningResult:
    """Create a conservative, auditable content view for arbitrary text.

    The cleaner does not assume the input is a novel.  It removes explicit
    metadata and structural headings in any document.  It removes a prose
    preamble before the first heading only when that region also contains a
    strong dedication/attribution signal, as in a book epigraph.  Otherwise
    ordinary pre-heading prose remains included.
    """

    raw_text = text
    raw_lines = text.replace("\ufeff", "").splitlines()
    normalized_lines = [line.strip(" \\t\u3000") for line in raw_lines]
    nonempty_indices = [index for index, line in enumerate(normalized_lines) if line]
    first_nonempty_index = nonempty_indices[0] if nonempty_indices else None

    preliminary: list[tuple[str, float, str]] = [
        _classify_line(line, index, first_nonempty_index)
        for index, line in enumerate(normalized_lines)
    ]
    structures: list[DocumentStructure] = []
    structure_by_line: dict[int, str] = {}
    for index, (role, _, _) in enumerate(preliminary):
        if role not in {"heading", "title"}:
            continue
        structure_id = f"structure:{len(structures)}"
        structures.append(
            DocumentStructure(
                structure_id=structure_id,
                text=normalized_lines[index],
                role=role,
                source_line_index=index,
                level=1,
            )
        )
        structure_by_line[index] = structure_id

    heading_indices = [index for index, (role, _, _) in enumerate(preliminary) if role == "heading"]
    first_heading_index = heading_indices[0] if heading_indices else None

    # A prose preamble is only discarded when its surrounding structure proves
    # that it is front matter: an attribution or dedication appears before the
    # first heading.  Without that evidence, pre-heading prose is retained.
    pre_heading_roles = (
        {role for role, _, _ in preliminary[:first_heading_index]}
        if first_heading_index is not None
        else set()
    )
    has_epigraph_structure = bool(
        first_heading_index is not None
        and pre_heading_roles.intersection({"attribution", "dedication"})
    )

    decisions: list[DocumentLineDecision] = []
    kept_lines: list[str] = []
    content_lines: list[DocumentContentLine] = []
    current_structure_id: str | None = None
    for index, line in enumerate(normalized_lines):
        role, confidence, reason = preliminary[index]
        included = True

        if index in structure_by_line:
            current_structure_id = structure_by_line[index]

        if role == "blank":
            included = False
        elif role in {"heading", "metadata", "attribution", "dedication", "title", "formatting"}:
            included = False
        elif has_epigraph_structure and first_heading_index is not None and index < first_heading_index:
            role = "preamble"
            confidence = 0.85
            reason = "content before first heading in a dedication/attribution preamble"
            included = False

        decisions.append(
            DocumentLineDecision(
                index=index,
                text=line,
                role=role,
                confidence=confidence,
                included=included,
                reason=reason,
            )
        )
        if included:
            kept_lines.append(line)
            content_lines.append(
                DocumentContentLine(
                    source_line_index=index,
                    text=line,
                    structure_id=current_structure_id,
                )
            )

    return DocumentCleaningResult(
        raw_text=raw_text,
        text="\n".join(kept_lines),
        decisions=decisions,
        structures=structures,
        content_lines=content_lines,
    )


@dataclass(slots=True)
class SegmentedBlock:
    """A block with the source lines and structural context it came from."""

    index: int
    text: str
    source_line_indices: tuple[int, ...] = ()
    structure_id: str | None = None


def _add_source_line(block: SegmentedBlock, source_line_index: int | None) -> None:
    if source_line_index is None or source_line_index in block.source_line_indices:
        return
    block.source_line_indices = (*block.source_line_indices, source_line_index)


def _segment_items(
    items: list[tuple[str, int | None, str | None]],
    *,
    pipeline: Any | None = None,
    respect_structure_boundaries: bool = False,
    max_blocks: int | None = None,
) -> list[SegmentedBlock]:
    blocks: list[SegmentedBlock] = []
    pending: list[str] = []
    pending_lines: list[int] = []
    pending_structure_id: str | None = None
    active_structure_marker = object()
    active_structure: object | str | None = active_structure_marker

    def flush_pending() -> None:
        nonlocal pending, pending_lines, pending_structure_id
        if not pending:
            return
        if max_blocks is not None and len(blocks) >= max_blocks:
            return
        blocks.append(
            SegmentedBlock(
                index=len(blocks),
                text="".join(pending),
                source_line_indices=tuple(dict.fromkeys(pending_lines)),
                structure_id=pending_structure_id,
            )
        )
        pending = []
        pending_lines = []
        pending_structure_id = None

    for sentence, source_line_index, structure_id in items:
        if max_blocks is not None and len(blocks) >= max_blocks:
            break
        structure_changed = bool(
            respect_structure_boundaries
            and active_structure is not active_structure_marker
            and structure_id != active_structure
        )
        if respect_structure_boundaries and (
            active_structure is active_structure_marker or structure_changed
        ):
            flush_pending()
            active_structure = structure_id

        analysis = analyze_sentence_start(sentence, pipeline=pipeline)
        is_continuation = not analysis.has_subject

        if is_continuation:
            if blocks and not structure_changed:
                blocks[-1].text += sentence
                _add_source_line(blocks[-1], source_line_index)
            else:
                pending.append(sentence)
                if source_line_index is not None:
                    pending_lines.append(source_line_index)
                if pending_structure_id is None:
                    pending_structure_id = structure_id
            continue

        if pending:
            pending.append(sentence)
            if source_line_index is not None:
                pending_lines.append(source_line_index)
            blocks.append(
                SegmentedBlock(
                    index=len(blocks),
                    text="".join(pending),
                    source_line_indices=tuple(dict.fromkeys(pending_lines)),
                    structure_id=structure_id,
                )
            )
            pending = []
            pending_lines = []
            pending_structure_id = None
        else:
            blocks.append(
                SegmentedBlock(
                    index=len(blocks),
                    text=sentence,
                    source_line_indices=()
                    if source_line_index is None
                    else (source_line_index,),
                    structure_id=structure_id,
                )
            )

    flush_pending()
    return blocks


def segment_text(
    text: str,
    *,
    pipeline: Any | None = None,
    max_blocks: int | None = None,
) -> list[str]:
    """Split text into blocks according to the sentence-start subject rule."""

    items = [(sentence, None, None) for sentence in _split_sentences(text)]
    return [
        block.text
        for block in _segment_items(
            items,
            pipeline=pipeline,
            max_blocks=max_blocks,
        )
    ]


def segment_document(
    cleaning: DocumentCleaningResult,
    *,
    pipeline: Any | None = None,
    max_blocks: int | None = None,
) -> list[SegmentedBlock]:
    """Segment cleaned content while preserving document structure context."""

    items: list[tuple[str, int | None, str | None]] = []
    content_lines = cleaning.content_lines or [
        DocumentContentLine(source_line_index=index, text=line)
        for index, line in enumerate(cleaning.text.splitlines())
        if line
    ]
    for line in content_lines:
        items.extend(
            (sentence, line.source_line_index, line.structure_id)
            for sentence in _split_sentences(line.text)
        )
    return _segment_items(
        items,
        pipeline=pipeline,
        respect_structure_boundaries=True,
        max_blocks=max_blocks,
    )


@dataclass(slots=True)
class EvidenceRecord:
    """An immutable text observation from which derived data was extracted."""

    evidence_id: str
    document_id: str
    block_index: int
    text: str
    frame_id: str
    source_line_indices: tuple[int, ...] = ()
    kind: str = "content"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PropositionRecord:
    """A generic linguistic fact or event extracted from one sentence.

    This is the loss-preserving layer between NLP and the current world
    state.  ``subject`` and ``arguments`` contain the text seen in the
    sentence; ``entity_ids`` contains the current resolution chosen by the
    world model.  A proposition can remain a question, conditional, report,
    or unresolved observation instead of being asserted as a world fact.
    """

    proposition_id: str
    block_index: int
    sentence_index: int
    source_text: str
    predicate: str
    kind: str
    surface_predicate: str | None = None
    subject: str | None = None
    arguments: dict[str, str] = field(default_factory=dict)
    raw_arguments: dict[str, str] = field(default_factory=dict)
    entity_ids: dict[str, str] = field(default_factory=dict)
    mention_ids: dict[str, str] = field(default_factory=dict)
    polarity: str = "affirmed"
    modality: str = "asserted"
    frame_id: str = DEFAULT_FRAME_ID
    evidence_id: str | None = None
    document_id: str = "document"
    parser: str = "fallback"
    confidence: float = 1.0
    diagnostics: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ContextFrameVersion:
    """One append-only interpretation of a document context."""

    frame_id: str
    label: str | None
    kind: str
    status: str
    block_index: int
    source_text: str
    attributes: dict[str, str] = field(default_factory=dict)
    parent_frame_id: str | None = None
    document_id: str = "document"
    evidence_id: str | None = None
    confidence: float = 1.0
    previous_version_id: str | None = None
    version_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EntityMention:
    """A mention whose identity may remain unresolved or ambiguous."""

    mention_id: str
    text: str
    entity_id: str
    block_index: int
    source_text: str
    frame_id: str
    resolution_status: str
    candidates: tuple[str, ...] = ()
    evidence_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EntityResolutionVersion:
    """An append-only later resolution of an earlier entity mention."""

    mention_id: str
    entity_id: str
    status: str
    block_index: int
    source_text: str
    evidence_id: str | None = None
    version_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StateVersion:
    """One observed version of an entity attribute."""

    entity: str
    attribute: str
    value: str
    block_index: int
    source_text: str
    mode: str = "asserted"
    kind: str = "property"
    confidence: float = 1.0
    previous_value: str | None = None
    frame_id: str = DEFAULT_FRAME_ID
    evidence_id: str | None = None
    epistemic_status: str = "asserted"
    document_id: str = "document"
    mention_id: str | None = None
    supersedes_version_id: str | None = None
    version_id: str = ""
    proposition_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class WorldModel:
    """Append-only evidence, context, entity, and state histories."""

    history: list[StateVersion] = field(default_factory=list)
    aliases: dict[str, str] = field(default_factory=dict)
    entity_kinds: dict[str, str] = field(default_factory=dict)
    _recent_entities: list[str] = field(default_factory=list)
    _recent_entities_by_frame: dict[str, list[str]] = field(default_factory=dict)
    evidence: list[EvidenceRecord] = field(default_factory=list)
    propositions: list[PropositionRecord] = field(default_factory=list)
    frame_history: list[ContextFrameVersion] = field(default_factory=list)
    mentions: list[EntityMention] = field(default_factory=list)
    resolution_history: list[EntityResolutionVersion] = field(default_factory=list)

    def next_block_index(self) -> int:
        """Return the next monotonic block index for incremental extraction."""

        indexes = [
            item.block_index
            for item in (*self.history, *self.evidence, *self.frame_history)
            if item.block_index >= 0
        ]
        return max(indexes, default=-1) + 1

    def record_evidence(
        self,
        *,
        document_id: str,
        block_index: int,
        text: str,
        frame_id: str = DEFAULT_FRAME_ID,
        source_line_indices: tuple[int, ...] = (),
        kind: str = "content",
        metadata: dict[str, Any] | None = None,
        evidence_id: str | None = None,
    ) -> EvidenceRecord:
        record = EvidenceRecord(
            evidence_id=evidence_id or f"evidence:{len(self.evidence)}",
            document_id=document_id,
            block_index=block_index,
            text=text,
            frame_id=frame_id,
            source_line_indices=source_line_indices,
            kind=kind,
            metadata=dict(metadata or {}),
        )
        self.evidence.append(record)
        return record

    def record_proposition(self, proposition: PropositionRecord) -> PropositionRecord:
        """Append a derived linguistic fact without collapsing it into state."""

        self.propositions.append(proposition)
        return proposition

    def to_dict(self) -> dict[str, Any]:
        """Serialize the complete append-only model for durable storage.

        The current state is intentionally not stored as a second authority;
        it is reconstructed from ``history`` after loading.  Evidence,
        propositions, mentions, and resolution history are included so a
        later reference correction remains auditable.
        """

        return {
            "history": [item.to_dict() for item in self.history],
            "aliases": dict(self.aliases),
            "entity_kinds": dict(self.entity_kinds),
            "_recent_entities": list(self._recent_entities),
            "_recent_entities_by_frame": {
                frame_id: list(entities)
                for frame_id, entities in self._recent_entities_by_frame.items()
            },
            "evidence": [item.to_dict() for item in self.evidence],
            "propositions": [item.to_dict() for item in self.propositions],
            "frame_history": [item.to_dict() for item in self.frame_history],
            "mentions": [item.to_dict() for item in self.mentions],
            "resolution_history": [item.to_dict() for item in self.resolution_history],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WorldModel":
        """Restore a model serialized by ``to_dict``.

        Missing collections are treated as empty to allow loading an older
        snapshot that predates one of the audit layers.
        """

        def records(name: str) -> list[dict[str, Any]]:
            values = data.get(name, [])
            return [dict(value) for value in values]

        return cls(
            history=[StateVersion(**item) for item in records("history")],
            aliases=dict(data.get("aliases", {})),
            entity_kinds=dict(data.get("entity_kinds", {})),
            _recent_entities=list(data.get("_recent_entities", [])),
            _recent_entities_by_frame={
                frame_id: list(entities)
                for frame_id, entities in dict(
                    data.get("_recent_entities_by_frame", {})
                ).items()
            },
            evidence=[
                EvidenceRecord(
                    **{
                        **item,
                        "source_line_indices": tuple(item.get("source_line_indices", ())),
                    }
                )
                for item in records("evidence")
            ],
            propositions=[
                PropositionRecord(
                    **{
                        **item,
                        "arguments": dict(item.get("arguments", {})),
                        "raw_arguments": dict(item.get("raw_arguments", {})),
                        "entity_ids": dict(item.get("entity_ids", {})),
                        "mention_ids": dict(item.get("mention_ids", {})),
                        "diagnostics": tuple(item.get("diagnostics", ())),
                    }
                )
                for item in records("propositions")
            ],
            frame_history=[
                ContextFrameVersion(
                    **{
                        **item,
                        "attributes": dict(item.get("attributes", {})),
                    }
                )
                for item in records("frame_history")
            ],
            mentions=[
                EntityMention(
                    **{
                        **item,
                        "candidates": tuple(item.get("candidates", ())),
                    }
                )
                for item in records("mentions")
            ],
            resolution_history=[
                EntityResolutionVersion(**item)
                for item in records("resolution_history")
            ],
        )

    def current_proposition_entity(self, proposition: PropositionRecord, role: str) -> str | None:
        """Resolve one proposition role using the latest mention resolution."""

        mention_id = proposition.mention_ids.get(role)
        if mention_id:
            resolution = self.current_mention_resolution(mention_id)
            if resolution:
                return resolution.entity_id
        return proposition.entity_ids.get(role)

    def resolved_proposition(self, proposition: PropositionRecord) -> dict[str, Any]:
        """Return a read-only view with the latest entity resolutions.

        Proposition records themselves remain immutable observations.  This
        view is for consumers that need old sentences to follow a later
        pronoun or alias resolution without rewriting the original evidence.
        """

        data = proposition.to_dict()
        roles = tuple(dict.fromkeys((*proposition.entity_ids, *proposition.mention_ids)))
        data["entity_ids"] = {
            role: entity_id
            for role in roles
            if (entity_id := self.current_proposition_entity(proposition, role)) is not None
        }
        data["mention_resolution_status"] = {
            role: (
                self.current_mention_resolution(mention_id).status
                if self.current_mention_resolution(mention_id)
                else "initial"
            )
            for role, mention_id in proposition.mention_ids.items()
        }
        return data

    def current_propositions(
        self,
        *,
        frame_id: str | None = None,
        document_id: str | None = None,
        include_non_asserted: bool = True,
    ) -> list[dict[str, Any]]:
        """Return all observations with current reference bindings.

        The list is append-only: ``current`` refers to the latest entity
        resolution, not to deleting older observations or treating them as
        mutable state snapshots.
        """

        return [
            self.resolved_proposition(proposition)
            for proposition in self.propositions
            if (frame_id is None or proposition.frame_id == frame_id)
            and (document_id is None or proposition.document_id == document_id)
            and (
                include_non_asserted
                or (
                    proposition.modality == "asserted"
                    and proposition.polarity == "affirmed"
                )
            )
        ]

    def current_frame(self, frame_id: str) -> ContextFrameVersion | None:
        for version in reversed(self.frame_history):
            if version.frame_id == frame_id:
                return version
        return None

    def current_frames(self) -> dict[str, ContextFrameVersion]:
        frames: dict[str, ContextFrameVersion] = {}
        for version in self.frame_history:
            frames[version.frame_id] = version
        return frames

    def upsert_frame(
        self,
        *,
        frame_id: str,
        label: str | None,
        kind: str = "context",
        status: str = "unknown",
        block_index: int = -1,
        source_text: str = "",
        attributes: dict[str, str] | None = None,
        parent_frame_id: str | None = None,
        document_id: str = "document",
        evidence_id: str | None = None,
        confidence: float = 1.0,
    ) -> ContextFrameVersion:
        normalized_attributes = dict(attributes or {})
        previous = self.current_frame(frame_id)
        if previous and (
            previous.label == label
            and previous.kind == kind
            and previous.status == status
            and previous.attributes == normalized_attributes
            and previous.parent_frame_id == parent_frame_id
        ):
            return previous

        version = ContextFrameVersion(
            frame_id=frame_id,
            label=label,
            kind=kind,
            status=status,
            block_index=block_index,
            source_text=source_text,
            attributes=normalized_attributes,
            parent_frame_id=parent_frame_id,
            document_id=document_id,
            evidence_id=evidence_id,
            confidence=confidence,
            previous_version_id=previous.version_id if previous else None,
            version_id=f"frame-version:{len(self.frame_history)}",
        )
        self.frame_history.append(version)
        return version

    def ensure_frame(
        self,
        frame_id: str = DEFAULT_FRAME_ID,
        *,
        label: str | None = None,
        kind: str = "document",
        status: str = "observed",
        document_id: str = "document",
    ) -> ContextFrameVersion:
        current = self.current_frame(frame_id)
        if current:
            return current
        return self.upsert_frame(
            frame_id=frame_id,
            label=label,
            kind=kind,
            status=status,
            document_id=document_id,
        )

    def resolve_mention(
        self,
        *,
        mention_id: str,
        entity_id: str,
        status: str = "resolved",
        block_index: int,
        source_text: str,
        evidence_id: str | None = None,
    ) -> EntityResolutionVersion:
        """Append a later interpretation of an earlier unresolved mention."""

        version = EntityResolutionVersion(
            mention_id=mention_id,
            entity_id=entity_id,
            status=status,
            block_index=block_index,
            source_text=source_text,
            evidence_id=evidence_id,
            version_id=f"resolution-version:{len(self.resolution_history)}",
        )
        self.resolution_history.append(version)
        mention = next((item for item in self.mentions if item.mention_id == mention_id), None)
        if mention:
            self.aliases[mention.text] = entity_id
            self.entity_kinds.setdefault(entity_id, "entity")
            self._remember_entity(entity_id, frame_id=mention.frame_id)
        return version

    def current_mention_resolution(self, mention_id: str) -> EntityResolutionVersion | None:
        for version in reversed(self.resolution_history):
            if version.mention_id == mention_id:
                return version
        return None

    def rebind_mention(
        self,
        *,
        mention_id: str,
        entity_id: str,
        block_index: int,
        source_text: str,
        evidence_id: str | None = None,
        document_id: str = "document",
    ) -> list[StateVersion]:
        """Resolve a mention and append revised versions of its live states."""

        self.resolve_mention(
            mention_id=mention_id,
            entity_id=entity_id,
            block_index=block_index,
            source_text=source_text,
            evidence_id=evidence_id,
        )
        revised: list[StateVersion] = []
        affected = [version for version in self.history if version.mention_id == mention_id]
        for previous in affected:
            if self.latest(previous.entity, previous.attribute, frame_id=previous.frame_id) is not previous:
                continue
            self.upsert(
                entity=previous.entity,
                attribute=previous.attribute,
                value=previous.value,
                block_index=block_index,
                source_text=source_text,
                mode="reference-retraction",
                kind=previous.kind,
                confidence=previous.confidence,
                entity_kind=self.entity_kinds.get(previous.entity, "entity"),
                frame_id=previous.frame_id,
                evidence_id=evidence_id,
                epistemic_status="retracted",
                document_id=document_id,
                mention_id=previous.mention_id,
                proposition_id=previous.proposition_id,
            )
            version = self.upsert(
                entity=entity_id,
                attribute=previous.attribute,
                value=previous.value,
                block_index=block_index,
                source_text=source_text,
                mode="reference-revision",
                kind=previous.kind,
                confidence=previous.confidence,
                entity_kind=self.entity_kinds.get(entity_id, "entity"),
                frame_id=previous.frame_id,
                evidence_id=evidence_id,
                epistemic_status="revised",
                document_id=document_id,
                mention_id=previous.mention_id,
                proposition_id=previous.proposition_id,
            )
            if version is not None:
                revised.append(version)
        return revised

    def _remember_entity(self, entity: str, frame_id: str = DEFAULT_FRAME_ID) -> None:
        if entity in self._recent_entities:
            self._recent_entities.remove(entity)
        self._recent_entities.insert(0, entity)
        recent = self._recent_entities_by_frame.setdefault(frame_id, [])
        if entity in recent:
            recent.remove(entity)
        recent.insert(0, entity)

    def resolve_entity(
        self,
        raw_entity: str,
        expected_kind: str | None = None,
        *,
        frame_id: str = DEFAULT_FRAME_ID,
    ) -> str:
        normalized = _normalize_entity(raw_entity)

        if normalized in _AUTO_RESOLVE_PRONOUNS:
            recent_entities = self._recent_entities_by_frame.get(frame_id, self._recent_entities)
            candidates = _candidate_entities(recent_entities, self.entity_kinds, expected_kind)
            if candidates:
                return candidates[0]

        return self.aliases.get(normalized, normalized)

    def register_entity(
        self,
        raw_entity: str,
        kind: str = "entity",
        *,
        block_index: int | None = None,
        source_text: str = "",
        frame_id: str = DEFAULT_FRAME_ID,
        evidence_id: str | None = None,
    ) -> str:
        normalized = _normalize_entity(raw_entity)
        candidates: list[str] = []
        if normalized in _PRONOUNS:
            recent_entities = self._recent_entities_by_frame.get(frame_id, self._recent_entities)
            candidates = _candidate_entities(recent_entities, self.entity_kinds, kind)
        if normalized in _AUTO_RESOLVE_PRONOUNS:
            entity = candidates[0] if len(candidates) == 1 else normalized
        elif normalized in _PRONOUNS:
            entity = normalized
        else:
            entity = self.resolve_entity(normalized, expected_kind=kind, frame_id=frame_id)

        # An unresolved pronoun is retained as a literal entity.  It is better
        # to expose an unresolved reference than to silently attach it to the
        # wrong object.
        if normalized in _PRONOUNS and entity == normalized:
            entity = normalized

        if normalized not in _PRONOUNS:
            self.aliases[normalized] = entity
        self.entity_kinds.setdefault(entity, kind)
        self._remember_entity(entity, frame_id=frame_id)
        if block_index is not None:
            if normalized in _PRONOUNS and normalized not in _AUTO_RESOLVE_PRONOUNS:
                resolution_status = "ambiguous" if len(candidates) > 1 else "unresolved"
            elif normalized in _PRONOUNS and not candidates:
                resolution_status = "unresolved"
            elif len(candidates) > 1:
                resolution_status = "ambiguous"
            else:
                resolution_status = "resolved"
            self.mentions.append(
                EntityMention(
                    mention_id=f"mention:{len(self.mentions)}",
                    text=normalized,
                    entity_id=entity,
                    block_index=block_index,
                    source_text=source_text,
                    frame_id=frame_id,
                    resolution_status=resolution_status,
                    candidates=tuple(candidates),
                    evidence_id=evidence_id,
                )
            )
        return entity

    def latest(
        self,
        entity: str,
        attribute: str,
        frame_id: str = DEFAULT_FRAME_ID,
    ) -> StateVersion | None:
        for version in reversed(self.history):
            if (
                version.entity == entity
                and version.attribute == attribute
                and version.frame_id == frame_id
            ):
                return version
        return None

    def upsert(
        self,
        *,
        entity: str,
        attribute: str,
        value: str,
        block_index: int,
        source_text: str,
        mode: str = "asserted",
        kind: str = "property",
        confidence: float = 1.0,
        entity_kind: str = "entity",
        frame_id: str = DEFAULT_FRAME_ID,
        evidence_id: str | None = None,
        epistemic_status: str = "asserted",
        document_id: str = "document",
        mention_id: str | None = None,
        proposition_id: str | None = None,
    ) -> StateVersion | None:
        """Update an existing state or append a new state.

        ``None`` means the observation is identical to the latest state and
        was intentionally ignored as a duplicate.
        """

        mention_count = len(self.mentions)
        canonical_entity = self.register_entity(
            entity,
            kind=entity_kind,
            block_index=block_index,
            source_text=source_text,
            frame_id=frame_id,
            evidence_id=evidence_id,
        )
        attached_mention_id = mention_id or (
            self.mentions[-1].mention_id if len(self.mentions) > mention_count else None
        )
        canonical_attribute = _normalize_attribute(attribute)
        normalized_value = _clean_text(value)
        previous = self.latest(canonical_entity, canonical_attribute, frame_id=frame_id)

        if previous and (
            previous.value == normalized_value
            and previous.epistemic_status == epistemic_status
        ):
            self._remember_entity(canonical_entity, frame_id=frame_id)
            return None

        version = StateVersion(
            entity=canonical_entity,
            attribute=canonical_attribute,
            value=normalized_value,
            block_index=block_index,
            source_text=source_text,
            mode=mode,
            kind=kind,
            confidence=confidence,
            previous_value=previous.value if previous else None,
            frame_id=frame_id,
            evidence_id=evidence_id,
            epistemic_status=epistemic_status,
            document_id=document_id,
            mention_id=attached_mention_id,
            supersedes_version_id=previous.version_id if previous else None,
            version_id=f"state-version:{len(self.history)}",
            proposition_id=proposition_id,
        )
        self.history.append(version)
        self._remember_entity(canonical_entity, frame_id=frame_id)
        return version

    def revise_state(self, **kwargs: Any) -> StateVersion | None:
        """Append a later interpretation while preserving the prior version."""

        kwargs.setdefault("mode", "revision")
        kwargs.setdefault("epistemic_status", "revised")
        return self.upsert(**kwargs)

    def current_records(
        self,
        *,
        include_retracted: bool = False,
        include_observations: bool = False,
        through_block_index: int | None = None,
    ) -> dict[tuple[str, str], StateVersion]:
        latest: dict[tuple[str, str], StateVersion] = {}
        for version in self.history:
            if through_block_index is not None and version.block_index > through_block_index:
                continue
            if not include_observations and version.kind == "observation":
                continue
            key = (version.entity, version.attribute)
            if version.epistemic_status == "retracted" and not include_retracted:
                latest.pop(key, None)
            else:
                latest[key] = version
        return latest

    def current_scoped_records(
        self,
        *,
        include_retracted: bool = False,
        include_observations: bool = False,
        through_block_index: int | None = None,
    ) -> dict[tuple[str, str, str], StateVersion]:
        """Return the latest value separately inside every context frame."""

        latest: dict[tuple[str, str, str], StateVersion] = {}
        for version in self.history:
            if through_block_index is not None and version.block_index > through_block_index:
                continue
            if not include_observations and version.kind == "observation":
                continue
            key = (version.frame_id, version.entity, version.attribute)
            if version.epistemic_status == "retracted" and not include_retracted:
                latest.pop(key, None)
            else:
                latest[key] = version
        return latest

    def current_state(
        self,
        *,
        include_observations: bool = False,
        through_block_index: int | None = None,
    ) -> dict[str, dict[str, str]]:
        """Return a legacy unscoped view of every attribute's last value.

        Use ``current_state_by_frame`` when facts from separate contexts must
        remain distinct.
        """

        state: dict[str, dict[str, str]] = {}
        for (entity, attribute), version in self.current_records(
            include_observations=include_observations,
            through_block_index=through_block_index,
        ).items():
            state.setdefault(entity, {})[attribute] = version.value
        return state

    def current_state_by_frame(
        self,
        *,
        include_observations: bool = False,
        through_block_index: int | None = None,
    ) -> dict[str, dict[str, dict[str, str]]]:
        """Return the latest state without merging separate context frames."""

        state: dict[str, dict[str, dict[str, str]]] = {}
        for (
            frame_id,
            entity,
            attribute,
        ), version in self.current_scoped_records(
            include_observations=include_observations,
            through_block_index=through_block_index,
        ).items():
            state.setdefault(frame_id, {}).setdefault(entity, {})[attribute] = version.value
        return state

    def current_state_with_metadata(
        self,
        *,
        include_observations: bool = False,
        through_block_index: int | None = None,
    ) -> dict[str, dict[str, dict[str, Any]]]:
        state: dict[str, dict[str, dict[str, Any]]] = {}
        for (entity, attribute), version in self.current_records(
            include_observations=include_observations,
            through_block_index=through_block_index,
        ).items():
            state.setdefault(entity, {})[attribute] = version.to_dict()
        return state

    def current_state_by_frame_with_metadata(
        self,
        *,
        include_observations: bool = False,
        through_block_index: int | None = None,
    ) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
        state: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
        for (
            frame_id,
            entity,
            attribute,
        ), version in self.current_scoped_records(
            include_observations=include_observations,
            through_block_index=through_block_index,
        ).items():
            state.setdefault(frame_id, {}).setdefault(entity, {})[attribute] = version.to_dict()
        return state

    def current_observations(
        self,
        *,
        through_block_index: int | None = None,
    ) -> dict[tuple[str, str], StateVersion]:
        """Return the latest materialized observation for each address."""

        return {
            key: version
            for key, version in self.current_records(
                include_observations=True,
                through_block_index=through_block_index,
            ).items()
            if version.kind == "observation"
        }


@dataclass(slots=True)
class BlockResult:
    index: int
    text: str
    updates: list[StateVersion]
    propositions: list[PropositionRecord] = field(default_factory=list)
    evidence_id: str | None = None
    frame_id: str = DEFAULT_FRAME_ID
    source_line_indices: tuple[int, ...] = ()


@dataclass(slots=True)
class ExtractionResult:
    blocks: list[BlockResult]
    world: WorldModel
    cleaning: DocumentCleaningResult | None = None
    document_id: str = "document"

    @property
    def propositions(self) -> list[PropositionRecord]:
        return self.world.propositions


@dataclass(slots=True, frozen=True)
class ExtractionContext:
    """Context attached to every observation extracted from one block."""

    block_index: int
    frame_id: str
    evidence_id: str
    document_id: str


class StateExtractor:
    """A conservative, LLM-independent Chinese fact and state extractor.

    Every sentence first produces one or more generic ``PropositionRecord``
    objects from its dependency parse.  The older hand-written patterns below
    are optional state projections for relations where a persistent attribute
    is clear.  The extractor never invents an update merely because a previous
    state was not mentioned in the current block.
    """

    _DURATION_RE = r"[0-9一二三四五六七八九十百千万零〇两]+(?:个?年|个?月|天|小时|分钟)"

    def __init__(
        self,
        projection_rules: Iterable[StateProjectionRule] | None = None,
        *,
        include_legacy_patterns: bool | None = None,
        materialize_observations: bool = True,
    ) -> None:
        """Create an extractor with replaceable state projection semantics.

        Passing ``projection_rules=()`` keeps the complete proposition layer
        while disabling all generic event-to-state effects.  This is useful
        for measuring whether a project's own projection rules add value.
        Supplying any rule set also disables the compatibility regex rules by
        default; set ``include_legacy_patterns=True`` when old projections
        are still required during migration.
        ``materialize_observations`` keeps every proposition in the durable
        model as an observation state, including questions and conditions.
        """

        self.projection_rules = tuple(
            DEFAULT_STATE_PROJECTION_RULES if projection_rules is None else projection_rules
        )
        self.include_legacy_patterns = (
            projection_rules is None
            if include_legacy_patterns is None
            else include_legacy_patterns
        )
        self.materialize_observations = materialize_observations
        self._active_context: ExtractionContext | None = None

    def extract(
        self,
        text: str,
        world: WorldModel | None = None,
        *,
        document_id: str = "document",
        max_blocks: int | None = None,
    ) -> ExtractionResult:
        model = world or WorldModel()
        self._active_context = None
        block_results: list[BlockResult] = []
        cleaning = clean_document_text(text)
        document_frame_id = DEFAULT_FRAME_ID if document_id == "document" else f"{document_id}:document"
        document_frame = model.ensure_frame(
            frame_id=document_frame_id,
            label=None,
            kind="document",
            status="observed",
            document_id=document_id,
        )
        frame_ids: dict[str, str] = {document_frame_id: document_frame.frame_id}
        for structure in cleaning.structures:
            frame_id = f"{document_id}:{structure.structure_id}"
            model.upsert_frame(
                frame_id=frame_id,
                label=structure.text,
                kind=structure.role,
                status="observed",
                block_index=-1,
                source_text=structure.text,
                parent_frame_id=document_frame.frame_id,
                document_id=document_id,
            )
            frame_ids[structure.structure_id] = frame_id

        starting_index = model.next_block_index()
        for relative_index, block in enumerate(
            segment_document(cleaning, max_blocks=max_blocks)
        ):
            block_index = starting_index + relative_index
            frame_id = frame_ids.get(block.structure_id, document_frame.frame_id)
            evidence = model.record_evidence(
                document_id=document_id,
                block_index=block_index,
                text=block.text,
                frame_id=frame_id,
                source_line_indices=block.source_line_indices,
            )
            context = ExtractionContext(
                block_index=block_index,
                frame_id=frame_id,
                evidence_id=evidence.evidence_id,
                document_id=document_id,
            )
            self._active_context = context
            updates: list[StateVersion] = []
            propositions: list[PropositionRecord] = []
            for sentence_index, sentence in enumerate(_split_extraction_units(block.text)):
                self._extract_sentence(
                    sentence,
                    block_index,
                    model,
                    updates,
                    propositions,
                    sentence_index,
                )
            block_results.append(
                BlockResult(
                    block_index,
                    block.text,
                    updates,
                    propositions,
                    evidence_id=evidence.evidence_id,
                    frame_id=frame_id,
                    source_line_indices=block.source_line_indices,
                )
            )

        self._active_context = None
        return ExtractionResult(block_results, model, cleaning, document_id=document_id)

    def _register_entity(
        self,
        model: WorldModel,
        raw_entity: str,
        kind: str,
        source_text: str = "",
    ) -> str:
        context = getattr(self, "_active_context", None)
        return model.register_entity(
            raw_entity,
            kind=kind,
            block_index=context.block_index if context else None,
            source_text=source_text,
            frame_id=context.frame_id if context else DEFAULT_FRAME_ID,
            evidence_id=context.evidence_id if context else None,
        )

    def _emit(
        self,
        model: WorldModel,
        updates: list[StateVersion],
        *,
        entity: str,
        attribute: str,
        value: str,
        block_index: int,
        source_text: str,
        mode: str = "asserted",
        kind: str = "property",
        confidence: float = 1.0,
        entity_kind: str = "entity",
        epistemic_status: str = "asserted",
        mention_id: str | None = None,
        proposition_id: str | None = None,
    ) -> None:
        context = getattr(self, "_active_context", None)
        version = model.upsert(
            entity=entity,
            attribute=attribute,
            value=value,
            block_index=block_index,
            source_text=source_text,
            mode=mode,
            kind=kind,
            confidence=confidence,
            entity_kind=entity_kind,
            frame_id=context.frame_id if context else DEFAULT_FRAME_ID,
            evidence_id=context.evidence_id if context else None,
            epistemic_status=epistemic_status,
            document_id=context.document_id if context else "document",
            mention_id=mention_id,
            proposition_id=proposition_id,
        )
        if version is not None:
            updates.append(version)

    def _project_generic_observation(
        self,
        proposition: PropositionRecord,
        block_index: int,
        model: WorldModel,
        updates: list[StateVersion],
    ) -> None:
        """Materialize every proposition without claiming it is world fact.

        ``PropositionRecord`` is the loss-preserving linguistic form.  This
        additional observation address makes it available through the same
        append-only persistence and replay path as ordinary state versions.
        Its ``kind`` remains ``observation`` so consumers can keep it separate
        from verified world attributes.
        """

        if not self.materialize_observations:
            return

        anchor_role = "subject" if proposition.mention_ids.get("subject") else None
        if anchor_role is None:
            anchor_role = next(iter(proposition.entity_ids), None)
        entity_id = (
            model.current_proposition_entity(proposition, anchor_role)
            if anchor_role
            else None
        )
        mention_id = proposition.mention_ids.get(anchor_role) if anchor_role else None
        entity_kind = model.entity_kinds.get(entity_id, "entity") if entity_id else "observation"
        if entity_id is None:
            entity_id = f"observation:{proposition.proposition_id}"

        attribute = f"observation:{proposition.predicate or proposition.kind}"
        value = json.dumps(
            proposition.arguments,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ) or "true"
        epistemic_status = (
            "negated"
            if proposition.polarity == "negated"
            else proposition.modality
        )
        self._emit(
            model,
            updates,
            entity=entity_id,
            attribute=attribute,
            value=value,
            block_index=block_index,
            source_text=proposition.source_text,
            mode="generic-observation",
            kind="observation",
            confidence=proposition.confidence,
            entity_kind=entity_kind,
            epistemic_status=epistemic_status,
            mention_id=mention_id,
            proposition_id=proposition.proposition_id,
        )

    def _project_generic_property(
        self,
        proposition: PropositionRecord,
        block_index: int,
        model: WorldModel,
        updates: list[StateVersion],
    ) -> None:
        """Project only syntactically persistent propositions into state.

        Events remain events.  A generic parser cannot safely assume that an
        arbitrary verb describes a lasting attribute, so this projection is
        intentionally limited to copular, adjectival, possession, and
        location-like predicates with an identified subject.
        """

        if proposition.kind != "property" or not proposition.subject:
            return
        if "inherited_subject" in proposition.diagnostics:
            return
        if proposition.modality in {"question", "conditional", "predicted"}:
            return
        if proposition.polarity != "affirmed":
            return

        subject = model.current_proposition_entity(proposition, "subject")
        if not subject:
            return
        predicate = proposition.predicate
        argument_values = [
            value
            for role, value in proposition.arguments.items()
            if role != "subject"
        ]
        value = argument_values[0] if argument_values else "true"
        attribute = predicate
        if predicate in {"在", "位于", "处于"}:
            attribute = "location"
        elif predicate == "有":
            attribute = "has"
        elif predicate in {"是", "属于"}:
            attribute = "identity"

        self._emit(
            model,
            updates,
            entity=subject,
            attribute=attribute,
            value=value,
            block_index=block_index,
            source_text=proposition.source_text,
            mode="generic-projection",
            kind="property",
            confidence=proposition.confidence,
            entity_kind="entity",
            epistemic_status="negated" if proposition.polarity == "negated" else "asserted",
            mention_id=proposition.mention_ids.get("subject"),
            proposition_id=proposition.proposition_id,
        )

    @staticmethod
    def _proposition_argument(
        model: WorldModel,
        proposition: PropositionRecord,
        role: str,
    ) -> tuple[str | None, str | None, str | None]:
        for key, value in proposition.arguments.items():
            if key != role and not key.startswith(f"{role}_"):
                continue
            entity_id = model.current_proposition_entity(proposition, key)
            return entity_id, value, proposition.mention_ids.get(key)
        return None, None, None

    @staticmethod
    def _location_value(value: str) -> str:
        return re.sub(r"^(?:在|于|到|向)", "", value) or value

    @staticmethod
    def _match_predicate(predicate: str, vocabulary: set[str]) -> str | None:
        for candidate in sorted(vocabulary, key=len, reverse=True):
            if predicate == candidate or predicate.startswith(candidate):
                return candidate
        return None

    @staticmethod
    def _first_projection_argument(
        model: WorldModel,
        proposition: PropositionRecord,
        primary_role: str | None,
        fallback_roles: tuple[str, ...],
    ) -> tuple[str | None, str | None, str | None]:
        roles = tuple(role for role in (primary_role, *fallback_roles) if role)
        for role in roles:
            entity_id, value, mention_id = StateExtractor._proposition_argument(
                model,
                proposition,
                role,
            )
            if entity_id is not None or value is not None:
                return entity_id, value, mention_id
        return None, None, None

    def _project_generic_event(
        self,
        proposition: PropositionRecord,
        block_index: int,
        model: WorldModel,
        updates: list[StateVersion],
    ) -> None:
        """Apply configured proposition-to-state effects.

        The proposition layer is complete even when no rule matches.  Rules
        only materialize a subset of propositions as current state, and each
        materialized value keeps the original proposition as provenance.
        """

        for rule in self.projection_rules:
            if rule.allowed_kinds and proposition.kind not in rule.allowed_kinds:
                continue
            if rule.allowed_modalities and proposition.modality not in rule.allowed_modalities:
                continue
            if rule.allowed_polarities and proposition.polarity not in rule.allowed_polarities:
                continue
            matched_predicate = self._match_predicate(
                proposition.predicate,
                set(rule.predicates),
            )
            if matched_predicate is None:
                continue

            entity_id, entity_value, entity_mention_id = self._first_projection_argument(
                model,
                proposition,
                rule.entity_role,
                rule.fallback_entity_roles,
            )
            if entity_id is None and rule.predicate_suffix_entity:
                suffix = ""
                for candidate in (proposition.predicate, entity_value or ""):
                    if candidate.startswith(matched_predicate):
                        suffix = candidate[len(matched_predicate) :]
                        if suffix:
                            break
                if suffix:
                    entity_id = self._register_entity(
                        model,
                        suffix,
                        rule.entity_kind,
                        proposition.source_text,
                    )

            if entity_id is None:
                continue

            if rule.effect == "relation":
                value_entity_id, value, _ = self._first_projection_argument(
                    model,
                    proposition,
                    rule.value_role,
                    rule.fallback_value_roles,
                )
                if rule.value_is_entity:
                    value = value_entity_id
                if value is None:
                    continue
                if rule.normalize_location_value:
                    value = self._location_value(value)
                self._emit(
                    model,
                    updates,
                    entity=entity_id,
                    attribute=rule.attribute or "relation",
                    value=value,
                    block_index=block_index,
                    source_text=proposition.source_text,
                    mode="generic-event-effect",
                    kind=rule.state_kind,
                    confidence=min(proposition.confidence, rule.confidence),
                    entity_kind=rule.entity_kind,
                    epistemic_status="negated" if proposition.polarity == "negated" else "asserted",
                    mention_id=entity_mention_id,
                    proposition_id=proposition.proposition_id,
                )
                continue

            if rule.value_role:
                _, value, _ = self._first_projection_argument(
                    model,
                    proposition,
                    rule.value_role,
                    rule.fallback_value_roles,
                )
                if value is None:
                    continue
                if rule.normalize_condition_value:
                    value = re.sub(
                        r"^(?:\u53ea\u6709|\u53ea\u8981|\u5982\u679c)",
                        "",
                        value,
                    ).strip()
            elif rule.value_from_predicate:
                value = matched_predicate
            else:
                value = rule.value or matched_predicate
            self._emit(
                model,
                updates,
                entity=entity_id,
                attribute=rule.attribute or "state",
                value=value,
                block_index=block_index,
                source_text=proposition.source_text,
                mode="generic-event-effect",
                kind=rule.state_kind,
                confidence=min(proposition.confidence, rule.confidence),
                entity_kind=rule.entity_kind,
                epistemic_status="negated" if proposition.polarity == "negated" else "asserted",
                mention_id=entity_mention_id,
                proposition_id=proposition.proposition_id,
            )

    def _extract_sentence(
        self,
        sentence: str,
        block_index: int,
        model: WorldModel,
        updates: list[StateVersion],
        propositions: list[PropositionRecord],
        sentence_index: int,
    ) -> None:
        self._extract_generic_propositions(
            sentence,
            block_index,
            sentence_index,
            model,
            updates,
            propositions,
        )
        if self.include_legacy_patterns:
            self._extract_conditional_opening(sentence, block_index, model, updates)
            self._extract_transfer(sentence, block_index, model, updates)
            self._extract_waiting(sentence, block_index, model, updates)
            self._extract_condition(sentence, block_index, model, updates)
            self._extract_opened(sentence, block_index, model, updates)
            self._extract_location(sentence, block_index, model, updates)

    def _register_proposition_entity(
        self,
        model: WorldModel,
        cache: dict[tuple[str, str], tuple[str, str | None]],
        raw_value: str,
        kind: str,
        *,
        block_index: int,
        source_text: str,
    ) -> tuple[str, str | None]:
        normalized = _normalize_entity(raw_value)
        key = (normalized, kind)
        if key not in cache:
            context = getattr(self, "_active_context", None)
            mention_count = len(model.mentions)
            entity = model.register_entity(
                normalized,
                kind=kind,
                block_index=block_index,
                source_text=source_text,
                frame_id=context.frame_id if context else DEFAULT_FRAME_ID,
                evidence_id=context.evidence_id if context else None,
            )
            mention_id = model.mentions[-1].mention_id if len(model.mentions) > mention_count else None
            cache[key] = (entity, mention_id)
        return cache[key]

    @staticmethod
    def _proposition_modality(sentence: str) -> tuple[str, str]:
        stripped = sentence.strip()
        leading = stripped.lstrip("\u201c\u2018\u300c\u300e\uff08(\"'")
        modality_text = stripped.rstrip("\u201d\u2019\u300d\u300f\u3011\uff09)]\"'")
        if modality_text.endswith(("？", "?")) or re.search(r"(?:吗|么)[。！？!?]?$", modality_text):
            return "question", "affirmed"
        if any(stripped.startswith(marker) for marker in _REPORTING_MARKERS):
            return "reported", "affirmed"
        conditional = (
            re.search(r"(?:如果|只有|只要|除非|一旦)", stripped)
            or re.search(r"(?:当|在)[^。！？!?]{0,40}(?:时|时候|之前|之后|以后|以前)", stripped)
            or re.search(r"[^。！？!?]{1,40}(?:才|就)(?:能|可以|会|是|打开|发生)?", stripped)
        )
        if conditional:
            return "conditional", "affirmed"
        if re.search(r"(?:会|将会|将|可能|应该|要)(?=[\u4e00-\u9fff])", stripped):
            polarity = (
                "negated"
                if re.search(r"^(?:不|未|没)(?:会|将|可能|应该|要)", leading)
                else "affirmed"
            )
            return "predicted", polarity
        if re.search(
            r"^(?:\u6ca1\u6709|\u6ca1|\u672a|\u65e0|\u4e0d\u662f|\u4e0d\u80fd|\u65e0\u6cd5|\u4e0d)(?=[\u4e00-\u9fff！。！？!?]|$)",
            leading,
        ):
            return "asserted", "negated"
        if re.search(
            r"^[^，。！？!?]{0,6}(?:\u6ca1\u6709|\u6ca1|\u672a|\u65e0)(?=[，。！？!?]|$)",
            stripped,
        ):
            return "asserted", "negated"
        if re.search(r"(?:^|[，。！？!?、])(?:不|没|没有|未|无|别|莫)", leading):
            return "asserted", "negated"
        return "asserted", "affirmed"

    @staticmethod
    def _argument_kind(role: str, value: str) -> str:
        if role == "location":
            return "location"
        if role == "time":
            return "time"
        if role in {"subject", "indirect_object"}:
            if value in _PERSON_PRONOUNS:
                return "person"
            if value in _OBJECT_PRONOUNS:
                return "object"
            return "entity"
        if role == "object":
            return "object"
        return "entity"

    @staticmethod
    def _normalize_argument(role: str, value: str) -> tuple[str, str]:
        """Normalize common Chinese case markers without losing the raw form."""

        normalized = value.strip()
        if role in {"oblique", "clause", "object"}:
            for prefix in ("把", "将"):
                if normalized.startswith(prefix) and len(normalized) > len(prefix):
                    return "object", normalized[len(prefix) :]
            for prefix in ("在", "于"):
                if normalized.startswith(prefix) and len(normalized) > len(prefix):
                    return "location", normalized
            for prefix in ("向", "对"):
                if normalized.startswith(prefix) and len(normalized) > len(prefix):
                    return "indirect_object", normalized[len(prefix) :]
            if normalized.startswith(("如果", "只有", "只要", "当", "除非", "一旦")):
                return "condition", normalized
        return role, normalized

    def _record_proposition(
        self,
        model: WorldModel,
        propositions: list[PropositionRecord],
        *,
        sentence: str,
        block_index: int,
        sentence_index: int,
        predicate: str,
        kind: str,
        surface_predicate: str | None = None,
        subject: str | None = None,
        arguments: dict[str, str] | None = None,
        raw_arguments: dict[str, str] | None = None,
        entity_ids: dict[str, str] | None = None,
        mention_ids: dict[str, str] | None = None,
        polarity: str = "affirmed",
        modality: str = "asserted",
        parser: str = "fallback",
        confidence: float = 1.0,
        diagnostics: tuple[str, ...] = (),
    ) -> PropositionRecord:
        context = getattr(self, "_active_context", None)
        proposition = PropositionRecord(
            proposition_id=f"proposition:{len(model.propositions)}",
            block_index=block_index,
            sentence_index=sentence_index,
            source_text=sentence,
            predicate=predicate,
            kind=kind,
            surface_predicate=surface_predicate or predicate,
            subject=subject,
            arguments=dict(arguments or {}),
            raw_arguments=dict(raw_arguments or arguments or {}),
            entity_ids=dict(entity_ids or {}),
            mention_ids=dict(mention_ids or {}),
            polarity=polarity,
            modality=modality,
            frame_id=context.frame_id if context else DEFAULT_FRAME_ID,
            evidence_id=context.evidence_id if context else None,
            document_id=context.document_id if context else "document",
            parser=parser,
            confidence=confidence,
            diagnostics=diagnostics,
        )
        model.record_proposition(proposition)
        propositions.append(proposition)
        return proposition

    def _extract_generic_propositions(
        self,
        sentence: str,
        block_index: int,
        sentence_index: int,
        model: WorldModel,
        updates: list[StateVersion],
        propositions: list[PropositionRecord],
    ) -> None:
        """Extract dependency-backed facts without a domain vocabulary.

        This method intentionally does not decide whether a proposition is
        important.  It records predicates, arguments, modifiers and modality;
        only the later state projection decides whether a persistent attribute
        is clear enough for ``StateVersion``.
        """

        tokens = parse_dependencies(sentence)
        if not tokens:
            proposition = self._record_proposition(
                model,
                propositions,
                sentence=sentence,
                block_index=block_index,
                sentence_index=sentence_index,
                predicate="",
                kind="unparsed",
                arguments={"text": sentence.strip()},
                modality="unparsed",
                parser="unavailable",
                confidence=0.2,
            )
            self._project_generic_observation(proposition, block_index, model, updates)
            return

        children = _dependency_children(tokens)
        entity_cache: dict[tuple[str, str], tuple[str, str | None]] = {}
        lexical_spans = _lexical_word_spans(sentence)
        predicate_candidates = {
            token.id: _surface_predicate_candidate(sentence, tokens, token, lexical_spans)
            for token in tokens
            if token.upos in _PREDICATE_UPOS
        }

        # Register nominal mentions even when they are not selected as the
        # main predicate's arguments.  This prevents noun phrases in a clause
        # or quoted content from disappearing merely because the parser chose
        # a different root.
        for token in tokens:
            if token.upos not in _NOMINAL_UPOS or token.relation not in _MENTION_RELATIONS:
                continue
            if _is_internal_lexical_fragment(sentence, tokens, token, lexical_spans):
                continue
            raw_value = _dependency_text(tokens, _dependency_subtree(tokens, token.id))
            if not raw_value:
                continue
            self._register_proposition_entity(
                model,
                entity_cache,
                raw_value,
                _pronoun_kind(token.text) if token.upos == "PRON" else "entity",
                block_index=block_index,
                source_text=sentence,
            )

        predicate_tokens = [
            token
            for token in tokens
            if token.upos in _PREDICATE_UPOS
            and token.relation not in {"aux", "cop"}
            and not _is_governing_existential(token, children)
            and not (
                _is_internal_lexical_fragment(sentence, tokens, token, lexical_spans)
                and token.relation != "root"
            )
            and (
                token.relation == "root"
                or any(
                    child.relation
                    in _SUBJECT_ARGUMENT_RELATIONS | _OBJECT_ARGUMENT_RELATIONS | _CLAUSE_ARGUMENT_RELATIONS
                    for child in children.get(token.id, ())
                )
                or (
                    token.relation in _PREDICATE_RELATIONS
                    and predicate_candidates.get(token.id, (token.text, None))[0] != token.text
                )
            )
        ]
        predicate_tokens.extend(
            token
            for token in tokens
            if token.upos in {"NOUN", "ADJ"}
            and any(child.relation == "cop" for child in children.get(token.id, ()))
            and not _is_internal_lexical_fragment(sentence, tokens, token, lexical_spans)
            and token not in predicate_tokens
        )
        root = next((token for token in tokens if token.head == 0 and token.upos != "PUNCT"), None)
        if root is not None and root in predicate_tokens and root.upos in {"NOUN", "ADJ", "PART"}:
            root_span = _token_surface_spans(sentence, tokens).get(root.id)
            if root_span is not None and any(
                token is not root
                and token.upos in {"VERB", "AUX"}
                and predicate_candidates.get(token.id, (token.text, None))[0] != token.text
                and (
                    (candidate_span := predicate_candidates[token.id][1]) is not None
                    and candidate_span[0] < root_span[0]
                    and candidate_span[1] <= root_span[1]
                )
                for token in predicate_tokens
            ):
                predicate_tokens.remove(root)
        if not predicate_tokens:
            predicate = root.text if root else "utterance"
            modality, polarity = self._proposition_modality(sentence)
            fallback_diagnostics = ["no_reliable_predicate"]
            if root and _is_internal_lexical_fragment(sentence, tokens, root, lexical_spans):
                fallback_diagnostics.append("root_inside_lexical_word")
            proposition = self._record_proposition(
                model,
                propositions,
                sentence=sentence,
                block_index=block_index,
                sentence_index=sentence_index,
                predicate=predicate,
                kind="question" if modality == "question" else "utterance",
                arguments={"text": sentence.strip()},
                modality=modality,
                polarity=polarity,
                parser="stanza",
                confidence=0.55,
                diagnostics=tuple(fallback_diagnostics),
            )
            self._project_generic_observation(proposition, block_index, model, updates)
            return

        # Preserve the order in the source text.  A sentence may contain more
        # than one predicate, for example a main clause plus a subordinate
        # clause; collapsing it to one state would lose information.
        for predicate_token in sorted(predicate_tokens, key=lambda item: item.id):
            arguments: dict[str, str] = {}
            raw_arguments: dict[str, str] = {}
            entity_ids: dict[str, str] = {}
            mention_ids: dict[str, str] = {}
            subject: str | None = None
            role_counts: dict[str, int] = {}
            argument_diagnostics: list[str] = []
            candidate_predicate, candidate_span = predicate_candidates.get(
                predicate_token.id,
                (predicate_token.text, None),
            )
            predicate_fragment_span = (
                candidate_span if candidate_predicate != predicate_token.text else None
            )

            for child in children.get(predicate_token.id, ()):
                role = _argument_role(child)
                if role is None:
                    continue
                if (
                    role == "subject"
                    and predicate_token.text in {"有", "没有"}
                    and _is_vocative_subject(tokens, child, predicate_token)
                ):
                    argument_diagnostics.append("vocative_subject_ignored")
                    continue
                raw_value = _dependency_text(tokens, _dependency_subtree(tokens, child.id))
                if not raw_value:
                    continue
                argument_value, argument_repaired = _dependency_text_excluding_span(
                    sentence,
                    tokens,
                    _dependency_subtree(tokens, child.id),
                    predicate_fragment_span,
                )
                if argument_repaired:
                    argument_diagnostics.append("argument_overlaps_predicate_lexeme")
                normalized_role, normalized_value = self._normalize_argument(role, argument_value)
                candidate_predicate = predicate_candidates.get(
                    predicate_token.id,
                    (predicate_token.text, None),
                )[0]
                if normalized_role == "clause" and candidate_predicate in _OPEN_PREDICATES:
                    normalized_role = "object"
                    argument_diagnostics.append("clause_retyped_as_object")
                role_counts[normalized_role] = role_counts.get(normalized_role, 0) + 1
                role_key = normalized_role if role_counts[normalized_role] == 1 else f"{normalized_role}_{role_counts[normalized_role]}"
                arguments[role_key] = normalized_value
                raw_arguments[role_key] = raw_value
                if normalized_role == "subject" and subject is None:
                    subject = normalized_value
                if normalized_role in {"subject", "object", "indirect_object", "location", "time", "oblique"}:
                    entity_id, mention_id = self._register_proposition_entity(
                        model,
                        entity_cache,
                        normalized_value,
                        self._argument_kind(normalized_role, normalized_value),
                        block_index=block_index,
                        source_text=sentence,
                    )
                    entity_ids[role_key] = entity_id
                    if mention_id:
                        mention_ids[role_key] = mention_id

            if subject is None:
                copula = next(
                    (child for child in children.get(predicate_token.id, ()) if child.relation == "cop"),
                    None,
                )
                # Some Chinese UD parses attach the subject and copula as one
                # token (for example ``门是``).  Recover the visible subject
                # prefix instead of dropping the entire copular proposition.
                if copula and copula.text.endswith("是") and len(copula.text) > 1:
                    subject = copula.text[:-1]
                    arguments["subject"] = subject
                    entity_id, mention_id = self._register_proposition_entity(
                        model,
                        entity_cache,
                        subject,
                        "entity",
                        block_index=block_index,
                        source_text=sentence,
                    )
                    entity_ids["subject"] = entity_id
                    if mention_id:
                        mention_ids["subject"] = mention_id

            if subject is None:
                inherited = _inherited_subject(tokens, predicate_token)
                if inherited is not None:
                    subject, inherited_token = inherited
                    arguments["subject"] = subject
                    entity_id, mention_id = self._register_proposition_entity(
                        model,
                        entity_cache,
                        subject,
                        self._argument_kind("subject", subject),
                        block_index=block_index,
                        source_text=sentence,
                    )
                    entity_ids["subject"] = entity_id
                    if mention_id:
                        mention_ids["subject"] = mention_id
                    argument_diagnostics.append("inherited_subject")

            if (
                predicate_fragment_span is not None
                and predicate_token.relation in {"root", "advcl", "ccomp", "xcomp", "conj"}
                and not _negative_token(predicate_token)
                and not any(
                role in arguments
                for role in {"object", "indirect_object", "location", "oblique", "clause"}
                )
            ):
                recovered_object = _surface_argument_after(sentence, predicate_fragment_span)
                if recovered_object:
                    next_word = next(
                        (
                            (word, word_start, word_end)
                            for word, word_start, word_end in lexical_spans
                            if word_start == predicate_fragment_span[1]
                        ),
                        None,
                    )
                    if next_word is not None:
                        _, next_start, next_end = next_word
                        if any(
                            token.id != predicate_token.id
                            and token.upos in {"VERB", "AUX"}
                            and (
                                token_span := _token_surface_spans(sentence, tokens).get(token.id)
                            ) is not None
                            and token_span[0] < next_end
                            and token_span[1] > next_start
                            for token in tokens
                        ):
                            recovered_object = ""
                if recovered_object:
                    arguments["object"] = recovered_object
                    raw_arguments["object"] = recovered_object
                    entity_id, mention_id = self._register_proposition_entity(
                        model,
                        entity_cache,
                        recovered_object,
                        self._argument_kind("object", recovered_object),
                        block_index=block_index,
                        source_text=sentence,
                    )
                    entity_ids["object"] = entity_id
                    if mention_id:
                        mention_ids["object"] = mention_id
                    argument_diagnostics.append("surface_argument_recovered")

            modality, polarity = self._proposition_modality(sentence)
            if _predicate_is_negated(tokens, predicate_token):
                polarity = "negated"
            predicate, surface_predicate, diagnostics = _normalize_predicate_surface(
                sentence,
                tokens,
                predicate_token,
                lexical_spans,
            )
            diagnostics = tuple(dict.fromkeys((*diagnostics, *argument_diagnostics)))
            if (
                predicate_candidates.get(predicate_token.id, (predicate_token.text, None))[0]
                != predicate_token.text
                and predicate_token.relation != "root"
            ):
                diagnostics = tuple(dict.fromkeys((*diagnostics, "no_reliable_predicate")))
            if predicate_token.text in _SPEECH_PREDICATES or predicate in _SPEECH_PREDICATES:
                kind = "speech"
            elif modality == "question":
                kind = "question"
            elif (
                predicate_token.upos in {"ADJ", "NOUN"}
                and any(child.relation == "cop" for child in children.get(predicate_token.id, ()))
            ) or predicate in {"是", "有", "属于", "位于", "在", "处于", "拥有", "持有"}:
                kind = "property"
            else:
                kind = "event"

            proposition = self._record_proposition(
                model,
                propositions,
                sentence=sentence,
                block_index=block_index,
                sentence_index=sentence_index,
                predicate=predicate,
                kind=kind,
                surface_predicate=surface_predicate,
                subject=subject,
                arguments=arguments,
                raw_arguments=raw_arguments,
                entity_ids=entity_ids,
                mention_ids=mention_ids,
                modality=modality,
                polarity=polarity,
                parser="stanza",
                confidence=0.7 if arguments else 0.5,
                diagnostics=diagnostics,
            )
            self._project_generic_observation(proposition, block_index, model, updates)
            self._project_generic_property(proposition, block_index, model, updates)
            self._project_generic_event(proposition, block_index, model, updates)

    def _extract_conditional_opening(
        self,
        sentence: str,
        block_index: int,
        model: WorldModel,
        updates: list[StateVersion],
    ) -> None:
        # Example: 在你最孤单最无望的时候，有一扇门会在你身边打开。
        match = re.search(
            r"在(?P<condition>[^，,。！？!?]+?)的时候[，,]?(?:有)?"
            r"(?P<object>一扇[^，,。！？!?]*?门|门)"
            r"(?:会|将会|将)(?:在(?P<location>[^，,。！？!?]+?))?"
            r"(?P<verb>打开|开启)",
            sentence,
        )
        if match:
            entity = self._register_entity(model, match.group("object"), "object", sentence)
            condition = match.group("condition") + "的时候"
            self._emit(
                model,
                updates,
                entity=entity,
                attribute="opening_condition",
                value=condition,
                block_index=block_index,
                source_text=sentence,
                mode="conditional",
                kind="rule",
                confidence=0.95,
                entity_kind="object",
            )
            self._emit(
                model,
                updates,
                entity=entity,
                attribute="expected_event",
                value=match.group("verb"),
                block_index=block_index,
                source_text=sentence,
                mode="conditional",
                kind="event",
                confidence=0.95,
                entity_kind="object",
            )
            location = match.group("location")
            if location:
                self._emit(
                    model,
                    updates,
                    entity=entity,
                    attribute="location",
                    value=location,
                    block_index=block_index,
                    source_text=sentence,
                    mode="conditional",
                    kind="relation",
                    confidence=0.8,
                    entity_kind="object",
                )

        # Example: 只有钟声响起时，它才能打开。
        match = re.search(
            r"只有(?P<condition>[^，,。！？!?]+?)(?:时|时候)[，,]?"
            r"(?P<object>它|[^，,。！？!?]+?)(?:才能|才会|可以)(?P<verb>打开|开启)",
            sentence,
        )
        if match:
            entity = self._register_entity(model, match.group("object"), "object", sentence)
            self._emit(
                model,
                updates,
                entity=entity,
                attribute="opening_condition",
                value=match.group("condition") + "时",
                block_index=block_index,
                source_text=sentence,
                mode="conditional",
                kind="rule",
                confidence=0.95,
                entity_kind="object",
            )
            self._emit(
                model,
                updates,
                entity=entity,
                attribute="expected_event",
                value=match.group("verb"),
                block_index=block_index,
                source_text=sentence,
                mode="conditional",
                kind="event",
                confidence=0.95,
                entity_kind="object",
            )

    def _extract_transfer(
        self,
        sentence: str,
        block_index: int,
        model: WorldModel,
        updates: list[StateVersion],
    ) -> None:
        # Example: 楚子航把戒指交给了路明非。
        match = re.search(
            r"(?P<actor>[^，,。！？!?；]+?)(?:把|将)"
            r"(?P<object>[^，,。！？!?；]+?)"
            r"(?:交给|递给|送给)(?:了)?(?P<recipient>[^，,。！？!?；]+)",
            sentence,
        )
        if not match:
            return

        object_entity = self._register_entity(model, match.group("object"), "object", sentence)
        recipient = self._register_entity(model, match.group("recipient"), "person", sentence)
        self._register_entity(model, match.group("actor"), "person", sentence)
        self._emit(
            model,
            updates,
            entity=object_entity,
            attribute="holder",
            value=recipient,
            block_index=block_index,
            source_text=sentence,
            kind="relation",
            confidence=0.98,
            entity_kind="object",
        )

    def _extract_waiting(
        self,
        sentence: str,
        block_index: int,
        model: WorldModel,
        updates: list[StateVersion],
    ) -> None:
        match = re.search(
            rf"(?P<entity>[^，,。！？!?；]+?)(?:等了|等待了)(?P<duration>{self._DURATION_RE})",
            sentence,
        )
        if not match:
            return

        entity = self._register_entity(model, match.group("entity"), "person", sentence)
        self._emit(
            model,
            updates,
            entity=entity,
            attribute="waiting_duration",
            value=match.group("duration"),
            block_index=block_index,
            source_text=sentence,
            kind="property",
            confidence=0.98,
            entity_kind="person",
        )

    def _extract_condition(
        self,
        sentence: str,
        block_index: int,
        model: WorldModel,
        updates: list[StateVersion],
    ) -> None:
        # Example: 在他最衰的那一刻，门开了。
        match = re.search(
            r"在(?P<subject>他|她|它|其)(?P<condition>[^，,。！？!?]+?)的那一刻",
            sentence,
        )
        if not match:
            return

        expected_kind = "object" if match.group("subject") == "它" else "person"
        context = getattr(self, "_active_context", None)
        entity = model.resolve_entity(
            match.group("subject"),
            expected_kind=expected_kind,
            frame_id=context.frame_id if context else DEFAULT_FRAME_ID,
        )
        self._emit(
            model,
            updates,
            entity=entity,
            attribute="condition",
            value=match.group("condition"),
            block_index=block_index,
            source_text=sentence,
            kind="property",
            confidence=0.8 if entity == match.group("subject") else 0.92,
            entity_kind=expected_kind,
        )

    def _extract_opened(
        self,
        sentence: str,
        block_index: int,
        model: WorldModel,
        updates: list[StateVersion],
    ) -> None:
        # Prefer the explicit object form.  It gives the parser a reliable
        # syntactic boundary and avoids treating arbitrary words ending in
        # "开了" (for example "离开了" or "展开了") as an opening event.
        match = re.search(
            r"(?:把|将)(?P<object>[^，,。！？!?；]+?)(?:打开了|开启了)",
            sentence,
        )
        if match:
            object_value = match.group("object")
        else:
            # The short form is accepted only for a noun-like object at a
            # sentence/clause boundary, and only for common openable nouns.
            short_match = re.search(
                r"(?:^|[，,。！？!?；\s])"
                r"(?P<object>[\u4e00-\u9fffA-Za-z0-9]{1,16}?)(?:打开了|开启了|开了)",
                sentence,
            )
            if not short_match:
                return
            object_value = short_match.group("object")
            normalized_object = _normalize_entity(object_value)
            if (
                not _looks_like_openable_entity(normalized_object)
                or normalized_object[-1:] in _NON_OPENING_PREFIXES
            ):
                return

        if not object_value:
            return

        entity = self._register_entity(model, object_value, "object", sentence)
        self._emit(
            model,
            updates,
            entity=entity,
            attribute="status",
            value="已打开",
            block_index=block_index,
            source_text=sentence,
            kind="property",
            confidence=0.98,
            entity_kind="object",
        )

    def _extract_location(
        self,
        sentence: str,
        block_index: int,
        model: WorldModel,
        updates: list[StateVersion],
    ) -> None:
        match = re.search(
            r"(?:把|将)(?P<object>[^，,。！？!?；]+?)(?:放在|放到|带到|拿到)"
            r"(?P<location>[^，,。！？!?；]+)",
            sentence,
        )
        if not match:
            return

        entity = self._register_entity(model, match.group("object"), "object", sentence)
        self._emit(
            model,
            updates,
            entity=entity,
            attribute="location",
            value=match.group("location"),
            block_index=block_index,
            source_text=sentence,
            kind="relation",
            confidence=0.9,
            entity_kind="object",
        )


def extract_state(
    text: str,
    world: WorldModel | None = None,
    *,
    document_id: str = "document",
    projection_rules: Iterable[StateProjectionRule] | None = None,
    include_legacy_patterns: bool | None = None,
    max_blocks: int | None = None,
) -> ExtractionResult:
    """Convenience function for one-shot extraction."""

    return StateExtractor(
        projection_rules=projection_rules,
        include_legacy_patterns=include_legacy_patterns,
    ).extract(
        text,
        world=world,
        document_id=document_id,
        max_blocks=max_blocks,
    )


__all__ = [
    "BlockResult",
    "ContextFrameVersion",
    "DEFAULT_FRAME_ID",
    "DEFAULT_STATE_PROJECTION_RULES",
    "DependencyToken",
    "DocumentContentLine",
    "DocumentCleaningResult",
    "DocumentLineDecision",
    "DocumentStructure",
    "EntityMention",
    "EntityResolutionVersion",
    "EvidenceRecord",
    "ExtractionContext",
    "ExtractionResult",
    "PropositionRecord",
    "SegmentedBlock",
    "SentenceStartAnalysis",
    "StateProjectionRule",
    "StateExtractor",
    "StateVersion",
    "WorldModel",
    "analyze_sentence_start",
    "clean_document_text",
    "extract_state",
    "parse_dependencies",
    "segment_document",
    "segment_text",
]
