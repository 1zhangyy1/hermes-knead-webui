"""Unit tests for Next AI product scope/line resolution (no live server needed).

Covers the 用/调 (use/build) model wired in across:
- api.models.Session.product_line          (use/build line tag, back-compat)
- api.product_context.infer_product_scope  (explicit scope authoritative; regex only as fallback)
- api.product_context.product_context_from_request   (line derived from final scope; line-aware workspace guard)
- api.product_context.product_context_request_body   (session line is the authoritative scope default)

These guard the boundary that the regex must NOT override an explicit scope, and that
the build line (which writes the product canvas) stays pinned to the product workspace
while the use line is free to run elsewhere.
"""

import pathlib

from api.models import Session
from api.product_context import (
    infer_product_scope,
    product_context_from_request,
    product_context_request_body,
    product_ephemeral_prompt,
)
from api.products import get_product

_BUILTIN = "ppt-designer"


class _FakeSession:
    """Minimal stand-in for api.models.Session for request-body restoration."""

    def __init__(self, **kw):
        self.product_id = _BUILTIN
        self.product_scope = None
        self.product_intent = None
        self.product_line = None
        self.messages = ["prior turn"]
        self.context_messages = []
        self.pending_user_message = None
        self.__dict__.update(kw)


# --- api.models.Session.product_line -----------------------------------------

def test_session_product_line_roundtrip(tmp_path):
    s = Session(workspace=str(tmp_path), product_id=_BUILTIN, product_line="build")
    assert s.product_line == "build"
    assert s.compact().get("product_line") == "build"


def test_session_product_line_defaults_to_use(tmp_path):
    s = Session(workspace=str(tmp_path), product_id=_BUILTIN)
    assert s.compact().get("product_line") == "use"


def test_session_product_line_rejects_garbage(tmp_path):
    s = Session(workspace=str(tmp_path), product_id=_BUILTIN, product_line="garbage")
    assert s.product_line is None
    assert s.compact().get("product_line") == "use"


def test_session_without_product_omits_line(tmp_path):
    # Non-product sessions must not gain product fields (back-compat).
    assert "product_line" not in Session(workspace=str(tmp_path)).compact()


# --- infer_product_scope ------------------------------------------------------

def test_explicit_usage_is_not_flipped_by_regex():
    # "把讲稿固定右边" matches the builder regex, but an explicit toggle wins.
    assert infer_product_scope("把讲稿固定右边", "product_usage", explicit=True) == "product_usage"


def test_regex_fallback_flips_usage_when_not_explicit():
    assert infer_product_scope("把讲稿固定右边", "product_usage", explicit=False) == "product_builder"


def test_explicit_builder_is_preserved():
    assert infer_product_scope("帮我改这一页内容", "product_builder", explicit=True) == "product_builder"


def test_plain_chat_stays_usage():
    assert infer_product_scope("随便聊聊天气", "product_usage", explicit=False) == "product_usage"


def test_unknown_requested_scope_falls_back_to_usage():
    assert infer_product_scope("随便聊聊", "not_a_scope", explicit=True) == "product_usage"


# --- product_context_from_request: line derivation + workspace guard ----------

def test_from_request_builder_derives_build_line():
    ctx = product_context_from_request(
        {"product_id": _BUILTIN, "product_scope": "product_builder",
         "product_scope_explicit": True, "message": "调整界面"}
    )
    assert ctx and ctx["line"] == "build"


def test_from_request_usage_derives_use_line():
    ctx = product_context_from_request(
        {"product_id": _BUILTIN, "product_scope": "product_usage",
         "product_scope_explicit": True, "message": "做个汇报 PPT"}
    )
    assert ctx and ctx["line"] == "use"


def test_build_line_rejects_mismatched_workspace():
    import pytest
    pw = get_product(_BUILTIN)["workspace_path"]
    assert pw  # sanity
    with pytest.raises(ValueError):
        product_context_from_request(
            {"product_id": _BUILTIN, "product_scope": "product_builder",
             "product_scope_explicit": True, "message": "改界面"},
            workspace="/tmp/not-the-product-dir",
        )


def test_build_line_accepts_product_workspace():
    pw = get_product(_BUILTIN)["workspace_path"]
    ctx = product_context_from_request(
        {"product_id": _BUILTIN, "product_scope": "product_builder",
         "product_scope_explicit": True, "message": "改界面"},
        workspace=pw,
    )
    assert ctx["line"] == "build"


def test_use_line_allows_separate_workspace():
    # The use line must be free to run in its own (non-product) workspace.
    ctx = product_context_from_request(
        {"product_id": _BUILTIN, "product_scope": "product_usage",
         "product_scope_explicit": True, "message": "做个汇报 PPT"},
        workspace="/tmp/some-task-workspace",
    )
    assert ctx["line"] == "use"


# --- product_context_request_body: session line is authoritative default ------

def test_build_session_continuation_stays_builder():
    body = product_context_request_body({}, _FakeSession(product_line="build"), "把讲稿固定右边")
    assert body["product_scope"] == "product_builder"
    assert body["product_scope_explicit"] is True


def test_use_session_continuation_stays_usage_even_with_edit_words():
    body = product_context_request_body({}, _FakeSession(product_line="use"), "帮我改这一页")
    assert body["product_scope"] == "product_usage"
    assert body["product_scope_explicit"] is True


def test_legacy_session_without_line_uses_prior_behavior():
    # Old sessions have no product_line; with existing turns they default to usage.
    body = product_context_request_body({}, _FakeSession(product_line=None), "随便聊")
    assert body["product_scope"] == "product_usage"


