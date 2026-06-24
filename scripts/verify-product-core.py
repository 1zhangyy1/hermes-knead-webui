#!/usr/bin/env python3
"""Fast product-model smoke checks for release verification.

These checks intentionally avoid a live browser/server and avoid pytest so the
root `pnpm verify` command can protect Knead's product invariants in a plain
Python environment.
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBUI_ROOT = ROOT / "apps" / "webui"
sys.path.insert(0, str(WEBUI_ROOT))

from api import products  # noqa: E402
from api import product_context  # noqa: E402


ORIGINAL_BUILTINS = copy.deepcopy(products.BUILTIN_PRODUCTS)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def isolate_storage(root: Path, *, builtins=None, save_workspaces=None) -> None:
    products.PRODUCTS_FILE = root / "state" / "ai_products.json"
    products.PRODUCT_DRAFTS_DIR = root / "state" / "product_drafts"
    products.BUILTIN_PRODUCTS_DIR = root / "repo" / "products"
    products.PRODUCTS_DIR = root / "state" / "products"
    products.BUILTIN_PRODUCTS = tuple(copy.deepcopy(item) for item in (builtins if builtins is not None else ORIGINAL_BUILTINS))
    products.load_workspaces = lambda: []
    products.save_workspaces = save_workspaces or (lambda _items: None)


def restore_repo_products() -> None:
    products.BUILTIN_PRODUCTS = tuple(copy.deepcopy(item) for item in ORIGINAL_BUILTINS)
    products.BUILTIN_PRODUCTS_DIR = ROOT / "products"
    products.PRODUCTS_DIR = ROOT / ".hermes-home" / "webui" / "products"
    products.PRODUCT_DRAFTS_DIR = ROOT / ".hermes-home" / "webui" / "product_drafts"
    products.PRODUCTS_FILE = ROOT / ".hermes-home" / "webui" / "ai_products.json"


def test_draft_publish_boundary() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        isolate_storage(root, builtins=())

        created = products.create_product_draft(
            {"title": "Tiny Timer", "prompt": "A simple 25 minute focus timer"}
        )
        draft = created["draft"]
        workspace = root / "state" / "product_drafts" / draft["id"]
        manifest_path = workspace / "product.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        check(manifest["draft"] is True, "draft manifest must stay marked as a draft")
        check(manifest["draft_status"] == "clarifying", "new drafts should start clarifying")
        listed = products.list_products()["products"]
        check(all(item["id"] != draft["id"] for item in listed), "drafts must not appear in the product shelf")

        manifest.update(
            {
                "title": "Focus Timer",
                "desc": "Runs a tiny focus timer.",
                "draft_status": "ready",
                "draft_ready_reason": "Specific enough for a first usable focus timer.",
                "ui_mode": "chat_only",
                "product_layout": "chat_only",
            }
        )
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        published = products.publish_product_draft({"workspace_path": str(workspace), "if_ready": True})
        product = published["product"]
        product_dir = root / "state" / "products" / product["id"]

        check(published["published"] is True, "ready draft should publish")
        check(published["ready_reason"] == "Specific enough for a first usable focus timer.",
              "publish response should carry the Creator ready reason")
        check(published["draft"]["id"] == draft["id"], "publish response should include the source draft")
        check(product_dir.is_dir(), "published products must live in runtime products dir")
        check(not (root / "repo" / "products" / product["id"]).exists(), "publish must not write generated products into repo products")

        repeated = products.publish_product_draft({"workspace_path": str(workspace), "if_ready": True})
        check(repeated.get("already_published") is True, "publishing a draft twice should be idempotent")
        check(repeated["ready_reason"] == "Specific enough for a first usable focus timer.",
              "repeated publish should preserve the ready reason")
        check(repeated["product"]["id"] == product["id"], "repeat publish should return the same product")


def test_created_product_storage_boundary() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        isolate_storage(root, builtins=())
        created = products.create_product(
            {
                "title": "Reading Coach",
                "source_prompt": "Help me read papers with short summaries",
                "ui_mode": "chat_only",
                "product_layout": "chat_only",
            }
        )
        product = created["product"]
        check(product["builtin"] is False, "created product should not be builtin")
        check(
            product["workspace_path"] == str((root / "state" / "products" / product["id"]).resolve()),
            "created product workspace should use runtime products dir",
        )
        check(not (root / "repo" / "products" / product["id"]).exists(), "created product must not dirty repo products")


def test_builtin_products_are_loaded_read_only() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        builtin_dir = root / "repo" / "products" / "source-product"
        builtin_dir.mkdir(parents=True)
        manifest_path = builtin_dir / "product.json"
        manifest_before = '{"sentinel": true}\n'
        manifest_path.write_text(manifest_before, encoding="utf-8")

        isolate_storage(
            root,
            builtins=(
                {
                    "id": "source-product",
                    "kind": "source-product",
                    "title": "Source Product",
                    "avatar": "S",
                    "desc": "A built-in source product.",
                    "source_prompt": "Keep this built-in read-only during registry load.",
                    "product_type": "general",
                    "ui_mode": "chat_only",
                    "product_layout": "chat_only",
                    "builtin": True,
                },
            ),
        )

        listed = products.list_products()["products"]
        check(any(item["id"] == "source-product" for item in listed), "built-in product should load into registry")
        check(manifest_path.read_text(encoding="utf-8") == manifest_before, "loading built-ins must not rewrite product.json")
        check(not (builtin_dir / "index.html").exists(), "loading built-ins must not seed source product files")


def test_product_scope_and_tool_boundaries() -> None:
    restore_repo_products()
    game = products.get_product("ai-otome")
    check(game is not None, "AI Otome builtin product should exist")
    workspace = game["workspace_path"]

    builder = product_context.product_context_from_request(
        {
            "product_id": "ai-otome",
            "product_scope": "product_builder",
            "product_scope_explicit": True,
            "message": "Make the scene controls clearer.",
        },
        workspace=workspace,
    )
    check(builder["line"] == "build", "builder scope should resolve to build line")
    for tool in ("skills", "file", "terminal", "code_execution"):
        check(tool in builder["tools"], f"builder scope missing {tool}")
    check("image_gen" in builder["tools"], "builder scope should keep product-specific tools")
    check("product.json" in builder["files"], "builder scope should expose product file manifest")

    usage = product_context.product_context_from_request(
        {
            "product_id": "ai-otome",
            "product_scope": "product_usage",
            "product_scope_explicit": True,
            "message": "Talk to Mira.",
        },
        workspace="/tmp/knead-task-workspace",
    )
    check(usage["line"] == "use", "usage scope should resolve to use line")
    check("file" not in usage["tools"], "usage scope should not get file editing by default")
    check("terminal" not in usage["tools"], "usage scope should not get terminal by default")

    inferred = product_context.infer_product_scope("Move the notes panel right", "product_usage", explicit=True)
    check(inferred == "product_usage", "explicit usage scope must not be flipped by regex fallback")


def test_shell_product_id_owns_task_assignment() -> None:
    source = (WEBUI_ROOT / "static" / "product-shell-runtime.js").read_text(encoding="utf-8")
    fn_pos = source.find("function assistantTaskBelongsToCurrentAssistant")
    check(fn_pos >= 0, "assistantTaskBelongsToCurrentAssistant should exist")
    product_pos = source.find("const productId", fn_pos)
    resolver_pos = source.find("_assistantKindForProductId(productId)", fn_pos)
    legacy_pos = source.find("const assignedKind", fn_pos)
    check(product_pos >= 0 and resolver_pos >= 0, "product_id branch should resolve product ownership")
    check(legacy_pos < 0 or resolver_pos < legacy_pos, "product_id ownership must run before legacy assistant assignment")


def test_creator_sessions_are_explicitly_marked() -> None:
    shell = (WEBUI_ROOT / "static" / "product-shell-runtime.js").read_text(encoding="utf-8")
    messages = (WEBUI_ROOT / "static" / "messages.js").read_text(encoding="utf-8")
    ui = (WEBUI_ROOT / "static" / "ui.js").read_text(encoding="utf-8")
    sessions = (WEBUI_ROOT / "static" / "sessions.js").read_text(encoding="utf-8")
    model = (WEBUI_ROOT / "api" / "session_model.py").read_text(encoding="utf-8")

    check("creatorDraft:" in shell, "Creator session creation should pass explicit draft metadata")
    check("options&&options.creatorDraft" in sessions, "newSession should send creatorDraft metadata")
    check("self.creator_draft" in model, "Session should persist creator_draft metadata")
    check("S.session.creator_draft" in shell, "Creator draft UI state should recover from persisted session metadata")
    check("_syncCurrentCreatorDraftFromStatus(data)" in shell, "Creator draft status refresh should sync back into the session")
    check("appendCreatorDraftReadyCard(data)" in shell, "Creator ready state should surface an in-chat Add to shelf card")
    check("creator-publish-draft" in messages and "action==='creator-publish-draft'" in ui,
          "Creator ready card should have a publish action wired to the UI handler")
    check("draft_ready_reason" in shell, "Creator instruction should require a ready reason when marking drafts ready")


def test_creator_instruction_is_structured_not_user_text() -> None:
    messages = (WEBUI_ROOT / "static" / "messages.js").read_text(encoding="utf-8")
    runtime_prompt = (WEBUI_ROOT / "api" / "streaming_runtime_prompt.py").read_text(encoding="utf-8")
    chat_routes = (WEBUI_ROOT / "api" / "chat_routes.py").read_text(encoding="utf-8")

    check("agent_instruction:agentInstruction||undefined" in messages, "Creator instruction should be sent as a structured chat/start field")
    check("if(hiddenAgentInstruction&&msgText)" not in messages, "Creator instruction must not be appended to the visible user message")
    check("agent_instruction_from_request" in chat_routes, "chat/start should parse structured agent_instruction")
    check("agent_instruction" in runtime_prompt and "runtime_parts.append(str(agent_instruction).strip())" in runtime_prompt,
          "runtime prompt should merge structured agent_instruction into ephemeral system context")


def test_runtime_branding_does_not_expose_old_name() -> None:
    checked_paths = [
        WEBUI_ROOT / "api" / "products.py",
        WEBUI_ROOT / "api" / "product_context.py",
        WEBUI_ROOT / "static" / "product-runtime.js",
        WEBUI_ROOT / "static" / "product-bridge-sdk.js",
        WEBUI_ROOT / "static" / "sessions.js",
        WEBUI_ROOT / "static" / "desktop.html",
        WEBUI_ROOT / "static" / "style.css",
    ]
    for path in checked_paths:
        content = path.read_text(encoding="utf-8")
        check("Next AI" not in content, f"{path.relative_to(ROOT)} should not expose old product branding")


def main() -> None:
    test_draft_publish_boundary()
    test_created_product_storage_boundary()
    test_builtin_products_are_loaded_read_only()
    test_product_scope_and_tool_boundaries()
    test_shell_product_id_owns_task_assignment()
    test_creator_sessions_are_explicitly_marked()
    test_creator_instruction_is_structured_not_user_text()
    test_runtime_branding_does_not_expose_old_name()
    print("Product core smoke passed")


if __name__ == "__main__":
    main()
