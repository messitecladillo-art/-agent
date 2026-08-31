import hashlib

from problem_contract import build_problem_contract


def test_dynamic_subproblems_and_observed_fields():
    result = build_problem_contract("问题一：根据数据预测 y。\n问题二：在约束 x<=10 下优化路径，并验证结果。", ["problem.pdf:p1"])
    assert result["status"] == "DRAFT_UNVERIFIED"
    assert len(result["subproblems"]) == 2
    assert result["subproblems"][0]["variables"]["claim_class"] == "observed"
    assert "预测" in result["subproblems"][0]["delivery_verbs"]["value"]
    assert result["subproblems"][1]["constraints"]["value"] != ["unknown"]


def test_revision_is_deterministic_and_suggestions_are_hypotheses():
    text = "Q1: optimize allocation using data; validate sensitivity."
    a = build_problem_contract(text, ["a"])
    b = build_problem_contract(text, ["a"])
    expected = "sha256:" + hashlib.sha256('{"source_refs":["a"],"text":"Q1: optimize allocation using data; validate sensitivity."}'.encode()).hexdigest()
    assert a["revision"] == b["revision"] == expected
    assert a["archetype_cue_suggestions"][0]["claim_class"] == "hypothesis"


def test_missing_evidence_is_explicitly_unknown():
    result = build_problem_contract("这是一个没有结构化提示的题面。")
    q = result["subproblems"][0]
    assert q["constraints"]["value"] == ["unknown"]
    assert q["data_prompts"]["value"] == ["unknown"]
    assert q["validation_prompts"]["value"] == ["unknown"]
