from pathlib import Path

import knowledge_base as kb_module
from knowledge_base import KnowledgeBase


def test_inventory_excludes_temporary_and_symlink_escape(tmp_path):
    root = tmp_path / "资料"
    root.mkdir()
    (root / "01_国赛资料模块" / "2019").mkdir(parents=True)
    (root / "01_国赛资料模块" / "2019" / "B047.txt").write_text("约束 敏感性分析", encoding="utf-8")
    (root / "unfinished.qkdownloading").write_text("partial", encoding="utf-8")
    (root / "draft.part").write_text("partial", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("must never be indexed", encoding="utf-8")
    try:
        (root / "escape.txt").symlink_to(outside)
    except (OSError, NotImplementedError):
        pass  # Windows without developer mode; path-boundary test remains below.

    result = KnowledgeBase(str(root)).summary(include_documents=True)
    assert result["source_status"] == "LOCAL_PENDING"
    assert result["valid_count"] == 1
    assert result["temporary_count"] == 2
    assert result["bytes"] == len("约束 敏感性分析".encode("utf-8"))
    assert result["facets"]["modules"]["01_国赛资料模块"] == 1
    assert result["facets"]["years"]["2019"] == 1
    assert all("outside" not in row["path_rel"] for row in result["documents"])


def test_search_and_preview_are_lexical_and_bounded(tmp_path):
    root = tmp_path / "kb"
    (root / "05_模型算法与代码模块").mkdir(parents=True)
    source = root / "05_模型算法与代码模块" / "2020_logistic.py"
    source.write_text("# logistic baseline\nprint('不执行')\n", encoding="utf-8")
    kb = KnowledgeBase(str(root))
    doc = kb.summary(include_documents=True)["documents"][0]
    found = kb.search("logistic", module="05_模型算法", year=2020, top_k=99)
    assert found["results"] and len(found["results"]) <= 20
    assert found["returned_count"] == len(found["results"])
    assert "total_candidates" in found
    row = found["results"][0]
    assert row["doc_id"] == doc["doc_id"]
    assert row["citation_ref"].startswith("kbdoc:")
    assert "logistic" in row["snippet"].lower()
    preview = kb.document(doc["doc_id"], include_preview=True)
    assert preview["path_rel"].endswith(".py")
    assert "不执行" in preview["preview"]
    assert kb.file_path(doc["doc_id"]) == source
    assert kb.file_path("kbdoc_../../etc") is None


def test_missing_root_is_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("GAOJIAO_MATERIALS_ROOT", str(tmp_path / "does-not-exist"))
    result = KnowledgeBase().summary(include_documents=True)
    assert result["source_status"] == "UNAVAILABLE"
    assert result["valid_count"] == 0
    assert result["index_revision"] if "index_revision" in result else True


def test_catalog_promotional_numbers_are_not_inventory_truth(tmp_path):
    root = tmp_path / "pack"
    root.mkdir()
    (root / "00_请先阅读_说明.html").write_text(
        "<div>18,976 个资料文件 · 21.19 GB · 4,943 PDF 文件</div>", encoding="utf-8"
    )
    (root / "one.txt").write_text("真实文件", encoding="utf-8")
    result = KnowledgeBase(str(root)).summary(include_documents=True)
    assert result["catalog_claims"]
    assert result["catalog_consistent"] is False
    assert any("18,976" in number for claim in result["catalog_claims"] for number in claim["promotional_numbers"])
    assert result["valid_count"] == 2


def test_document_and_file_fail_closed_when_source_changes(tmp_path):
    root = tmp_path / "pack"
    root.mkdir()
    source = root / "template.txt"
    source.write_text("原始内容", encoding="utf-8")
    kb = KnowledgeBase(str(root))
    doc_id = kb.summary(include_documents=True)["documents"][0]["doc_id"]
    source.write_text("替换后的内容", encoding="utf-8")
    document = kb.document(doc_id)
    assert document["source_status"] == "SOURCE_CHANGED"
    assert document["extract_status"] == "REINDEX_REQUIRED"
    assert kb.file_path(doc_id) is None


def test_large_document_hash_is_deferred(monkeypatch, tmp_path):
    root = tmp_path / "pack"
    root.mkdir()
    source = root / "large.txt"
    source.write_text("x" * 32, encoding="utf-8")
    monkeypatch.setattr(kb_module, "ON_DEMAND_HASH_LIMIT", 1)
    kb = KnowledgeBase(str(root))
    doc_id = kb.summary(include_documents=True)["documents"][0]["doc_id"]
    document = kb.document(doc_id, include_preview=False)
    assert document["hash_status"] == "DEFERRED_LARGE"
    assert document["sha256"] is None
