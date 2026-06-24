import json

from api import products


def test_create_product_draft_is_not_registered_product(tmp_path, monkeypatch):
    monkeypatch.setattr(products, "PRODUCT_DRAFTS_DIR", tmp_path / "drafts")
    monkeypatch.setattr(products, "PRODUCTS_FILE", tmp_path / "ai_products.json")
    monkeypatch.setattr(products, "PRODUCTS_DIR", tmp_path / "products")

    result = products.create_product_draft(
        {
            "title": "Tiny Timer",
            "prompt": "A simple 25 minute focus timer",
        }
    )

    draft = result["draft"]
    workspace = tmp_path / "drafts" / draft["id"]
    manifest = json.loads((workspace / "product.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert draft["workspace_path"] == str(workspace.resolve())
    assert draft["original_title"] == "Tiny Timer"
    assert manifest["draft"] is True
    assert manifest["draft_status"] == "clarifying"
    assert manifest["title"] == "Tiny Timer"
    assert manifest["source_prompt"] == "A simple 25 minute focus timer"
    assert manifest["ui_mode"] == "chat_only"

    listed = products.list_products()["products"]
    assert all(item["id"] != draft["id"] for item in listed)


def test_publish_product_draft_registers_real_product(tmp_path, monkeypatch):
    monkeypatch.setattr(products, "PRODUCT_DRAFTS_DIR", tmp_path / "drafts")
    monkeypatch.setattr(products, "PRODUCTS_FILE", tmp_path / "ai_products.json")
    monkeypatch.setattr(products, "PRODUCTS_DIR", tmp_path / "products")
    monkeypatch.setattr(products, "BUILTIN_PRODUCTS", ())
    monkeypatch.setattr(products, "load_workspaces", lambda: [])
    saved_workspaces = []
    monkeypatch.setattr(products, "save_workspaces", lambda items: saved_workspaces.extend(items))

    created = products.create_product_draft({"title": "Placeholder AI", "prompt": "hello"})
    workspace = tmp_path / "drafts" / created["draft"]["id"]
    manifest_path = workspace / "product.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "title": "Article AI",
            "desc": "Turns a topic into a structured article.",
            "ui_mode": "canvas",
            "product_layout": "canvas",
            "draft_status": "ready",
            "updated_at": "2026-06-18T08:00:00Z",
            "suggestions": ["Write about React Server Components"],
        }
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (workspace / "index.html").write_text("<!doctype html><title>Article AI</title>", encoding="utf-8")

    published = products.publish_product_draft(
        {
            "workspace_path": str(workspace),
            "original_title": "Placeholder AI",
            "if_ready": True,
        }
    )

    product = published["product"]
    draft = published["draft"]
    product_dir = tmp_path / "products" / product["id"]
    stored_manifest = json.loads((product_dir / "product.json").read_text(encoding="utf-8"))

    assert published["published"] is True
    assert draft["id"] == created["draft"]["id"]
    assert draft["workspace_path"] == str(workspace.resolve())
    assert draft["title"] == "Article AI"
    assert product["title"] == "Article AI"
    assert product["ui_mode"] == "workspace"
    assert product["product_layout"] == "canvas_full"
    assert product["ui_status"] == "ready"
    assert (product_dir / "index.html").is_file()
    assert "draft" not in stored_manifest
    assert stored_manifest["suggestions"] == [["Write about React Server Components", "Write about React Server"]]
    assert any(item["path"] == str(product_dir.resolve()) for item in saved_workspaces)

    repeated = products.publish_product_draft(
        {
            "workspace_path": str(workspace),
            "if_ready": True,
        }
    )
    assert repeated["published"] is True
    assert repeated["already_published"] is True
    assert repeated["draft"]["id"] == draft["id"]
    assert repeated["product"]["id"] == product["id"]


def test_publish_product_draft_if_ready_waits_for_ready_status(tmp_path, monkeypatch):
    monkeypatch.setattr(products, "PRODUCT_DRAFTS_DIR", tmp_path / "drafts")
    monkeypatch.setattr(products, "PRODUCTS_FILE", tmp_path / "ai_products.json")
    monkeypatch.setattr(products, "PRODUCTS_DIR", tmp_path / "products")
    monkeypatch.setattr(products, "BUILTIN_PRODUCTS", ())

    created = products.create_product_draft({"title": "Placeholder AI", "prompt": "hello"})
    workspace = tmp_path / "drafts" / created["draft"]["id"]
    manifest_path = workspace / "product.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "title": "Article AI",
            "desc": "Turns a topic into a structured article.",
            "draft_status": "clarifying",
        }
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    result = products.publish_product_draft(
        {
            "workspace_path": str(workspace),
            "original_title": "Placeholder AI",
            "if_ready": True,
        }
    )

    assert result["published"] is False
    assert result["not_ready"] is True
    assert result["ready_reason"] == ""
    assert not (tmp_path / "products" / "article-ai").exists()


