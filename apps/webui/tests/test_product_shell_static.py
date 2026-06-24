from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PRODUCT_SHELL = ROOT / "apps" / "webui" / "static" / "product-shell-runtime.js"
PRODUCT_STORE = ROOT / "apps" / "webui" / "static" / "product-store.js"
MESSAGES = ROOT / "apps" / "webui" / "static" / "messages.js"
ROUTES = ROOT / "apps" / "webui" / "api" / "routes.py"
SESSION_ROUTES = ROOT / "apps" / "webui" / "api" / "session_routes.py"
INDEX = ROOT / "apps" / "webui" / "static" / "index.html"
UI = ROOT / "apps" / "webui" / "static" / "ui.js"


def _function_body(source: str, name: str) -> str:
    marker = f"function {name}"
    start = source.index(marker)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[brace + 1:index]
    raise AssertionError(f"{name} body not found")


def test_product_sessions_are_filtered_by_product_id_before_legacy_assignment():
    source = PRODUCT_SHELL.read_text(encoding="utf-8")
    body = _function_body(source, "assistantTaskBelongsToCurrentAssistant")

    product_id_pos = body.index("const productId")
    kind_lookup_pos = body.index("_assistantKindForProductId(productId)")
    legacy_assignment_pos = body.index("const assignedKind")

    assert product_id_pos < kind_lookup_pos < legacy_assignment_pos
    assert "return productKind === _assistantKey()" in body


def test_creator_instruction_is_sent_as_structured_runtime_context():
    messages = MESSAGES.read_text(encoding="utf-8")
    shell = PRODUCT_SHELL.read_text(encoding="utf-8")

    assert "agent_instruction:agentInstruction||undefined" in messages
    assert "if(hiddenAgentInstruction&&msgText)" not in messages
    assert "`${msgText}\\n\\n${hiddenAgentInstruction}`" not in messages
    assert "_nextAiPendingAgentInstruction" in shell
    assert "agentInstruction: _creatorDraftInstruction" in shell


def test_creator_draft_status_survives_reload_via_session_metadata():
    shell = PRODUCT_SHELL.read_text(encoding="utf-8")
    session_routes = SESSION_ROUTES.read_text(encoding="utf-8")
    payload_start = shell.index("function _currentCreatorDraftPayload")
    payload_end = shell.index("function _currentCreatorDraftStatus", payload_start)
    payload_body = shell[payload_start:payload_end]
    sync_body = _function_body(shell, "_syncCurrentCreatorDraftFromStatus")

    assert "S.session.creator_draft" in payload_body
    assert "sessionDraft && sessionDraft.workspace_path" in payload_body
    assert "sessionDraft && sessionDraft.id" in payload_body
    assert "sessionDraft && (sessionDraft.original_title || sessionDraft.originalTitle)" in payload_body
    assert "sessionDraft && sessionDraft.title" in payload_body
    assert "S.session.creator_draft =" in sync_body
    assert "previousOriginalTitle" in sync_body
    assert "original_title: previousOriginalTitle" in sync_body
    assert "_syncCurrentCreatorDraftFromStatus(data)" in shell
    assert '"original_title"' in session_routes


def test_creator_ready_has_chat_card_and_publish_action():
    shell = PRODUCT_SHELL.read_text(encoding="utf-8")
    messages = MESSAGES.read_text(encoding="utf-8")
    ui = (ROOT / "apps" / "webui" / "static" / "ui.js").read_text(encoding="utf-8")

    assert "function appendCreatorDraftReadyCard" in messages
    assert "creator-publish-draft" in messages
    assert "appendCreatorDraftReadyCard(data)" in shell
    assert "removeCreatorDraftStatusCards(draftId)" in shell
    assert "action==='creator-publish-draft'" in ui
    assert "publishCreatorDraft({silent:false})" in ui


def test_creator_visible_state_copy_is_explicit():
    shell = PRODUCT_SHELL.read_text(encoding="utf-8")
    phase_body = _function_body(shell, "_creatorDraftPhase")
    task_header_body = _function_body(shell, "_syncTaskHeaderStatus")
    task_ui_body = _function_body(shell, "syncAssistantTaskUi")

    assert "Draft in progress" in phase_body
    assert "Add to shelf" in phase_body
    assert "Added" in phase_body
    assert "creatorDraftPhase.chatLabel" in task_header_body
    assert "creatorDraftPhase.shelfLabel" in task_header_body
    assert "creatorDraftPhase.composer" in task_ui_body
    assert "publishCreatorDraftIfReady" not in shell


