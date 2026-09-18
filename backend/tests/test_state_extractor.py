import json
from types import SimpleNamespace

from app.services.memory.state_extractor import (
    DEFAULT_STATE_PROJECTION_RULES,
    PropositionRecord,
    StateProjectionRule,
    StateExtractor,
    WorldModel,
    analyze_sentence_start,
    clean_document_text,
    parse_dependencies,
    segment_text,
)


def test_first_subjectless_sentence_is_joined_to_next_sentence():
    text = "在你最孤单最无望的时候，有一扇门会在你身边打开。路明非等了十八年。"

    assert segment_text(text) == [
        "在你最孤单最无望的时候，有一扇门会在你身边打开。路明非等了十八年。"
    ]


def test_sentence_segmentation_keeps_quoted_dialogue_with_its_attribution():
    text = (
        "“哥哥……”有人在黑暗里轻声地呼喊。\n"
        "“哥哥。”孩子又喊。\n"
        "“好啦！你家住哪？我送你回家！”他翻身坐了起来。"
    )

    assert segment_text(text) == [
        "“哥哥……”有人在黑暗里轻声地呼喊。",
        "“哥哥。”孩子又喊。",
        "“好啦！你家住哪？我送你回家！”他翻身坐了起来。",
    ]


def test_nlp_subject_detection_merges_a_subjectless_sentence_backwards():
    text = "他说。这么安静的。他想。"

    assert segment_text(text) == ["他说。这么安静的。", "他想。"]


def test_dependency_parser_uses_the_subject_phrase_span_not_only_the_first_token():
    def fake_pipeline(_sentence):
        return SimpleNamespace(
            sentences=[
                SimpleNamespace(
                    words=[
                        SimpleNamespace(id=1, text="楚子", lemma="楚子", upos="PROPN", xpos="NNP", head=2, deprel="compound"),
                        SimpleNamespace(id=2, text="航", lemma="航", upos="PROPN", xpos="NNP", head=4, deprel="nsubj"),
                        SimpleNamespace(id=3, text="把", lemma="把", upos="ADP", xpos="BB", head=4, deprel="case"),
                        SimpleNamespace(id=4, text="交给", lemma="交给", upos="VERB", xpos="VV", head=0, deprel="root"),
                        SimpleNamespace(id=5, text="。", lemma="。", upos="PUNCT", xpos=".", head=4, deprel="punct"),
                    ]
                )
            ]
        )

    analysis = analyze_sentence_start("楚子航把戒指交给了路明非。", pipeline=fake_pipeline)

    assert analysis.parser == "stanza"
    assert analysis.has_subject is True
    assert analysis.subject == "楚子航"
    assert analysis.dependency_relation == "nsubj"
    assert [token.text for token in parse_dependencies("楚子航把戒指交给了路明非。", pipeline=fake_pipeline)] == [
        "楚子",
        "航",
        "把",
        "交给",
        "。",
    ]


def test_dependency_parser_rejects_a_leading_adverb_before_a_later_subject():
    def fake_pipeline(_sentence):
        return SimpleNamespace(
            sentences=[
                SimpleNamespace(
                    words=[
                        SimpleNamespace(id=1, text="这么", lemma="这么", upos="ADV", xpos="RB", head=2, deprel="advmod"),
                        SimpleNamespace(id=2, text="安静", lemma="安静", upos="ADJ", xpos="JJ", head=0, deprel="root"),
                        SimpleNamespace(id=3, text="。", lemma="。", upos="PUNCT", xpos=".", head=2, deprel="punct"),
                    ]
                )
            ]
        )

    analysis = analyze_sentence_start("这么安静的。", pipeline=fake_pipeline)

    assert analysis.parser == "stanza"
    assert analysis.has_subject is False
    assert analysis.dependency_relation == "advmod"