def test_publish_product_draft_requires_explicit_ready_status_even_after_edits(tmp_path, monkeypatch):
    monkeypatch.setattr(products, "PRODUCT_DRAFTS_DIR", tmp_path / "drafts")
    monkeypatch.setattr(products, "PRODUCTS_FILE", tmp_path / "ai_products.json")
    monkeypatch.setattr(products, "PRODUCTS_DIR", tmp_path / "products")
    monkeypatch.setattr(products, "BUILTIN_PRODUCTS", ())

    created = products.create_product_draft({"title": "Placeholder AI", "prompt": "hello"})
    workspace = tmp_path / "drafts" / created["draft"]["id"]
    manifest_path = workspace / "product.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "title": "Article AI",
            "desc": "Turns a topic into a structured article.",
            "suggestions": ["Draft an outline"],
        }
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    status = products.product_draft_status({"workspace_path": str(workspace)})
    result = products.publish_product_draft({"workspace_path": str(workspace), "if_ready": True})

    assert status["ready"] is False
    assert status["not_ready_reason"] == "Creator is still shaping this AI. Keep chatting until it marks the draft ready."
    assert status["ready_reason"] == ""
    assert result["published"] is False
    assert result["not_ready"] is True
    assert result["not_ready_reason"] == "Creator is still shaping this AI. Keep chatting until it marks the draft ready."
    assert not (tmp_path / "products" / "article-ai").exists()


def test_publish_product_draft_rejects_ready_generic_placeholder_name(tmp_path, monkeypatch):
    monkeypatch.setattr(products, "PRODUCT_DRAFTS_DIR", tmp_path / "drafts")
    monkeypatch.setattr(products, "PRODUCTS_FILE", tmp_path / "ai_products.json")
    monkeypatch.setattr(products, "PRODUCTS_DIR", tmp_path / "products")
    monkeypatch.setattr(products, "BUILTIN_PRODUCTS", ())

    created = products.create_product_draft({"prompt": "hello"})
    workspace = tmp_path / "drafts" / created["draft"]["id"]
    manifest_path = workspace / "product.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "title": "New AI",
            "desc": "A friendly helper.",
            "draft_status": "ready",
            "draft_ready_reason": "The draft is usable.",
        }
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    status = products.product_draft_status({"workspace_path": str(workspace)})
    result = products.publish_product_draft({"workspace_path": str(workspace), "if_ready": True})

    assert status["ready"] is False
    assert status["not_ready_reason"] == "Creator still needs to name this AI before it can be added to the shelf."
    assert result["published"] is False
    assert result["not_ready"] is True
    assert result["not_ready_reason"] == "Creator still needs to name this AI before it can be added to the shelf."
    assert not (tmp_path / "products" / "new-ai").exists()


