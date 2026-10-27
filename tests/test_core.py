import random

import pytest

from ccst import generator
from ccst.objectives import InvalidChapter, chapter_path, load_chapter, validate_chapter
from ccst.schema import GeneratedQuestion


@pytest.mark.parametrize("bad", [0, 14, -1, "1", "../x", 1.0, True, None])
def test_chapter_allowlist_rejects(bad):
    with pytest.raises(InvalidChapter):
        validate_chapter(bad)


def test_chapter_path_is_fixed_pattern():
    assert chapter_path(6).name == "CCST_Ch06.md"


@pytest.mark.parametrize("n", range(1, 14))
def test_every_chapter_parses(n):
    ch = load_chapter(n)
    assert ch.objectives
    assert all(o.id.startswith(f"C{n:02d}-") for o in ch.objectives.values())
    assert all(o.discriminator for o in ch.objectives.values())


def test_ch1_has_48_objectives():
    assert len(load_chapter(1).objectives) == 48


def _question(**over):
    base = {
        "objectives": ["C01-46"],
        "type": "single",
        "angle": "neighbor-discrimination",
        "difficulty": 2,
        "stem": "A visitor slips through a badge door behind an employee who never notices. What is this?",
        "options": [
            {"key": "A", "text": "Tailgating", "rationale": "Correct: the employee did not know.", "role": "best"},
            {"key": "B", "text": "Piggybacking", "rationale": "Requires the employee's consent.", "role": "related"},
            {"key": "C", "text": "Shoulder surfing", "rationale": "Visual observation, no entry.", "role": "related"},
            {"key": "D", "text": "Vishing", "rationale": "Voice-based phishing.", "role": "wrong"},
        ],
        "answer": ["A"],
        "explanation": "No knowledge or consent from the authorized person means tailgating.",
        "discriminator_tested": "Knowledge or consent of the authorized person.",
    }
    base.update(over)
    return GeneratedQuestion.model_validate(base)


def _target(obj="C01-46"):
    return generator.Target(obj, "neighbor-discrimination", "single")


def test_valid_question_passes():
    assert generator.check(_question(), _target(), load_chapter(1), []) == []


def test_answer_key_must_exist():
    q = _question(answer=["E"])
    assert any("subset" in p for p in generator.check(q, _target(), load_chapter(1), []))


def test_unknown_objective_rejected():
    q = _question(objectives=["C01-99"])
    probs = generator.check(q, generator.Target("C01-99", "x", "single"), load_chapter(1), [])
    assert any("unknown objective" in p for p in probs)


def test_wrong_primary_objective_rejected():
    assert any("assigned" in p for p in generator.check(_question(), _target("C01-47"), load_chapter(1), []))


def test_multi_needs_choose_count():
    q = _question(type="multi", answer=["A", "B"])
    assert any("how many" in p for p in generator.check(q, _target(), load_chapter(1), []))
    q2 = _question(type="multi", answer=["A", "B"], stem=_question().stem + " (Choose two.)")
    assert not any("multi" in p for p in generator.check(q2, _target(), load_chapter(1), []))


def test_letter_reference_rejected():
    q = _question(explanation="Option A is right because no consent was given.")
    assert any("letter" in p for p in generator.check(q, _target(), load_chapter(1), []))


def test_near_duplicate_rejected():
    q = _question()
    seen = [generator.content_words(q)]
    assert any("duplicate" in p for p in generator.check(q, _target(), load_chapter(1), seen))


def test_templated_stem_with_different_options_is_not_duplicate():
    # Ch3 set 2 false positive: identical "Which statement ... is NOT true?" stems, different options.
    a = _question(stem="Which statement about tailgating is NOT true?")
    b = _question(stem="Which statement about tailgating is NOT true?", options=[
        {"key": "A", "text": "Requires the employee's consent", "rationale": "False: that is piggybacking."},
        {"key": "B", "text": "Uses a badge-controlled entrance", "rationale": "True."},
        {"key": "C", "text": "Is a physical social engineering technique", "rationale": "True."},
        {"key": "D", "text": "Can be stopped by a one-person turnstile", "rationale": "True."},
    ])
    assert not any("duplicate" in p for p in generator.check(b, _target(), load_chapter(1), [generator.content_words(a)]))


def test_lowercase_article_is_not_a_letter_reference():
    # Ch3 set 2 false positive: "the SYN-ACK answers a SYN".
    q = _question(explanation="The employee never answers a challenge, so the visitor follows unnoticed: tailgating.")
    assert not any("letter" in p for p in generator.check(q, _target(), load_chapter(1), []))
    q2 = _question(explanation="Answer A is right because there was no consent.")
    assert any("letter" in p for p in generator.check(q2, _target(), load_chapter(1), []))


def test_shuffle_keeps_answer_mapping():
    q = _question()
    for seed in range(20):
        s = generator.shuffle_options(q, random.Random(seed))
        correct = [o.text for o in s.options if o.key in s.answer]
        assert correct == ["Tailgating"]
        assert [o.key for o in s.options] == ["A", "B", "C", "D"]