def test_shape_it_opens_product_builder_session_before_adjusting():
    shell = PRODUCT_SHELL.read_text(encoding="utf-8")
    ensure_start = shell.index("async function ensureCurrentProductBuilderSession")
    adjust_start = shell.index("async function setCurrentProductAdjustMode")
    toggle_start = shell.index("function toggleCurrentProductAdjustMode")
    chat_panel_start = shell.index("function setCurrentProductChatPanelMode", toggle_start)
    ensure_body = shell[ensure_start:adjust_start]
    adjust_body = shell[adjust_start:toggle_start]
    toggle_body = shell[toggle_start:chat_panel_start]

    assert "_currentSessionIsProductBuilderLine(object)" in ensure_body
    assert "await newSession(false, {" in ensure_body
    assert "workspace: object.workspacePath || ''" in ensure_body
    assert "productId: object.productId" in ensure_body
    assert "productScope: 'product_builder'" in ensure_body
    assert "productTaskTitle: taskTitle" in ensure_body
    assert "await ensureCurrentProductBuilderSession(object, options)" in adjust_body
    assert "document.body.dataset.nextAiProductAdjust = next ? 'open' : 'closed'" in adjust_body
    assert "void setCurrentProductAdjustMode" in toggle_body


def test_creator_instruction_requires_ready_reason():
    shell = PRODUCT_SHELL.read_text(encoding="utf-8")
    instruction_body = _function_body(shell, "_creatorDraftInstruction")

    assert "draft_ready_reason" in instruction_body
    assert "Only set draft_status=\"ready\"" in instruction_body
    assert "Add to shelf" in instruction_body
    assert "The host publishes the AI only when draft_status is ready" not in instruction_body


def test_creator_starter_kit_does_not_keyword_classify_product_types():
    shell = PRODUCT_SHELL.read_text(encoding="utf-8")
    starter_body = _function_body(shell, "_assistantStarterKit")

    for snippet in (
        "const isPpt",
        "const isPitch",
        "const isSales",
        "const isResearch",
        "const isData",
        "const isImage",
    ):
        assert snippet not in starter_body


def test_knead_one_create_does_not_frontend_classify_or_name_products():
    shell = PRODUCT_SHELL.read_text(encoding="utf-8")
    store = PRODUCT_STORE.read_text(encoding="utf-8")
    create_start = shell.index("async function createProductFromPrompt")
    create_end = shell.index("function _isCreatorDraftWorkspace", create_start)
    create_body = shell[create_start:create_end]
    register_body = _function_body(shell, "_registerCustomAssistant")

    assert '"New AI"' in create_body or "'New AI'" in create_body
    assert "source_prompt: text" in create_body
    assert "_assistantDraftFromPrompt" not in shell
    assert "_assistantTitleFromPrompt" not in shell
    assert "_assistantNaturalTitleFromRolePhrase" not in shell
    assert "_assistantRolePhraseFromPrompt" not in shell
    assert "imageLike" not in register_body
    assert "_assistantDefaultCapabilities" not in store


def test_creator_draft_api_routes_are_registered_with_error_boundaries():
    routes = ROUTES.read_text(encoding="utf-8")

    assert '"/api/product-drafts/create"' in routes
    assert '"/api/products/draft/create"' in routes
    assert 'create_product_draft(body)' in routes

    assert '"/api/product-drafts/status"' in routes
    assert '"/api/products/draft/status"' in routes
    assert 'product_draft_status(body)' in routes

    assert '"/api/product-drafts/publish"' in routes
    assert '"/api/products/draft/publish"' in routes
    assert 'publish_product_draft(body)' in routes

    assert 'except FileNotFoundError:' in routes
    assert 'Product draft not found' in routes
    assert 'except ValueError as e:' in routes
    assert 'status=400' in routes


def test_knead_one_frontend_flow_is_wired_end_to_end():
    index = INDEX.read_text(encoding="utf-8")
    shell = PRODUCT_SHELL.read_text(encoding="utf-8")
    messages = MESSAGES.read_text(encoding="utf-8")
    ui = UI.read_text(encoding="utf-8")

    assert 'data-ai-object="create"' in index
    assert "onclick=\"openAssistantHome('create')\"" in index
    assert "title: 'Knead one'" in shell
    assert "_assistantKey() === 'create'" in messages
    assert "const createProduct = typeof createProductFromPrompt === 'function'" in messages
    assert "const created = await createProduct(text, {deferInitialSend: true});" in messages
    assert "continueCreatorDraftTurn(created)" in messages

    assert "await newSession(false, {" in shell
    assert "workspace: creatorDraft.workspace_path" in shell
    assert "creatorDraft: {" in shell
    assert "enabledToolsets: ['skills', 'file', 'terminal', 'code_execution']" in shell
    assert "agentInstruction: _creatorDraftInstruction" in shell

    assert "appendCreatorDraftReadyCard(data)" in shell
    assert "actions: [{id:'creator-publish-draft', label:'Add to shelf'}]" in messages
    assert "action==='creator-publish-draft'" in ui
    assert "publishCreatorDraft({silent:false})" in ui
    assert "openAssistantHome(saved.kind)" in shell