def test_publish_product_draft_rejects_ready_title_that_is_still_original_request(tmp_path, monkeypatch):
    monkeypatch.setattr(products, "PRODUCT_DRAFTS_DIR", tmp_path / "drafts")
    monkeypatch.setattr(products, "PRODUCTS_FILE", tmp_path / "ai_products.json")
    monkeypatch.setattr(products, "PRODUCTS_DIR", tmp_path / "products")
    monkeypatch.setattr(products, "BUILTIN_PRODUCTS", ())

    created = products.create_product_draft({"title": "你好", "prompt": "你好"})
    workspace = tmp_path / "drafts" / created["draft"]["id"]
    manifest_path = workspace / "product.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "title": "你好",
            "desc": "A friendly helper.",
            "draft_status": "ready",
            "draft_ready_reason": "The draft is usable.",
        }
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    status = products.product_draft_status(
        {"workspace_path": str(workspace), "original_title": "你好"}
    )
    result = products.publish_product_draft(
        {"workspace_path": str(workspace), "original_title": "你好", "if_ready": True}
    )

    assert status["ready"] is False
    assert status["not_ready_reason"] == "Creator still needs to turn the original request into a product name."
    assert result["published"] is False
    assert result["not_ready"] is True
    assert result["not_ready_reason"] == "Creator still needs to turn the original request into a product name."
    assert not (tmp_path / "products" / "你好").exists()


def test_product_draft_status_reports_ready_without_publishing(tmp_path, monkeypatch):
    monkeypatch.setattr(products, "PRODUCT_DRAFTS_DIR", tmp_path / "drafts")
    monkeypatch.setattr(products, "PRODUCTS_FILE", tmp_path / "ai_products.json")
    monkeypatch.setattr(products, "PRODUCTS_DIR", tmp_path / "products")
    monkeypatch.setattr(products, "BUILTIN_PRODUCTS", ())

    created = products.create_product_draft({"title": "Placeholder AI", "prompt": "hello"})
    workspace = tmp_path / "drafts" / created["draft"]["id"]

    first = products.product_draft_status({"workspace_path": str(workspace)})
    assert first["ready"] is False
    assert first["published"] is False

    manifest_path = workspace / "product.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "title": "Article AI",
            "desc": "Turns a topic into a structured article.",
            "draft_status": "ready",
            "draft_ready_reason": "Specific enough for a first usable writing helper.",
        }
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    ready = products.product_draft_status({"workspace_path": str(workspace)})
    assert ready["ready"] is True
    assert ready["ready_reason"] == "Specific enough for a first usable writing helper."
    assert ready["published"] is False
    assert ready["draft"]["title"] == "Article AI"
    assert ready["draft"]["ready_reason"] == "Specific enough for a first usable writing helper."
    assert not (tmp_path / "products" / "article-ai").exists()


def test_publish_product_draft_returns_ready_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(products, "PRODUCT_DRAFTS_DIR", tmp_path / "drafts")
    monkeypatch.setattr(products, "PRODUCTS_FILE", tmp_path / "ai_products.json")
    monkeypatch.setattr(products, "PRODUCTS_DIR", tmp_path / "products")
    monkeypatch.setattr(products, "BUILTIN_PRODUCTS", ())
    monkeypatch.setattr(products, "load_workspaces", lambda: [])
    monkeypatch.setattr(products, "save_workspaces", lambda items: None)

    created = products.create_product_draft({"title": "Placeholder AI", "prompt": "hello"})
    workspace = tmp_path / "drafts" / created["draft"]["id"]
    manifest_path = workspace / "product.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "title": "Article AI",
            "desc": "Turns a topic into a structured article.",
            "draft_status": "ready",
            "draft_ready_reason": "User confirmed the article workflow.",
        }
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    published = products.publish_product_draft({"workspace_path": str(workspace), "if_ready": True})
    repeated = products.publish_product_draft({"workspace_path": str(workspace), "if_ready": True})

    assert published["ready_reason"] == "User confirmed the article workflow."
    assert published["draft"]["ready_reason"] == "User confirmed the article workflow."
    assert repeated["ready_reason"] == "User confirmed the article workflow."
