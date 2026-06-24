"""ui_status single source of truth (A1–A5).

Covers:
- api.products._resolve_ui_status      (pure derivation matrix, generating timeout)
- api.products._layout_promotion_patch (the ONE promotion decision)
- api.products.product_file_status     (pure read: never persists)
- api.products.reconcile_product_status(the explicit writer: heals drift)
"""

import json
import time
from datetime import datetime, timezone

import pytest

import api.products as products
from api.products import (
    GENERATION_TIMEOUT_SECONDS,
    _layout_promotion_patch,
    _resolve_ui_status,
)

NOW = time.time()


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# --- _resolve_ui_status matrix -------------------------------------------------

@pytest.mark.parametrize(
    "desc, product, entry_generated, kwargs, expect",
    [
        ("chat_only ignores stored failed", {"ui_mode": "chat_only", "ui_status": "failed"}, False, {}, "ready"),
        ("real entry wins", {"ui_mode": "workspace", "ui_status": "empty"}, True, {}, "ready"),
        ("explicit failed beats entry", {"ui_mode": "workspace", "ui_status": "ready"}, True, {"explicit_failed": True}, "failed"),
        ("generating fresh stays generating", {"ui_mode": "workspace", "ui_status": "generating", "generation_started_at": _iso(NOW - 60)}, False, {}, "generating"),
        ("generating times out to failed", {"ui_mode": "workspace", "ui_status": "generating", "generation_started_at": _iso(NOW - GENERATION_TIMEOUT_SECONDS - 5)}, False, {}, "failed"),
        ("generating falls back to updated_at for timeout", {"ui_mode": "workspace", "ui_status": "generating", "updated_at": _iso(NOW - 3600)}, False, {}, "failed"),
        ("generating with no timestamps trusted", {"ui_mode": "workspace", "ui_status": "generating"}, False, {}, "generating"),
        ("turn over without entry is failed", {"ui_mode": "workspace", "ui_status": "generating", "generation_started_at": _iso(NOW - 60)}, False, {"generation_over": True}, "failed"),
        ("turn over empty stored is still failed", {"ui_mode": "workspace", "ui_status": "empty"}, False, {"generation_over": True}, "failed"),
        ("stored failed stays failed", {"ui_mode": "workspace", "ui_status": "failed"}, False, {}, "failed"),
        ("ready but files vanished", {"ui_mode": "workspace", "ui_status": "ready"}, False, {}, "failed"),
        ("ready with unknown entry trusted", {"ui_mode": "workspace", "ui_status": "ready"}, None, {}, "ready"),
        ("empty with unknown entry stays empty", {"ui_mode": "workspace", "ui_status": "empty"}, None, {}, "empty"),
        ("fresh empty", {"ui_mode": "workspace", "ui_status": "empty"}, False, {}, "empty"),
    ],
)
def test_resolve_matrix(desc, product, entry_generated, kwargs, expect):
    got = _resolve_ui_status(product, entry_generated=entry_generated, now=NOW, **kwargs)
    assert got == expect, f"{desc}: expected {expect}, got {got}"


# --- _layout_promotion_patch ----------------------------------------------------

def test_promotion_only_from_chat_center_default():
    assert _layout_promotion_patch(
        ui_mode="workspace", product_layout="chat_center", entry_generated=True, current_canvas_label=""
    ) == {"product_layout": "chat_left_canvas_right", "canvas_label": "Workspace"}


def test_promotion_heals_chat_only_when_real_entry_exists():
    assert _layout_promotion_patch(
        ui_mode="chat_only", product_layout="chat_only", entry_generated=True, current_canvas_label=""
    ) == {
        "ui_mode": "workspace",
        "product_layout": "chat_left_canvas_right",
        "canvas_label": "Workspace",
    }


def test_promotion_never_overrides_explicit_layout():
    # canvas_full was the agent's/user's explicit choice — promotion must not touch it.
    assert _layout_promotion_patch(
        ui_mode="workspace", product_layout="canvas_full", entry_generated=True, current_canvas_label=""
    ) == {}


def test_promotion_keeps_explicit_canvas_label():
    patch = _layout_promotion_patch(
        ui_mode="workspace", product_layout="chat_center", entry_generated=True, current_canvas_label="角色聊天"
    )
    assert "canvas_label" not in patch


