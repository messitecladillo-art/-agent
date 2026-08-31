"""Regression tests for knowledge-base extractability and retrieval boundaries."""

from pathlib import Path

try:
    from knowledge_base import KnowledgeBase
except ImportError:  # pragma: no cover - package-style collection
    from backend.knowledge_base import KnowledgeBase


def test_summary_reports_body_extractability_without_scanning_bodies(tmp_path):
    root = tmp_path / "pack"
    (root / "资料").mkdir(parents=True)
    (root / "资料" / "native.txt").write_text("native text", encoding="utf-8")
    # Invalid PDF bytes are intentional: inventory must classify by extension
    # and remain metadata-only until a bounded extraction is requested.
    (root / "资料" / "scan.pdf").write_bytes(b"not a real pdf")
    (root / "资料" / "legacy.doc").write_bytes(b"old office binary")
    (root / "资料" / "picture.png").write_bytes(b"png placeholder")
    (root / "资料" / "archive.zip").write_bytes(b"zip placeholder")

    summary = KnowledgeBase(str(root)).summary()
    extractability = summary["extractability"]

    assert extractability["text_or_pdf_or_openxml"] == 2
    assert extractability["metadata_only"] == 3
    assert extractability["legacy_office"] == 1
    assert extractability["ocr_candidates"] == 1
    assert extractability["unsupported_extensions"] == {".zip": 1}
    assert extractability["unsupported_extension_count"] == 1
    assert extractability["extractability_rate"] == 0.4
    # Inventory does not pretend to have read bodies.
    assert extractability["quality_counts"]["not_examined"] == 2
    assert summary["extractability_rate"] == 0.4


def test_search_exposes_metadata_and_bounded_body_counts(tmp_path):
    root = tmp_path / "pack"
    module = root / "05_模型算法与代码模块"
    module.mkdir(parents=True)
    body_only = module / "01_alpha.txt"
    body_only.write_text("正文中出现 bodyneedle，文件名没有这个词。", encoding="utf-8")
    metadata_hit = module / "02_metadata-only.txt"
    metadata_hit.write_text("正文没有目标词。", encoding="utf-8")
    unknown = module / "03_unknown.bin"
    unknown.write_bytes(b"bodyneedle is not inspected in binary")

    kb = KnowledgeBase(str(root))
    result = kb.search("bodyneedle", top_k=5, with_preview=True)

    assert result["metadata_candidates"] == 3
    assert result["metadata_matches"] == 0
    assert result["body_examined"] == 2  # text files only; binary is metadata-only
    assert result["body_matched"] == 1
    assert result["metadata_only_results"] == 0
    assert result["ranking_mode"] == "bounded_body_fallback_lexical"
    assert result["retrieval_boundary"]["body_examined_limit"] == 12
    assert result["retrieval_boundary"]["exhaustive"] is False
    assert result["deduplication"]["duplicates_removed"] == 0
    assert result["results"][0]["match_source"] == "body"
    assert result["results"][0]["body_examined"] is True
    assert result["results"][0]["body_matched"] is True
    assert result["results"][0]["text_quality"] == "native_text"

    metadata = kb.search("metadata-only", top_k=5)
    assert metadata["metadata_candidates"] == 3
    assert metadata["metadata_matches"] == 1
    assert metadata["body_examined"] >= 1
    assert metadata["body_matched"] == 0
    assert metadata["metadata_only_results"] == 1
    assert metadata["ranking_mode"] == "metadata_then_bounded_body_lexical"
    assert metadata["results"][0]["match_source"] == "metadata"


def test_empty_search_is_explicit_metadata_browse(tmp_path):
    root = tmp_path / "pack"
    root.mkdir()
    (root / "one.txt").write_text("body", encoding="utf-8")
    (root / "two.png").write_bytes(b"asset")

    result = KnowledgeBase(str(root)).search("", top_k=1)
    assert result["ranking_mode"] == "metadata_browse"
    assert result["body_examined"] == 0
    assert result["body_matched"] == 0
    assert result["metadata_candidates"] == 2
    assert result["metadata_only_results"] == 1
    assert result["results"][0]["match_source"] == "metadata"
