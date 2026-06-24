import copy

from api import products


def _isolate_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(products, "PRODUCTS_FILE", tmp_path / "state" / "ai_products.json")
    monkeypatch.setattr(products, "PRODUCT_DRAFTS_DIR", tmp_path / "state" / "product_drafts")
    monkeypatch.setattr(products, "BUILTIN_PRODUCTS_DIR", tmp_path / "repo" / "products")
    monkeypatch.setattr(products, "PRODUCTS_DIR", tmp_path / "state" / "products")
    monkeypatch.setattr(products, "load_workspaces", lambda: [])
    monkeypatch.setattr(products, "save_workspaces", lambda _items: None)
    monkeypatch.setattr(products, "BUILTIN_PRODUCTS", (copy.deepcopy(products.BUILTIN_PRODUCTS[0]),))


def _write_builtin_source(tmp_path, product_id="general"):
    product_dir = tmp_path / "repo" / "products" / product_id
    product_dir.mkdir(parents=True)
    manifest = '{"source": true}\n'
    index = "<!doctype html><title>General AI</title>\n"
    (product_dir / "product.json").write_text(manifest, encoding="utf-8")
    (product_dir / "index.html").write_text(index, encoding="utf-8")
    return product_dir, manifest, index


def test_builtin_examples_live_in_repo_products_dir(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    product_dir, manifest_before, _index_before = _write_builtin_source(tmp_path)

    listed = products.list_products()["products"]
    general = next(item for item in listed if item["id"] == "general")

    assert general["builtin"] is True
    assert general["workspace_path"] == str((tmp_path / "repo" / "products" / "general").resolve())
    assert (tmp_path / "repo" / "products" / "general" / "product.json").is_file()
    assert (product_dir / "product.json").read_text(encoding="utf-8") == manifest_before


def test_created_products_live_in_runtime_products_dir(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)

    result = products.create_product(
        {
            "title": "Tiny Timer",
            "source_prompt": "A small focus timer",
            "ui_mode": "chat_only",
            "product_layout": "chat_only",
        }
    )

    product = result["product"]
    assert product["builtin"] is False
    assert product["workspace_path"] == str((tmp_path / "state" / "products" / product["id"]).resolve())
    assert (tmp_path / "state" / "products" / product["id"] / "product.json").is_file()
    assert not (tmp_path / "repo" / "products" / product["id"]).exists()


def test_direct_builtin_preview_ensures_builtin_registry(tmp_path, monkeypatch):
    _isolate_storage(tmp_path, monkeypatch)
    _write_builtin_source(tmp_path)

    preview = products.preview_product_file("general")

    assert preview == (tmp_path / "repo" / "products" / "general" / "index.html").resolve()
    assert preview.is_file()