def test_explicit_body_scope_is_not_overridden_by_session_line():
    # If the request already carries a scope, the session-line default must not clobber it.
    body = product_context_request_body(
        {"product_scope": "product_builder"}, _FakeSession(product_line="use"), "改界面"
    )
    assert body["product_scope"] == "product_builder"


# --- chat_only adjustment guard (product_ephemeral_prompt) --------------------

def test_chat_only_builder_gets_identity_only_guard():
    prompt = product_ephemeral_prompt(
        {"title": "通用 AI", "scope": "product_builder", "ui_mode": "chat_only",
         "product_layout": "chat_only"}
    )
    assert "Chat-only product adjustment" in prompt
    assert "NOT generating index.html" in prompt


def test_canvas_builder_has_no_chat_only_guard():
    prompt = product_ephemeral_prompt(
        {"title": "PPT 设计师", "scope": "product_builder", "ui_mode": "workspace",
         "product_layout": "chat_left_canvas_right"}
    )
    assert "Chat-only product adjustment" not in prompt


def test_chat_only_usage_has_no_builder_guard():
    prompt = product_ephemeral_prompt(
        {"title": "通用 AI", "scope": "product_usage", "ui_mode": "chat_only",
         "product_layout": "chat_only"}
    )
    assert "Chat-only product adjustment" not in prompt


# --- productize suggestion (chat_only usage) ----------------------------------

def test_chat_only_usage_gets_productize_suggestion_protocol():
    prompt = product_ephemeral_prompt(
        {"title": "通用 AI", "scope": "product_usage", "ui_mode": "chat_only",
         "product_layout": "chat_only"}
    )
    assert "NEXT_AI_SUGGEST_PRODUCT" in prompt
    assert "Only emit it when the thing is genuinely reusable" in prompt


def test_canvas_usage_has_no_productize_suggestion():
    # A specialized canvas product (PPT) should not nudge to create another product.
    prompt = product_ephemeral_prompt(
        {"title": "PPT 设计师", "scope": "product_usage", "ui_mode": "workspace",
         "product_layout": "chat_left_canvas_right"}
    )
    assert "NEXT_AI_SUGGEST_PRODUCT" not in prompt


def test_chat_only_builder_has_no_productize_suggestion():
    # Adjusting the chat-only product is not a usage turn; no productize nudge.
    prompt = product_ephemeral_prompt(
        {"title": "通用 AI", "scope": "product_builder", "ui_mode": "chat_only",
         "product_layout": "chat_only"}
    )
    assert "NEXT_AI_SUGGEST_PRODUCT" not in prompt


# --- Builder Agent: strong toolset + file manifest + distinct prompt -----------
# AI Otome declares only a light use toolset (skills + image_gen). The Shape/Build
# line must upgrade to the platform builder toolset so it can read/write product files.
_GAME = "ai-otome"


def test_builder_line_upgrades_to_strong_toolset():
    pw = get_product(_GAME)["workspace_path"]
    ctx = product_context_from_request(
        {"product_id": _GAME, "product_scope": "product_builder",
         "product_scope_explicit": True, "message": "把按钮改大点"},
        workspace=pw,
    )
    assert ctx["line"] == "build"
    # strong product-engineering tools present...
    for t in ("file", "terminal", "code_execution", "skills"):
        assert t in ctx["tools"], f"builder missing {t}: {ctx['tools']}"
    # ...and the product's own tool is still unioned on top.
    assert "image_gen" in ctx["tools"]


def test_use_line_keeps_product_weak_toolset():
    ctx = product_context_from_request(
        {"product_id": _GAME, "product_scope": "product_usage",
         "product_scope_explicit": True, "message": "陪我聊聊"},
        workspace="/tmp/some-task-workspace",
    )
    assert ctx["line"] == "use"
    # Use line cannot touch product files: no file/terminal tools.
    assert "file" not in ctx["tools"]
    assert "terminal" not in ctx["tools"]
    assert ctx["tools"] == ["skills", "image_gen"]


def test_builder_line_includes_file_manifest():
    pw = get_product(_GAME)["workspace_path"]
    ctx = product_context_from_request(
        {"product_id": _GAME, "product_scope": "product_builder",
         "product_scope_explicit": True, "message": "改界面"},
        workspace=pw,
    )
    assert ctx.get("files"), "builder context should carry a file manifest"
    assert "product.json" in ctx["files"]


def test_use_line_has_no_file_manifest():
    ctx = product_context_from_request(
        {"product_id": _GAME, "product_scope": "product_usage",
         "product_scope_explicit": True, "message": "陪我聊聊"},
        workspace="/tmp/some-task-workspace",
    )
    assert ctx.get("files") == []


def test_builder_prompt_is_engineer_not_persona():
    prompt = product_ephemeral_prompt(
        {"title": "AI Otome", "scope": "product_builder", "ui_mode": "workspace",
         "product_layout": "canvas_full", "files": ["app.js", "product.json"],
         "tools": ["skills", "file", "terminal", "code_execution", "image_gen"]}
    )
    assert "product builder" in prompt
    assert "Files you own" in prompt
    assert "You are running" not in prompt  # must not frame builder as the product runtime


def test_use_prompt_is_product_runtime_readonly():
    prompt = product_ephemeral_prompt(
        {"title": "AI Otome", "scope": "product_usage", "ui_mode": "workspace",
         "product_layout": "canvas_full", "tools": ["skills", "image_gen"]}
    )
    assert "You are running" in prompt
    assert "READ-ONLY" in prompt
    assert "Knead's product builder" not in prompt