def test_state_updates_reuse_existing_entity_and_keep_unchanged_state():
    text = "楚子航把戒指交给了路明非。只有钟声响起时，它才能打开。后来戒指打开了。"

    result = StateExtractor().extract(text)
    state = result.world.current_state()

    assert state["戒指"]["holder"] == "路明非"
    assert state["戒指"]["opening_condition"] == "钟声响起时"
    assert state["戒指"]["status"] == "已打开"
    assert "一枚戒指" not in state

    # The unchanged conditional rule is stored once; the status change is a
    # new version of the same entity's state.
    assert len([item for item in result.world.history if item.entity == "戒指" and item.attribute == "opening_condition"]) == 1
    assert len([item for item in result.world.history if item.entity == "戒指" and item.attribute == "status"]) == 1


def test_an_unchanged_observation_does_not_append_a_duplicate_version():
    world = WorldModel()
    world.upsert(
        entity="门",
        attribute="status",
        value="已打开",
        block_index=0,
        source_text="门开了。",
        entity_kind="object",
    )
    world.upsert(
        entity="一扇门",
        attribute="status",
        value="已打开",
        block_index=1,
        source_text="那扇门仍然开着。",
        entity_kind="object",
    )

    assert len(world.history) == 1
    assert world.current_state()["门"]["status"] == "已打开"


def test_document_cleaner_removes_structural_preamble_without_losing_raw_text():
    raw = (
        "《示例书》\n"
        "作者：甲\n\n"
        "在最孤单的时候，有一扇门会打开。\n"
        "谨以此书献给所有读者！\n"
        "——甲\n\n"
        "序章 白帝城\n\n"
        "门开了。"
    )

    cleaned = clean_document_text(raw)

    assert cleaned.raw_text == raw
    assert cleaned.text == "门开了。"
    assert any(decision.role == "preamble" for decision in cleaned.removed_lines)
    assert any(decision.role == "heading" for decision in cleaned.removed_lines)


def test_document_cleaner_keeps_ordinary_prose_when_no_structure_proves_it_is_metadata():
    raw = "在最孤单的时候，有一扇门会打开。\n路明非等了十八年。"

    cleaned = clean_document_text(raw)

    assert cleaned.text == raw


def test_document_structure_is_preserved_as_context_metadata():
    raw = "《示例》\n序章 白帝城\n甲把门打开了。\n第一章 新场景\n乙离开。"

    cleaned = clean_document_text(raw)

    assert [structure.text for structure in cleaned.structures] == ["《示例》", "序章 白帝城", "第一章 新场景"]
    assert cleaned.content_lines[0].structure_id == "structure:1"
    assert cleaned.content_lines[1].structure_id == "structure:2"


def test_extraction_keeps_evidence_and_separates_states_by_context_frame():
    result = StateExtractor().extract(
        "序章 A\n楚子航把戒指交给了路明非。\n第一章 B\n楚子航把戒指交给了楚子航。"
    )

    assert len(result.world.evidence) == 2
    assert result.blocks[0].frame_id == "document:structure:0"
    assert result.blocks[1].frame_id == "document:structure:1"
    assert result.world.current_state_by_frame()["document:structure:0"]["戒指"]["holder"] == "路明非"
    assert result.world.current_state_by_frame()["document:structure:1"]["戒指"]["holder"] == "楚子航"
    assert result.world.history[-1].evidence_id == result.blocks[1].evidence_id


def test_later_evidence_can_revise_a_context_and_a_provisional_state():
    world = WorldModel()
    world.ensure_frame("scene:1", label="opening", status="unknown")
    first = world.upsert(
        entity="entity:1",
        attribute="identity",
        value="unknown",
        block_index=0,
        source_text="某人出现了。",
        frame_id="scene:1",
        epistemic_status="provisional",
    )
    revised = world.upsert(
        entity="entity:1",
        attribute="identity",
        value="confirmed_identity",
        block_index=1,
        source_text="后来文本明确说明了身份。",
        frame_id="scene:1",
        epistemic_status="confirmed",
    )
    world.upsert_frame(
        frame_id="scene:1",
        label="opening",
        kind="context",
        status="confirmed",
        block_index=1,
        source_text="后来文本明确说明了场景性质。",
        attributes={"layer": "hypothetical"},
    )

    assert first is not None
    assert revised is not None
    assert revised.supersedes_version_id == first.version_id
    assert world.current_frame("scene:1").status == "confirmed"
    assert world.current_state_by_frame()["scene:1"]["entity:1"]["identity"] == "confirmed_identity"