def test_targets_avoid_previous_angle():
    ch = load_chapter(1)
    targets = generator.plan_targets(ch, [], 10, random.Random(1))
    assert len({t.objective for t in targets}) == 10


def test_repair_adds_choose_count():
    q = generator.repair(_question(type="multi", answer=["A", "B"]))
    assert q.stem.endswith("(Choose two.)")
    assert not any("multi" in p for p in generator.check(q, _target(), load_chapter(1), []))


def test_off_objective_question_rejected():
    # Labelled whaling (C01-45) but never mentions it: the Phase 1 pilot failure.
    q = _question(objectives=["C01-45"])
    probs = generator.check(q, _target("C01-45"), load_chapter(1), [])
    assert any("never mentions its objective" in p for p in probs)


def test_discriminator_copy_of_explanation_rejected():
    q = _question(discriminator_tested=_question().explanation)
    assert any("repeats" in p for p in generator.check(q, _target(), load_chapter(1), []))


# ---- v2 surface-cue checks --------------------------------------------

def _opts(*texts, roles=("best", "related", "partial", "wrong")):
    return [{"key": chr(65 + i), "text": t, "rationale": "Because.", "role": r} for i, (t, r) in enumerate(zip(texts, roles))]


def _cues(q):
    return generator.cue_problems(q)


def test_long_answer_is_rejected():
    q = _question(options=_opts("A person follows an employee through the secured door without the employee knowing",
                                "Piggybacking", "Shoulder surfing", "Vishing"))
    assert any("longer" in p for p in _cues(q))


def test_short_answer_among_long_distractors_is_rejected():
    q = _question(options=_opts("Tailgating", "Entering behind an employee who holds the door open on purpose",
                                "Watching a user type a PIN on the keypad by the entrance door",
                                "Calling the help desk while pretending to be a new starter"))
    assert any("shorter" in p or "vary" in p for p in _cues(q))


def test_absolutes_only_in_distractors_are_rejected():
    q = _question(options=_opts("Tailgating", "Always piggybacking", "Never shoulder surfing", "Vishing"))
    assert any("absolute" in p for p in _cues(q))
    q2 = _question(options=_opts("Only tailgating", "Always piggybacking", "Shoulder surfing", "Vishing"))
    assert not any("absolute" in p for p in _cues(q2))


def test_answer_echoing_the_stem_is_rejected():
    q = _question(options=_opts("Visitor following through the badge door", "Guest admitted with the holder's consent",
                                "Watching someone type a PIN at a keypad", "Caller impersonating the help desk staff"))
    assert any("repeats the stem" in p for p in _cues(q))


def test_roles_are_required_and_must_match_the_answer():
    q = _question(options=[{**o, "role": None} for o in _opts("Tailgating", "Piggybacking", "Shoulder surfing", "Vishing")])
    assert any("needs a role" in p for p in _cues(q))
    q2 = _question(options=_opts("Tailgating", "Piggybacking", "Shoulder surfing", "Vishing",
                                 roles=("related", "best", "partial", "wrong")))
    assert any("exactly the options with role 'best'" in p for p in _cues(q2))


def test_partial_option_needs_a_qualifier_in_the_stem():
    plain = _question(options=_opts("Tailgating", "Piggybacking", "Shoulder surfing", "Vishing"))
    assert any("partial" in p for p in _cues(plain))
    best = _question(stem="Which term BEST describes a visitor slipping through a badge door behind an unaware employee?",
                     options=_opts("Tailgating", "Piggybacking", "Shoulder surfing", "Vishing"))
    assert _cues(best) == []


def test_exhibit_line_limit():
    q = _question(exhibit="\n".join(f"line {i}" for i in range(40)))
    assert any("exhibit" in p for p in generator.check(q, _target(), load_chapter(1), []))
    assert not generator.check(_question(exhibit="Oct 21 10:02 sshd: Failed password"), _target(), load_chapter(1), [])


def test_non_strict_skips_cue_checks():
    q = _question(options=[{**o, "role": None} for o in _opts("Tailgating", "Piggybacking", "Shoulder surfing", "Vishing")])
    assert generator.check(q, _target(), load_chapter(1), [], strict=False) == []
    assert generator.check(q, _target(), load_chapter(1), [], strict=True)


def test_audit_bands_flag_a_skewed_pool():
    from ccst.audit import cue_failures
    even = {"single": 80, "multi": 20, "answer_longest": 20, "answer_shortest": 20, "multi_answers_are_longest": 2,
            "absolute_only_in_distractors": 0, "answer_echoes_stem_most": 4}
    assert cue_failures(even) == []
    skewed = {**even, "answer_longest": 54, "answer_shortest": 4}  # the v1 pattern: answer usually longest
    assert {f.split()[0] for f in cue_failures(skewed)} == {"answer_longest", "answer_shortest"}


def test_truncated_json_raises():
    with pytest.raises(ValueError):
        generator.parse_items('{"questions": [{"stem": "cut off')