def test_promotion_requires_real_entry():
    assert _layout_promotion_patch(
        ui_mode="workspace", product_layout="chat_center", entry_generated=False, current_canvas_label=""
    ) == {}


# --- file_status purity + reconcile persistence ---------------------------------

@pytest.fixture()
def fake_state(tmp_path, monkeypatch):
    """Isolated products state: one custom product, workspace in tmp, no builtins."""
    state_file = tmp_path / "ai_products.json"
    workspace = tmp_path / "ws"
    workspace.mkdir()
    monkeypatch.setattr(products, "PRODUCTS_FILE", state_file)
    monkeypatch.setattr(products, "BUILTIN_PRODUCTS", ())
    monkeypatch.setattr(products, "_register_workspace", lambda *a, **k: None)
    product = {
        "id": "demo",
        "kind": "custom-demo",
        "title": "Demo",
        "ui_mode": "workspace",
        "product_layout": "chat_center",
        "ui_status": "generating",
        "generation_started_at": _iso(NOW - GENERATION_TIMEOUT_SECONDS - 60),
        "workspace_path": str(workspace),
        "preview_entry": "index.html",
        "sessions": [],
    }
    state_file.write_text(json.dumps({"products": [product]}), encoding="utf-8")
    return state_file, workspace


def _stored_status(state_file) -> str:
    return json.loads(state_file.read_text(encoding="utf-8"))["products"][0]["ui_status"]


def test_file_status_is_pure_read(fake_state):
    state_file, _ = fake_state
    before = state_file.read_text(encoding="utf-8")
    status = products.product_file_status("demo")
    # Derived view says failed (generating timed out, no entry)...
    assert status["ui_status"] == "failed"
    # ...but the read NEVER persisted anything.
    assert state_file.read_text(encoding="utf-8") == before


def test_reconcile_persists_timed_out_generating(fake_state):
    state_file, _ = fake_state
    assert _stored_status(state_file) == "generating"
    updated = products.reconcile_product_status("demo")
    assert updated["ui_status"] == "failed"
    assert _stored_status(state_file) == "failed"


def test_reconcile_promotes_layout_when_entry_appears(fake_state):
    state_file, workspace = fake_state
    (workspace / "index.html").write_text("<html><body>real generated UI</body></html>", encoding="utf-8")
    updated = products.reconcile_product_status("demo")
    assert updated["ui_status"] == "ready"
    stored = json.loads(state_file.read_text(encoding="utf-8"))["products"][0]
    assert stored["product_layout"] == "chat_left_canvas_right"
    assert stored["canvas_label"] == "Workspace"


def test_reconcile_promotes_chat_only_when_real_entry_appears(fake_state):
    state_file, workspace = fake_state
    state = json.loads(state_file.read_text(encoding="utf-8"))
    state["products"][0]["ui_mode"] = "chat_only"
    state["products"][0]["product_layout"] = "chat_only"
    state_file.write_text(json.dumps(state), encoding="utf-8")
    (workspace / "index.html").write_text("<html><body>real generated UI</body></html>", encoding="utf-8")

    updated = products.reconcile_product_status("demo")

    assert updated["ui_status"] == "ready"
    stored = json.loads(state_file.read_text(encoding="utf-8"))["products"][0]
    assert stored["ui_mode"] == "workspace"
    assert stored["product_layout"] == "chat_left_canvas_right"
    assert stored["canvas_label"] == "Workspace"


def test_finalize_honors_chat_only_manifest_without_generated_entry(fake_state):
    state_file, workspace = fake_state
    (workspace / "product.json").write_text(
        json.dumps(
            {
                "title": "Writing Coach",
                "desc": "A chat-first writing coach.",
                "source_prompt": "Help me write better in a simple chat box.",
                "ui_mode": "chat_only",
                "product_layout": "chat_only",
                "skills": ["skills"],
                "tools": ["skills"],
            }
        ),
        encoding="utf-8",
    )
    updated = products.finalize_product_generation("demo")
    assert updated["ui_status"] == "ready"
    assert updated["ui_mode"] == "chat_only"
    assert updated["product_layout"] == "chat_only"
    assert _stored_status(state_file) == "ready"


def test_reconcile_is_idempotent(fake_state):
    state_file, _ = fake_state
    products.reconcile_product_status("demo")
    first = state_file.read_text(encoding="utf-8")
    products.reconcile_product_status("demo")
    assert state_file.read_text(encoding="utf-8") == first