def test_ambiguous_entity_mentions_are_kept_until_later_resolution():
    world = WorldModel()
    first_mention_entity = world.register_entity(
        "他",
        kind="person",
        block_index=0,
        source_text="他出现了。",
        frame_id="scene:1",
    )
    mention_id = world.mentions[-1].mention_id
    world.register_entity("甲", kind="person", frame_id="scene:1")
    world.register_entity("乙", kind="person", frame_id="scene:1")
    ambiguous_entity = world.register_entity(
        "他",
        kind="person",
        block_index=1,
        source_text="他走了。",
        frame_id="scene:1",
    )

    world.resolve_mention(
        mention_id=mention_id,
        entity_id="甲",
        block_index=2,
        source_text="后文明确指出他是甲。",
    )

    assert first_mention_entity == "他"
    assert ambiguous_entity == "他"
    assert world.mentions[-1].resolution_status == "ambiguous"
    assert world.current_mention_resolution(mention_id).entity_id == "甲"


def test_rebinding_a_mention_revises_its_live_state_without_deleting_history():
    world = WorldModel()
    world.upsert(
        entity="他",
        attribute="location",
        value="入口",
        block_index=0,
        source_text="他在入口。",
        frame_id="scene:1",
    )
    mention_id = world.mentions[-1].mention_id

    revised = world.rebind_mention(
        mention_id=mention_id,
        entity_id="甲",
        block_index=1,
        source_text="后文明确指出他是甲。",
    )

    assert revised
    assert len(world.history) == 3
    assert "他" not in world.current_state_by_frame()["scene:1"]
    assert world.current_state_by_frame()["scene:1"]["甲"]["location"] == "入口"
    assert world.history[1].epistemic_status == "retracted"


def test_resolved_proposition_view_tracks_later_reference_resolution():
    world = WorldModel()
    unresolved = world.register_entity(
        "它",
        kind="object",
        block_index=0,
        source_text="它打开了。",
        frame_id="scene:1",
    )
    mention_id = world.mentions[-1].mention_id
    world.record_proposition(
        PropositionRecord(
            proposition_id="proposition:test",
            block_index=0,
            sentence_index=0,
            source_text="它打开了。",
            predicate="打开",
            kind="event",
            subject="它",
            arguments={"subject": "它"},
            entity_ids={"subject": unresolved},
            mention_ids={"subject": mention_id},
            frame_id="scene:1",
        )
    )

    world.resolve_mention(
        mention_id=mention_id,
        entity_id="戒指",
        block_index=3,
        source_text="后文说明它指的是戒指。",
    )

    view = world.current_propositions()[0]
    assert view["entity_ids"]["subject"] == "戒指"
    assert view["mention_resolution_status"]["subject"] == "resolved"


def test_world_model_round_trip_reconstructs_state_and_audit_layers():
    original = StateExtractor().extract(
        "楚子航把戒指交给了路明非。只有钟声响起时，它才能打开。戒指打开了。"
    ).world

    encoded = json.dumps(original.to_dict(), ensure_ascii=False)
    restored = WorldModel.from_dict(json.loads(encoded))

    assert restored.current_state_by_frame() == original.current_state_by_frame()
    assert restored.current_state_by_frame_with_metadata() == original.current_state_by_frame_with_metadata()
    assert [item.to_dict() for item in restored.evidence] == [
        item.to_dict() for item in original.evidence
    ]
    assert [item.to_dict() for item in restored.propositions] == [
        item.to_dict() for item in original.propositions
    ]
    assert restored.current_propositions() == original.current_propositions()


