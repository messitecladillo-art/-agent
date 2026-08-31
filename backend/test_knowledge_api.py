"""HTTP contract tests for the local, read-only knowledge-base adapter."""

from pathlib import Path

from fastapi.testclient import TestClient

try:  # pytest from the repository root
    import app as api
    from knowledge_base import KnowledgeBase
except ImportError:  # pragma: no cover - package-style collection
    from backend import app as api
    from backend.knowledge_base import KnowledgeBase


def test_project_scoped_knowledge_routes_are_bounded(tmp_path, monkeypatch):
    root = tmp_path / "pack"
    source_dir = root / "06_论文写作与备赛模块"
    source_dir.mkdir(parents=True)
    source = source_dir / "论文模板与写作规范.md"
    source.write_text("摘要、模型假设、符号说明、敏感性分析与局限性。", encoding="utf-8")
    (root / "unfinished.qkdownloading").write_text("partial", encoding="utf-8")
    previous = api.knowledge_base
    monkeypatch.setattr(api, "knowledge_base", KnowledgeBase(str(root)))
    try:
        client = TestClient(api.app)
        summary = client.get(f"/api/projects/{api.PROJECT_ID}/knowledge/summary")
        assert summary.status_code == 200
        body = summary.json()
        assert body["valid_count"] == 1
        assert body["temporary_count"] == 1
        assert "documents" not in body  # summary is intentionally compact
        result = client.get(f"/api/projects/{api.PROJECT_ID}/knowledge/search", params={"q": "敏感性分析", "with_preview": "true"})
        assert result.status_code == 200
        hit = result.json()["results"][0]
        assert hit["citation_ref"].startswith("kbdoc:")
        doc_id = hit["doc_id"]
        document = client.get(f"/api/projects/{api.PROJECT_ID}/knowledge/documents/{doc_id}")
        assert document.status_code == 200
        assert "敏感性分析" in document.json()["document"]["preview"]
        opened = client.get(f"/api/projects/{api.PROJECT_ID}/knowledge/documents/{doc_id}/file")
        assert opened.status_code == 200
        assert opened.content.startswith("摘要".encode("utf-8"))
        context = client.get(f"/api/projects/{api.PROJECT_ID}/knowledge/context", params={"q": "敏感性分析", "extension": "md"})
        assert context.status_code == 200
        assert context.json()["items"][0]["citation_ref"] == hit["citation_ref"]
        assert context.json()["usage_note"]
        alias = client.get("/api/kb/search", params={"q": "敏感性分析", "extension": ".md", "top_k": 1})
        assert alias.status_code == 200 and alias.json()["results"]
        assert client.get("/api/projects/not-this-project/knowledge/summary").status_code == 404
        assert client.get(f"/api/projects/{api.PROJECT_ID}/knowledge/documents/kbdoc_../../file").status_code == 404
    finally:
        monkeypatch.setattr(api, "knowledge_base", previous)
