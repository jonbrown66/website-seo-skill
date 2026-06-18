from search_visibility_auditor.adapters.source_project import SourceProjectAdapter


def test_source_project_target_candidates_ignore_generated_reports(tmp_path):
    app_dir = tmp_path / "app"
    reports_dir = tmp_path / "reports"
    app_dir.mkdir()
    reports_dir.mkdir()
    (tmp_path / "package.json").write_text('{"dependencies":{"next":"15.0.0"}}', encoding="utf-8")
    (app_dir / "layout.tsx").write_text('export const metadata = { openGraph: { url: "https://product.example" } }', encoding="utf-8")
    (reports_dir / "audit.json").write_text('{"url":"https://old-report.example"}', encoding="utf-8")

    result = SourceProjectAdapter().run({"source_path": str(tmp_path), "url": "https://product.example"})

    urls = [item["url"] for item in result.raw["target_candidates"]]
    assert "https://product.example" in urls
    assert "https://old-report.example" not in urls


def test_source_project_target_candidates_skip_malformed_urls(tmp_path):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (tmp_path / "package.json").write_text('{"dependencies":{"next":"15.0.0"}}', encoding="utf-8")
    (app_dir / "layout.tsx").write_text('const bad = "http://[$"; const good = "https://product.example";', encoding="utf-8")

    result = SourceProjectAdapter().run({"source_path": str(tmp_path), "url": "https://product.example"})

    assert result.status == "ok"
    assert [item["url"] for item in result.raw["target_candidates"]] == ["https://product.example"]