def test_generic_proposition_layer_keeps_events_without_a_domain_rule():
    result = StateExtractor().extract("有人在黑暗里轻声地呼喊。")

    propositions = result.propositions
    assert propositions
    assert any(item.predicate == "呼喊" and item.kind == "speech" for item in propositions)
    assert all(item.evidence_id == result.blocks[0].evidence_id for item in propositions)
    assert result.world.current_state() == {}
    assert len(result.world.current_observations()) == len(propositions)


def test_generic_proposition_layer_keeps_questions_without_asserting_them():
    result = StateExtractor().extract("谁家的小孩跑丢了？")

    assert len(result.propositions) >= 1
    assert any(item.kind == "question" and item.modality == "question" for item in result.propositions)
    assert result.world.current_state() == {}
    assert result.world.current_observations()


def test_generic_copular_property_can_be_projected_into_current_state():
    result = StateExtractor().extract("门是蓝色的。")

    assert result.world.current_state()["门"]["蓝色"] == "true"
    assert result.world.history[-1].mode == "generic-projection"


def test_modality_detection_does_not_treat_every_location_as_a_condition():
    observed = StateExtractor().extract("有人在黑暗里呼喊。")
    conditional = StateExtractor().extract("只有钟声响起时，门才能打开。")

    assert all(item.modality == "asserted" for item in observed.propositions)
    assert any(item.modality == "conditional" for item in conditional.propositions)


def test_generic_proposition_keeps_a_resolved_pronoun_link():
    result = StateExtractor().extract("门打开了。它是蓝色的。")

    blue = next(item for item in result.propositions if item.predicate == "蓝色")
    assert blue.entity_ids["subject"] == "门"
    assert blue.mention_ids["subject"]
    assert result.world.current_state()["门"]["蓝色"] == "true"


def test_generic_location_property_updates_current_state():
    result = StateExtractor().extract("门在房间里。")

    assert result.world.current_state()["门"]["location"] == "房间里"


def test_negated_property_is_preserved_as_a_proposition_without_positive_state():
    result = StateExtractor().extract("这里没有！")

    proposition = result.propositions[0]
    assert proposition.polarity == "negated"
    assert result.world.current_state() == {}


def test_predicate_normalization_keeps_surface_text_and_parse_diagnostics():
    result = StateExtractor().extract("穿越荒原。")

    proposition = result.propositions[0]
    assert proposition.surface_predicate
    assert proposition.source_text == "穿越荒原。"
    assert "no_reliable_predicate" in proposition.diagnostics


def test_argument_normalization_keeps_ba_object_and_raw_dependency_text():
    result = StateExtractor().extract("楚子航把戒指交给了路明非。")

    proposition = next(item for item in result.propositions if item.predicate == "交给")
    assert proposition.arguments["object"] == "戒指"
    assert proposition.raw_arguments["object"] == "把戒指"
    assert proposition.arguments["indirect_object"] == "路明非"


def test_generic_event_effects_update_transfer_opening_and_location_state():
    transfer = StateExtractor().extract("楚子航把戒指交给了路明非。")
    opening = StateExtractor().extract("他打开门。")
    movement = StateExtractor().extract("他走进房间。")
    placement = StateExtractor().extract("他把钥匙放在桌上。")

    assert transfer.world.current_state()["戒指"]["holder"] == "路明非"
    assert transfer.world.history[-1].proposition_id is not None
    assert opening.world.current_state()["门"]["status"] == "已打开"
    assert movement.world.current_state()["他"]["location"] == "房间"
    assert placement.world.current_state()["钥匙"]["location"] == "桌上"


def test_projection_rules_can_be_replaced_without_removing_propositions():
    rule = StateProjectionRule(
        name="speech_signal",
        predicates=("呼喊",),
        effect="property",
        attribute="signal",
        value="active",
        entity_role="subject",
        allowed_kinds=("speech",),
    )

    result = StateExtractor(projection_rules=(rule,)).extract("有人在黑暗里呼喊。")

    assert result.propositions
    speech = next(item for item in result.propositions if item.predicate == "呼喊")
    assert speech.subject is not None
    assert result.world.current_state()[speech.subject]["signal"] == "active"
    assert result.world.history[-1].proposition_id == speech.proposition_id


def test_empty_projection_rules_keep_the_loss_preserving_proposition_layer():
    result = StateExtractor(projection_rules=()).extract("楚子航把戒指交给了路明非。")

    assert result.propositions
    assert result.world.current_state() == {}


def test_conditional_projection_works_without_compatibility_regexes():
    result = StateExtractor(
        projection_rules=DEFAULT_STATE_PROJECTION_RULES,
        include_legacy_patterns=False,
    ).extract("楚子航把戒指交给了路明非。只有钟声响起时，它才能打开。戒指打开了。")

    state = result.world.current_state()
    assert state["戒指"]["holder"] == "路明非"
    assert state["戒指"]["opening_condition"] == "钟声响起时"
    assert state["戒指"]["expected_event"] == "打开"
    assert state["戒指"]["status"] == "已打开"
    assert all(item.proposition_id is not None for item in result.world.history)


def test_extraction_separates_quoted_utterance_from_its_attribution():
    result = StateExtractor().extract(
        "\u201c\u54e5\u54e5\u2026\u2026\u201d\u6709\u4eba\u5728\u9ed1\u6697\u91cc\u8f7b\u58f0\u5730\u547c\u558a\u3002"
    )

    assert any(item.predicate == "\u547c\u558a" and item.subject == "\u4eba" for item in result.propositions)
    assert not any(item.predicate == "\u6709\u4eba" for item in result.propositions)
    assert any(item.source_text == "\u201c\u54e5\u54e5\u2026\u2026\u201d" for item in result.propositions)


def test_question_modality_does_not_leak_from_dialogue_into_narration():
    result = StateExtractor().extract(
        "\u201c\u5582\uff0c\u4f60\u6ca1\u8d70\u554a\uff1f\u4f60\u800d\u6211\u7684\u5427\uff1f\u201d\u4ed6\u60f3\u8bf4\uff0c\u5374\u6ca1\u6709\u8bf4\u3002"
    )

    assert any(item.predicate == "\u8d70" and item.modality == "question" for item in result.propositions)
    assert any(item.predicate == "\u800d" and item.modality == "question" for item in result.propositions)
    assert any(item.predicate == "\u8bf4" and item.modality == "asserted" for item in result.propositions)


def test_surface_parser_recovery_repairs_a_split_predicate_and_object():
    result = StateExtractor().extract("\u7a7f\u8d8a\u8352\u539f\u3002")

    proposition = result.propositions[0]
    assert proposition.predicate == "\u7a7f\u8d8a"
    assert proposition.arguments["object"] == "\u8352\u539f"
    assert "no_reliable_predicate" in proposition.diagnostics


def test_opening_recovery_does_not_turn_aspect_particle_into_an_entity():
    result = StateExtractor().extract("\u95e8\u6253\u5f00\u4e86\u3002")

    assert result.world.current_state()["\u95e8"]["status"] == "\u5df2\u6253\u5f00"
    assert "\u672a\u77e5\u5b9e\u4f53" not in result.world.current_state()


def test_first_and_second_person_pronouns_are_not_bound_by_recency():
    result = StateExtractor().extract(
        "\u4ed6\u4f20\u7ed9\u4ed6\u4e00\u4ef6\u4e1c\u897f\u3002\u4f60\u8bf4\u6211\u3002"
    )

    proposition = next(item for item in result.propositions if item.predicate == "\u8bf4")
    assert proposition.entity_ids["subject"] == "\u4f60"
    assert proposition.entity_ids["object"] == "\u6211"
