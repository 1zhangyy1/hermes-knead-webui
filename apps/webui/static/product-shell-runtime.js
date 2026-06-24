let _activeProductPreview = null;
let _lastTaskAssistantKind = 'ppt';
window._currentAiAssistantTitle = window._currentAiAssistantTitle || 'PPT Designer';
const NEXT_AI_TASK_ASSIGNMENTS_KEY = 'next-ai-session-assistant-assignments';
const NEXT_AI_TASK_TITLES_KEY = 'next-ai-session-task-titles';
let _backendProductAssistants = [];

const AI_OBJECTS = {
  general: {
    title: 'General AI',
    avatar: 'G',
    iconName: 'message-square',
    desc: 'Open-ended chat for quick questions, writing, analysis, and files.',
    homeDesc: 'Start with anything. Repeated work can be kneaded into its own AI.',
    placeholder: 'Say what you want to do...',
    productType: 'general',
    uiMode: 'chat_only',
    productLayout: 'chat_only',
    canvasLabel: '',
    suggestions: [
      ['Help me organize today’s work into clear next steps.', 'Plan my day'],
      ['Rewrite this copy so it is clearer and more professional.', 'Polish copy'],
      ['Analyze this problem and give me a few possible paths.', 'Analyze a problem']
    ]
  },
  ppt: {
    title: 'PPT Designer',
    avatar: 'P',
    iconName: 'presentation',
    desc: 'Make decks through chat, with outline, slides, and speaker notes when structure helps.',
    homeDesc: 'Tell me the topic, audience, and goal. I will shape the outline, slides, and speaker notes.',
    placeholder: 'Describe this deck, or upload materials...',
    productType: 'ppt',
    uiMode: 'workspace',
    productLayout: 'chat_left_canvas_right',
    canvasLabel: 'PPT workspace',
    suggestions: [
      ['Help me make a product intro deck. First confirm topic, audience, and outline.', 'Start from topic'],
      ['I have a document. Turn it into a presentation structure.', 'Use materials'],
      ['Help me improve an existing deck structure. Tell me what to change first.', 'Improve structure']
    ]
  },
  create: {
    title: 'Knead one',
    iconName: 'plus',
    desc: 'Describe a recurring job. It becomes an AI you can keep using and shaping.',
    placeholder: 'Describe the work you want this AI to handle...',
    suggestions: [
      ['I want an AI that keeps helping me make fundraising decks.', 'Fundraising decks'],
      ['I want an AI that keeps helping me write industry research reports.', 'Industry research'],
      ['I want an AI that keeps helping me analyze operations data.', 'Ops data']
    ]
  }
};

function _syncProductPreviewMode(activeProductPreview) {
  const title = $('productModeTitle');
  if (title && !syncAssistantTaskUi()) title.textContent = activeProductPreview ? (activeProductPreview.name || 'Workspace') : (window._currentAiAssistantTitle || window._currentAiProductTitle || 'PPT Designer');
}

function _setActiveProductPreviewMenuOpen(open) {
  const menu = $('activeProductMoreMenu');
  const btn = $('activeProductMoreBtn');
  if (!menu) return;
  menu.hidden = !open;
  if (btn) btn.setAttribute('aria-expanded', open ? 'true' : 'false');
}

function toggleActiveProductPreviewMenu(event) {
  if (event && typeof event.stopPropagation === 'function') event.stopPropagation();
  const menu = $('activeProductMoreMenu');
  _setActiveProductPreviewMenuOpen(!!menu && menu.hidden);
}

window.toggleActiveProductPreviewMenu = toggleActiveProductPreviewMenu;

document.addEventListener('click', (event) => {
  const menu = $('activeProductMoreMenu');
  const menuButton = event.target && event.target.closest ? event.target.closest('.active-product-menu button') : null;
  if (menu && !menu.hidden && menuButton) {
    setTimeout(() => _setActiveProductPreviewMenuOpen(false), 0);
    return;
  }
  const more = event.target && event.target.closest ? event.target.closest('.active-product-more') : null;
  if (menu && !menu.hidden && !more) _setActiveProductPreviewMenuOpen(false);
});

document.addEventListener('keydown', (event) => {
  if (event && event.key === 'Escape') _setActiveProductPreviewMenuOpen(false);
  if (event && event.key === 'Escape') closeCurrentProductCapabilities();
});

function _assistantAssignmentsRead() {
  try {
    const raw = localStorage.getItem(NEXT_AI_TASK_ASSIGNMENTS_KEY);
    const data = raw ? JSON.parse(raw) : {};
    return data && typeof data === 'object' ? data : {};
  } catch (_err) {
    return {};
  }
}

function _assistantAssignmentsWrite(data) {
  try {
    localStorage.setItem(NEXT_AI_TASK_ASSIGNMENTS_KEY, JSON.stringify(data || {}));
  } catch (_err) {}
}

function _assistantTaskTitlesRead() {
  try {
    const raw = localStorage.getItem(NEXT_AI_TASK_TITLES_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch (_err) {
    return {};
  }
}

function _assistantTaskTitlesWrite(data) {
  try {
    localStorage.setItem(NEXT_AI_TASK_TITLES_KEY, JSON.stringify(data || {}));
  } catch (_err) {}
}

function _customAssistantsRead() {
  return _backendProductAssistants.filter(item => item && item.kind && item.title && _customAssistantIsProductBacked(item));
}

function _customAssistantsWrite(items) {
  _backendProductAssistants = Array.isArray(items)
    ? items.filter(item => item && item.kind && item.title && _customAssistantIsProductBacked(item))
    : [];
}

function _customAssistantIsProductBacked(item) {
  return !!(item && (item.backendProduct || item.productId || item.product_id));
}

function _assistantTitleKey(value) {
  return String(value || '').replace(/\s+/g, '').toLowerCase();
}

function _registerCustomAssistant(assistant) {
  if (!assistant || !assistant.kind) return;
  if (_isBuiltinAssistantKind(assistant.kind)) return;
  if (!_customAssistantIsProductBacked(assistant)) return;
  const title = assistant.title || 'Custom AI';
  const starterKit = _assistantStarterKit(title, assistant.sourcePrompt || assistant.desc || '');
  const productType = assistant.productType || assistant.product_type || '';
  const tools = typeof _assistantNormalizeToolsets === 'function'
    ? _assistantNormalizeToolsets(assistant.tools)
    : (Array.isArray(assistant.tools) ? assistant.tools : []);
  AI_OBJECTS[assistant.kind] = {
    title,
    avatar: assistant.avatar || '',
    desc: assistant.desc || 'Owns the kind of work you describe. A workspace appears when structure helps.',
    placeholder: assistant.placeholder || starterKit.placeholder,
    suggestions: Array.isArray(assistant.suggestions) && assistant.suggestions.length
      ? assistant.suggestions
      : starterKit.suggestions,
    custom: true,
    sourcePrompt: assistant.sourcePrompt || '',
    createdAt: assistant.createdAt || 0,
    titleSource: assistant.titleSource || '',
    productId: assistant.productId || assistant.product_id || '',
    workspacePath: assistant.workspacePath || assistant.workspace_path || '',
    previewUrl: assistant.previewUrl || assistant.preview_url || '',
    uiStatus: assistant.uiStatus || assistant.ui_status || 'empty',
    skills: Array.isArray(assistant.skills) ? assistant.skills : [],
    tools,
    backendProduct: !!assistant.backendProduct,
    productType,
    uiMode: assistant.uiMode || assistant.ui_mode || 'workspace',
    productLayout: assistant.productLayout || assistant.product_layout || assistant.layout || '',
    canvasLabel: assistant.canvasLabel || assistant.canvas_label || '',
    toolHints: Array.isArray(assistant.toolHints) && assistant.toolHints.length
      ? assistant.toolHints
      : tools.length
        ? tools
      : []
  };
}

function _customAssistantByKind(kind) {
  return _customAssistantsRead().find(item => item && item.kind === kind && _customAssistantIsProductBacked(item)) || null;
}

function _customAssistantTitleExists(title, exceptKind = '') {
  const key = _assistantTitleKey(title);
  if (!key) return false;
  if (_customAssistantsRead().some(item => item && _customAssistantIsProductBacked(item) && item.kind !== exceptKind && _assistantTitleKey(item.title) === key)) return true;
  return Object.entries(AI_OBJECTS).some(([kind, object]) => kind !== exceptKind && object && !object.custom && _assistantTitleKey(object.title) === key);
}

function _customAssistantByTitle(title) {
  const key = _assistantTitleKey(title);
  if (!key) return null;
  return _customAssistantsRead().find(item => item && _customAssistantIsProductBacked(item) && _assistantTitleKey(item.title) === key) || null;
}

function _assistantNeedsInitialProductUi(assistant) {
  if (!assistant || !assistant.productId) return false;
  if (typeof _assistantUsesProductCanvas === 'function' && !_assistantUsesProductCanvas(assistant)) return false;
  const status = String(assistant.uiStatus || assistant.ui_status || '').toLowerCase();
  return !status || status === 'empty' || status === 'failed';
}

function _maybeStartInitialProductUiForExistingAssistant(assistant, sourcePrompt = '') {
  if (!assistant || !_assistantNeedsInitialProductUi(assistant)) return false;
  const object = assistant.kind && AI_OBJECTS[assistant.kind] ? AI_OBJECTS[assistant.kind] : assistant;
  if (!object || !object.productId || !object.workspacePath) return false;
  const prompt = String(sourcePrompt || object.sourcePrompt || object.desc || object.title || '').trim();
  setTimeout(() => {
    if (typeof _startProductInitializationTask === 'function') {
      _startProductInitializationTask(object, prompt);
    }
  }, 80);
  return true;
}

function _deleteCustomAssistantKind(kind) {
  if (!kind) return false;
  const before = _customAssistantsRead();
  const next = before.filter(item => item && item.kind !== kind);
  if (next.length === before.length) return false;
  _customAssistantsWrite(next);
  if (AI_OBJECTS[kind] && AI_OBJECTS[kind].custom) delete AI_OBJECTS[kind];

  const assignments = _assistantAssignmentsRead();
  let changed = false;
  Object.keys(assignments).forEach(sessionId => {
    if (assignments[sessionId] === kind) {
      delete assignments[sessionId];
      changed = true;
    }
  });
  if (changed) _assistantAssignmentsWrite(assignments);

  if (typeof S !== 'undefined' && S.session && S.session.next_ai_assistant_kind === kind) {
    delete S.session.next_ai_assistant_kind;
  }
  return true;
}

function _assistantShortMeta(object) {
  const type = String(object && (object.productType || object.product_type) || '').trim();
  const label = String(object && (object.canvasLabel || object.canvas_label) || '').trim();
  if (type === 'general') return 'Chat';
  if (type === 'ppt') return 'Slides';
  if (type === 'image') return 'Images';
  if (type === 'research') return 'Research';
  if (type === 'data') return 'Data';
  if (type === 'interactive') return 'Interactive';
  if (label) return label;
  return 'Custom';
}

function _assistantBaseMeta(kind, object) {
  if (kind === 'general') return 'Chat';
  if (object && object.custom) return _assistantShortMeta(object);
  if (kind === 'ppt') return 'Slides';
  return _assistantShortMeta(object);
}

function _assistantIsChatOnlyProduct(object) {
  if (!object) return false;
  if (typeof _assistantProductLayout === 'function') return _assistantProductLayout(object) === 'chat_only';
  return String(object.uiMode || object.ui_mode || '') === 'chat_only';
}

function _assistantListMeta(kind, object) {
  if (!kind || kind === 'create') return '';
  if (object && (object.productId || object.backendProduct)) {
    const usesProductCanvas = typeof _assistantCanShowProductCanvas === 'function'
      ? _assistantCanShowProductCanvas(object)
      : typeof _assistantUsesProductCanvas === 'function'
      ? _assistantUsesProductCanvas(object)
      : !_assistantIsChatOnlyProduct(object);
    if (!usesProductCanvas) return _assistantBaseMeta(kind, object);
    const status = String(object.uiStatus || object.ui_status || '').toLowerCase();
    if (status === 'generating') return 'Creating';
    if (status === 'failed') return 'Retry';
    if (status === 'ready') return usesProductCanvas ? 'Workspace' : 'Chat';
    return 'Draft';
  }
  return _assistantBaseMeta(kind, object);
}

function syncAssistantListMeta() {
  document.querySelectorAll('.ai-object-item[data-ai-object]').forEach(btn => {
    const kind = btn.dataset.aiObject;
    if (!kind) return;
    const object = AI_OBJECTS[kind] || null;
    const avatar = btn.querySelector('.ai-object-avatar');
    _renderAssistantAvatar(avatar, kind, object, 16);
    if (kind === 'create') return;
    const small = btn.querySelector('small');
    const meta = _assistantListMeta(kind, object);
    if (small && meta) {
      small.textContent = meta;
      small.title = meta;
    }
  });
}

function renderAssistantList() {
  const list = document.querySelector('.ai-object-list');
  if (!list) return;
  const createItem = list.querySelector('[data-ai-object="create"]');
  list.querySelectorAll('.ai-object-item.custom-assistant').forEach(item => item.remove());
  const customAssistants = _customAssistantsRead().filter(_customAssistantIsProductBacked);
  for (const assistant of customAssistants) {
    if (!AI_OBJECTS[assistant.kind]) AI_OBJECTS[assistant.kind] = assistant;
    const object = AI_OBJECTS[assistant.kind];
    const btn = document.createElement('button');
    btn.className = 'ai-object-item custom-assistant';
    btn.dataset.aiObject = assistant.kind;
    btn.type = 'button';
    btn.onclick = () => openAssistantHome(assistant.kind);
    const avatar = document.createElement('span');
    avatar.className = 'ai-object-avatar';
    _renderAssistantAvatar(avatar, assistant.kind, object, 16);
    const copy = document.createElement('span');
    const strong = document.createElement('strong');
    strong.textContent = object.title;
    const small = document.createElement('small');
    small.textContent = _assistantListMeta(assistant.kind, object);
    small.title = small.textContent;
    copy.appendChild(strong);
    copy.appendChild(small);
    btn.appendChild(avatar);
    btn.appendChild(copy);
    if (createItem) list.insertBefore(btn, createItem);
    else list.appendChild(btn);
  }
  syncAssistantListMeta();
}

function _assistantStarterKit(title, text = '') {
  return {
    placeholder: title ? `Tell "${title}" what you want to finish...` : 'Describe what you want to finish...',
    suggestions: [
      ['Break this task into executable steps.', 'Break down task'],
      ['Ask me a few key questions first.', 'Clarify requirements'],
      ['Draft the first version.', 'Draft first version']
    ]
  };
}

function _assistantProductPayloadFromDraft(draft) {
  const tools = typeof _assistantNormalizeToolsets === 'function'
    ? _assistantNormalizeToolsets(draft && draft.tools)
    : (Array.isArray(draft && draft.tools) ? draft.tools : []);
  return {
    kind: draft && draft.kind,
    title: draft && draft.title,
    avatar: draft && draft.avatar || '',
    desc: draft && draft.desc || '',
    placeholder: draft && draft.placeholder || '',
    suggestions: Array.isArray(draft && draft.suggestions) ? draft.suggestions : [],
    source_prompt: draft && (draft.sourcePrompt || draft.source_prompt) || '',
    product_type: draft && (draft.productType || draft.product_type) || 'custom',
    ui_mode: draft && (draft.uiMode || draft.ui_mode) || 'workspace',
    product_layout: draft && (draft.productLayout || draft.product_layout || draft.layout) || '',
    canvas_label: draft && (draft.canvasLabel || draft.canvas_label) || '',
    skills: Array.isArray(draft && draft.skills) ? draft.skills : [],
    tools
  };
}

async function _saveProductBackedAssistant(nextAssistant) {
  const productId = String(nextAssistant && (nextAssistant.productId || nextAssistant.product_id) || '').trim();
  if (!productId) throw new Error('这个产品缺少 productId');
  const data = await api('/api/products/update', {
    method: 'POST',
    body: JSON.stringify({
      product_id: productId,
      ..._assistantProductPayloadFromDraft(nextAssistant)
    })
  });
  const persisted = data && data.product && typeof _productToCustomAssistant === 'function'
    ? _productToCustomAssistant(data.product)
    : null;
  const saved = {
    ...(persisted || nextAssistant),
    titleSource: nextAssistant.titleSource || (persisted && persisted.titleSource) || ''
  };
  _customAssistantsWrite(_mergeCustomAssistants(_customAssistantsRead(), [saved]));
  _registerCustomAssistant(saved);
  return saved;
}

function _scheduleInitialProductShape(assistant, sourcePrompt = '') {
  if (!assistant || !assistant.productId || !assistant.workspacePath) return false;
  const object = assistant.kind && AI_OBJECTS[assistant.kind] ? AI_OBJECTS[assistant.kind] : assistant;
  const prompt = String(sourcePrompt || object.sourcePrompt || object.desc || object.title || '').trim();
  setTimeout(() => {
    const startShape = typeof startProductShapeTask === 'function'
      ? startProductShapeTask
      : (typeof _startProductInitializationTask === 'function'
        ? (nextObject, nextPrompt) => _startProductInitializationTask(nextObject, nextPrompt, {allowWithoutCanvas: true})
        : null);
    if (startShape) startShape(object, prompt);
  }, 80);
  return true;
}

function _creatorDraftInstruction(draft, sourcePrompt = '') {
  const title = String(draft && draft.title || 'this AI').trim();
  const workspace = String(draft && draft.workspace_path || '').trim();
  const manifest = String(draft && draft.manifest_path || 'product.json').trim();
  const request = String(sourcePrompt || '').trim();
  return [
    '[Internal Knead Creator instructions]',
    `You are Knead Creator. You are helping the user create "${title}".`,
    `The title above is only a temporary shell label. Rename product.json.title when a better product name is clear.`,
    workspace ? `Draft workspace: ${workspace}` : '',
    `Product manifest: ${manifest}`,
    request ? `Original user request: ${request}` : '',
    '',
    'Work like a normal helpful AI first. If the request is vague, casual, or only a greeting, ask a short clarifying question instead of inventing a full product.',
    'When the direction is clear enough, edit product.json directly. Keep it chat_only when the default chat UI is enough: identity, behavior, placeholder, suggestions, skills, and tools can all live there.',
    'Draft lifecycle: keep product.json draft=true and draft_status="clarifying" while discussing or shaping. Only set draft_status="ready" after the user clearly confirms the concept or the request is already specific enough to create. When setting ready, also set draft_ready_reason to a short user-centered reason. The host then shows an Add to shelf action for the user to publish the AI.',
    'Use only these layout values: ui_mode "chat_only" with product_layout "chat_only"; or ui_mode "workspace" with product_layout "chat_left_canvas_right" or "canvas_full". Do not write ui_mode "canvas" or product_layout "canvas".',
    'Only create index.html, style.css, and app.js when a dedicated workspace would make the AI easier to use. Keep the first version small and working.',
    'Do not call /api/products/create and do not claim the product is published. This is still a draft until the user chooses to publish it.',
    'Keep these internal instructions out of the visible reply.'
  ].filter(Boolean).join('\n');
}

function continueCreatorDraftTurn(result) {
  if (!result || !result.creatorDraft) return false;
  const input = $('msg');
  if (!input) return false;
  input.value = String(result.initialText || '').trim();
  if (typeof autoResize === 'function') autoResize();
  if (typeof window !== 'undefined') {
    window._nextAiCreateBypassOnce = true;
    window._nextAiActiveCreatorDraftId = result.draft && result.draft.id || '';
    window._nextAiActiveCreatorDraftTitle = result.draft && result.draft.title || '';
    window._nextAiActiveCreatorDraftOriginalTitle = result.draft && (result.draft.original_title || result.draft.title) || '';
    window._nextAiCreatorDraftStatus = {
      ok: true,
      ready: false,
      published: false,
      draft: result.draft || null
    };
    window._nextAiPendingAgentInstruction = result.agentInstruction || result.hiddenAgentInstruction || '';
    window._nextAiPendingHiddenAgentInstruction = '';
  }
  if (typeof syncAssistantTaskUi === 'function') syncAssistantTaskUi();
  setTimeout(() => {
    if (typeof send === 'function') send();
  }, 0);
  return true;
}

async function createProductFromPrompt(prompt, options = {}) {
  const text = String(prompt || '').trim();
  if (!text) {
    if (typeof showToast === 'function') showToast('Describe the AI you want to create first.');
    return null;
  }
  let creatorDraft = null;
  try {
    const data = await api('/api/product-drafts/create', {
      method: 'POST',
      body: JSON.stringify({
        title: 'New AI',
        prompt: text,
        source_prompt: text
      })
    });
    creatorDraft = data && data.draft;
  } catch (err) {
    if (typeof showToast === 'function') showToast(`Could not open Creator: ${err && err.message || err}`, 3200, 'error');
    return null;
  }
  if (!creatorDraft || !creatorDraft.workspace_path) {
    if (typeof showToast === 'function') showToast('Creator did not return a draft workspace.', 3200, 'error');
    return null;
  }
  if (typeof newSession !== 'function') {
    if (typeof showToast === 'function') showToast('Creator cannot start because sessions are unavailable.', 3200, 'error');
    return null;
  }
  await newSession(false, {
    workspace: creatorDraft.workspace_path,
    enabledToolsets: ['skills', 'file', 'terminal', 'code_execution'],
    creatorDraft: {
      id: creatorDraft.id || '',
      title: creatorDraft.title || '',
      original_title: creatorDraft.original_title || creatorDraft.title || '',
      workspace_path: creatorDraft.workspace_path || ''
    }
  });
  if (typeof renderSessionList === 'function') await renderSessionList();
  if (typeof showToast === 'function') showToast(`Creator opened: ${creatorDraft.title}`);
  const result = {
    creatorDraft: true,
    draft: creatorDraft,
    initialText: text,
    agentInstruction: _creatorDraftInstruction(creatorDraft, text)
  };
  if (!options || !options.deferInitialSend) continueCreatorDraftTurn(result);
  return result;
}

function _isCreatorDraftWorkspace(workspace) {
  return /(^|[\\/])product_drafts[\\/]/.test(String(workspace || '').trim());
}

function _isCreatorDraftSession(session = (typeof S !== 'undefined' ? S.session : null)) {
  if (session && session.creator_draft) return true;
  return _isCreatorDraftWorkspace(session && session.workspace);
}

function _isCreatorMode() {
  return _assistantKey() === 'create' || _isCreatorDraftSession();
}

function _currentCreatorDraftPayload(extra = {}) {
  const sessionDraft = (typeof S !== 'undefined' && S.session && S.session.creator_draft)
    ? S.session.creator_draft
    : {};
  const workspace = String(
    (sessionDraft && sessionDraft.workspace_path) ||
    (typeof S !== 'undefined' && S.session && S.session.workspace) ||
    ''
  ).trim();
  if (!_isCreatorDraftWorkspace(workspace)) return null;
  return {
    workspace_path: workspace,
    draft_id: String(
      (sessionDraft && sessionDraft.id) ||
      (typeof window !== 'undefined' ? window._nextAiActiveCreatorDraftId : '') ||
      ''
    ),
    original_title: String(
      (sessionDraft && (sessionDraft.original_title || sessionDraft.originalTitle)) ||
      (typeof window !== 'undefined' ? window._nextAiActiveCreatorDraftOriginalTitle : '') ||
      (sessionDraft && sessionDraft.title) ||
      (typeof window !== 'undefined' ? window._nextAiActiveCreatorDraftTitle : '') ||
      ''
    ),
    ...extra
  };
}

function _syncCurrentCreatorDraftFromStatus(status) {
  const draft = status && status.draft && typeof status.draft === 'object' ? status.draft : null;
  if (!draft) return false;
  const previousDraft = (typeof S !== 'undefined' && S.session && S.session.creator_draft)
    ? S.session.creator_draft
    : {};
  const previousOriginalTitle = String(
    (previousDraft && (previousDraft.original_title || previousDraft.originalTitle || previousDraft.title)) ||
    (typeof window !== 'undefined' ? window._nextAiActiveCreatorDraftOriginalTitle : '') ||
    ''
  ).trim();
  const next = {
    id: String(draft.id || '').trim(),
    title: String(draft.title || '').trim(),
    original_title: previousOriginalTitle,
    workspace_path: String(draft.workspace_path || '').trim()
  };
  if (!next.workspace_path) return false;
  if (typeof window !== 'undefined') {
    if (next.id) window._nextAiActiveCreatorDraftId = next.id;
    if (next.title) window._nextAiActiveCreatorDraftTitle = next.title;
    if (next.original_title) window._nextAiActiveCreatorDraftOriginalTitle = next.original_title;
  }
  if (typeof S !== 'undefined' && S.session && _isCreatorDraftSession(S.session)) {
    S.session.creator_draft = {
      ...(S.session.creator_draft || {}),
      ...Object.fromEntries(Object.entries(next).filter(([, value]) => value))
    };
  }
  return true;
}

function _currentCreatorDraftStatus() {
  if (typeof window === 'undefined') return null;
  const status = window._nextAiCreatorDraftStatus || null;
  const payload = _currentCreatorDraftPayload();
  const statusWorkspace = String(status && status.draft && status.draft.workspace_path || '').trim();
  if (payload && statusWorkspace && statusWorkspace !== payload.workspace_path) return null;
  return status;
}

function _creatorDraftPhase(status = _currentCreatorDraftStatus()) {
  const draft = status && status.draft && typeof status.draft === 'object' ? status.draft : {};
  const title = String(draft.title || window._nextAiActiveCreatorDraftTitle || 'this AI').trim() || 'this AI';
  if (status && status.published) {
    return {
      title,
      state: 'published',
      chatLabel: 'Created',
      shelfLabel: 'Added',
      composer: `"${title}" is on the shelf. Open it there to start using it.`
    };
  }
  if (status && status.ready) {
    return {
      title,
      state: 'ready',
      chatLabel: 'Ready',
      shelfLabel: 'Add to shelf',
      composer: `Add "${title}" to the shelf, or keep shaping it...`
    };
  }
  return {
    title,
    state: 'drafting',
    chatLabel: 'Creating',
    shelfLabel: 'Draft in progress',
    composer: `Tell Creator what "${title}" should become...`
  };
}

const _creatorDraftStatusRefreshInFlight = new Set();

function _maybeRefreshCreatorDraftStatus(options = {}) {
  const payload = _currentCreatorDraftPayload();
  const workspace = payload && payload.workspace_path;
  if (!workspace || typeof refreshCreatorDraftStatus !== 'function') return;
  const status = _currentCreatorDraftStatus();
  const statusWorkspace = String(status && status.draft && status.draft.workspace_path || '').trim();
  if (status && (!statusWorkspace || statusWorkspace === workspace)) return;
  if (_creatorDraftStatusRefreshInFlight.has(workspace)) return;
  _creatorDraftStatusRefreshInFlight.add(workspace);
  refreshCreatorDraftStatus({silent:true, skipReadyToast:true, ...options})
    .catch(() => {})
    .finally(() => _creatorDraftStatusRefreshInFlight.delete(workspace));
}

async function refreshCreatorDraftStatus(options = {}) {
  const payload = _currentCreatorDraftPayload();
  if (!payload) {
    if (typeof window !== 'undefined') window._nextAiCreatorDraftStatus = null;
    if (typeof syncAssistantTaskUi === 'function') syncAssistantTaskUi();
    return null;
  }
  let data = null;
  try {
    data = await api('/api/product-drafts/status', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  } catch (err) {
    if (!options.silent && typeof showToast === 'function') {
      showToast(`Could not read draft: ${err && err.message || err}`, 3200, 'error');
    }
    return null;
  }
  if (typeof window !== 'undefined') window._nextAiCreatorDraftStatus = data;
  _syncCurrentCreatorDraftFromStatus(data);
  if (data && data.ready && !data.published && !options.silent && !options.skipReadyToast && typeof showToast === 'function') {
    showToast('Draft is ready. Add it to the shelf when you are happy with it.');
  }
  if (data && data.ready && !data.published && !options.silent && typeof appendCreatorDraftReadyCard === 'function') {
    appendCreatorDraftReadyCard(data);
  }
  if (data && data.published && typeof removeCreatorDraftStatusCards === 'function') {
    const draftId = String(data && data.draft && data.draft.id || '').trim();
    removeCreatorDraftStatusCards(draftId);
  }
  if (typeof syncAssistantTaskUi === 'function') syncAssistantTaskUi();
  return data;
}

async function publishCreatorDraft(options = {}) {
  const payload = _currentCreatorDraftPayload({
    if_ready: options.force !== true,
    force: !!options.force
  });
  if (!payload) return null;
  let data = null;
  try {
    data = await api('/api/product-drafts/publish', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  } catch (err) {
    if (options.force && typeof showToast === 'function') {
      showToast(`Could not publish draft: ${err && err.message || err}`, 3600, 'error');
    }
    return null;
  }
  if (!data || !data.published || !data.product) {
    if (data && data.not_ready && typeof showToast === 'function' && !options.silent) {
      showToast(data.not_ready_reason || 'The draft is not ready yet. Keep chatting with Creator first.');
    }
    if (typeof refreshCreatorDraftStatus === 'function') refreshCreatorDraftStatus({silent:true});
    return data || null;
  }
  const saved = typeof _productToCustomAssistant === 'function' ? _productToCustomAssistant(data.product) : null;
  if (!saved || !saved.productId) return data;
  if (typeof window !== 'undefined') {
    window._nextAiCreatorDraftStatus = {
      ok: true,
      ready: true,
      published: true,
      draft: data.draft || null,
      product: data.product
    };
  }
  _syncCurrentCreatorDraftFromStatus({draft: data.draft || null});
  if (typeof removeCreatorDraftStatusCards === 'function') {
    const draftId = String(data && data.draft && data.draft.id || '').trim();
    removeCreatorDraftStatusCards(draftId);
  }
  _customAssistantsWrite(_mergeCustomAssistants(_customAssistantsRead(), [saved]));
  _registerCustomAssistant(saved);
  if (typeof hydrateProductsFromBackend === 'function') await hydrateProductsFromBackend();
  if (typeof renderAssistantList === 'function') renderAssistantList();
  if (typeof showToast === 'function' && !options.silent) {
    showToast(data.already_published ? `Opened AI: ${saved.title}` : `Created AI: ${saved.title}`);
  }
  if (options.open !== false && typeof openAssistantHome === 'function') {
    setTimeout(() => openAssistantHome(saved.kind), 80);
  }
  return data;
}

async function createAssistantFromPrompt(prompt) {
  return createProductFromPrompt(prompt);
}

async function renameCurrentCustomAssistant() {
  const kind = _assistantKey();
  const assistant = _customAssistantByKind(kind);
  if (!assistant) {
    if (typeof showToast === 'function') showToast('Only AIs you created can be renamed.');
    return null;
  }
  const nextTitleRaw = typeof showPromptDialog === 'function'
    ? await showPromptDialog({
      title: '重命名产品',
      message: '这个名称会显示在左侧产品列表和产品主页。',
        value: assistant.title,
        confirmLabel: 'Save'
      })
    : window.prompt('重命名产品', assistant.title);
  const nextTitle = String(nextTitleRaw || '').replace(/\s+/g, ' ').trim();
  if (!nextTitle || nextTitle === assistant.title) return assistant;
  if (_customAssistantTitleExists(nextTitle, kind)) {
    if (typeof showToast === 'function') showToast('已经有同名产品');
    return assistant;
  }
  let updated = null;
  try {
    updated = await _saveProductBackedAssistant({ ...assistant, title: nextTitle, titleSource: 'manual' });
  } catch (err) {
    if (typeof showToast === 'function') showToast(`重命名失败：${err && err.message || err}`, 3200, 'error');
    return assistant;
  }
  renderAssistantList();
  openAssistantHome(updated.kind || kind);
  if (typeof showToast === 'function') showToast(`已重命名为：${nextTitle}`);
  return updated;
}

async function deleteCurrentCustomAssistant() {
  const kind = _assistantKey();
  const assistant = _customAssistantByKind(kind);
  if (!assistant) {
    if (typeof showToast === 'function') showToast('Built-in AIs cannot be deleted.');
    return false;
  }
  const ok = typeof showConfirmDialog === 'function'
    ? await showConfirmDialog({
        title: `Delete "${assistant.title}"?`,
        message: 'This only deletes the AI object. Past tasks stay in history and move back to the closest built-in AI.',
        confirmLabel: 'Delete',
        danger: true,
        focusCancel: true
      })
    : window.confirm(`Delete "${assistant.title}"?`);
  if (!ok) return false;
  if ((assistant.backendProduct || assistant.productId) && assistant.productId) {
    try {
      await api('/api/products/delete', {
        method: 'POST',
        body: JSON.stringify({ product_id: assistant.productId })
      });
    } catch (err) {
      if (typeof showToast === 'function') showToast(`Delete failed: ${err && err.message || err}`, 3200, 'error');
      return false;
    }
  }
  const deleted = _deleteCustomAssistantKind(kind);
  if (!deleted) return false;
  renderAssistantList();
  openAssistantHome('general');
  if (typeof renderSessionListFromCache === 'function') renderSessionListFromCache();
  if (typeof showToast === 'function') showToast(`Deleted AI: ${assistant.title}`);
  return true;
}

function _assistantKey() {
  return window._currentAiAssistantKind || 'ppt';
}

function _assistantObject(kind = _assistantKey()) {
  const sessionObject = kind === _assistantKey()
    ? _assistantObjectForCurrentSessionProduct()
    : null;
  return sessionObject || AI_OBJECTS[kind] || AI_OBJECTS.ppt;
}

function _currentSessionProductId() {
  if (typeof S === 'undefined' || !S.session) return '';
  return String(S.session.product_id || S.session.productId || '').trim();
}

function _assistantKindForCurrentSessionProduct() {
  const productId = _currentSessionProductId();
  if (!productId || typeof _assistantKindForProductId !== 'function') return '';
  const kind = _assistantKindForProductId(productId);
  return kind && AI_OBJECTS[kind] ? kind : '';
}

function _assistantObjectForCurrentSessionProduct() {
  const kind = _assistantKindForCurrentSessionProduct();
  return kind ? AI_OBJECTS[kind] || null : null;
}

function syncAssistantSelectionToSessionProduct() {
  const kind = _assistantKindForCurrentSessionProduct();
  if (!kind) return '';
  if (_assistantKey() !== kind && typeof selectAiObject === 'function') {
    selectAiObject(kind);
  }
  return kind;
}

function _assistantDirectoryMode(hasTask = _assistantTaskHasActiveTask()) {
  const raw = document.body && document.body.dataset ? document.body.dataset.nextAiDirectory : '';
  if (raw === 'library' || raw === 'product') return raw;
  if (window._nextAiDirectory === 'library' || window._nextAiDirectory === 'product') return window._nextAiDirectory;
  return hasTask ? 'product' : 'library';
}

function _setAssistantDirectoryMode(mode) {
  const next = mode === 'library' ? 'library' : 'product';
  window._nextAiDirectory = next;
  if (document.body && document.body.dataset) document.body.dataset.nextAiDirectory = next;
  return next;
}

function assistantKindForSession(sessionId) {
  if (!sessionId) return '';
  const assignments = _assistantAssignmentsRead();
  return assignments[sessionId] || '';
}

function _assistantKindFromLegacySession(session) {
  if (!session) return '';
  const messageSource = Array.isArray(session.messages) && session.messages.length
    ? session.messages
    : ((typeof S !== 'undefined' && Array.isArray(S.messages)) ? S.messages : []);
  const messageText = messageSource
    .filter(message => message && message.role !== 'tool')
    .slice(0, 8)
    .map(message => {
      if (typeof msgContent === 'function') return msgContent(message);
      const content = message.content || '';
      if (Array.isArray(content)) {
        return content
          .filter(part => part && part.type === 'text')
          .map(part => part.text || part.content || '')
          .join(' ');
      }
      return String(content || '');
    })
    .filter(Boolean)
    .join(' ');
  const text = [
    session.title,
    session.pending_user_message,
    session.last_message,
    session.preview,
    session.summary,
    messageText
  ].filter(Boolean).join(' ');
  if (!text) return '';
  if (/(PPT|ppt|PowerPoint|幻灯|演示|路演)/.test(text) || /\b(BP|deck|slide|slides)\b/i.test(text)) return 'ppt';
  if (/(数据|表格|指标|运营|Excel|excel|CSV|csv|图表|看板|分析报表)/.test(text)) return 'data';
  if (/(研究|调研|竞品|资料|文献|论文|引用|市场分析|行业分析)/.test(text)) return 'research';
  return '';
}

function _assistantKindExists(kind) {
  return !!(kind && AI_OBJECTS[kind]);
}

function _clearAssistantAssignment(sessionId) {
  if (!sessionId) return;
  const assignments = _assistantAssignmentsRead();
  if (!Object.prototype.hasOwnProperty.call(assignments, sessionId)) return;
  delete assignments[sessionId];
  _assistantAssignmentsWrite(assignments);
}

function assistantKindForLoadedSession(session) {
  if (!session || !session.session_id) return 'general';
  if (_isCreatorDraftSession(session)) return 'create';
  const productId = String(session.product_id || session.productId || '').trim();
  if (productId) {
    const productKind = _assistantKindForProductId(productId);
    if (productKind && _assistantKindExists(productKind)) return productKind;
    return 'general';
  }
  const assignedKind = session.next_ai_assistant_kind || assistantKindForSession(session.session_id);
  const inferredKind = _assistantKindFromLegacySession(session);
  const validInferredKind = _assistantKindExists(inferredKind) ? inferredKind : '';
  if (!assignedKind) return validInferredKind || 'general';
  if (_assistantKindExists(assignedKind)) {
    return assignedKind === 'general' && validInferredKind ? validInferredKind : assignedKind;
  }
  _clearAssistantAssignment(session.session_id);
  return validInferredKind || 'general';
}

function syncAssistantForLoadedSession(session) {
  const productId = String(session && (session.product_id || session.productId) || '').trim();
  const kind = assistantKindForLoadedSession(session);
  _setAssistantDirectoryMode('product');
  if (session && kind) session.next_ai_assistant_kind = kind;
  if (kind && kind !== _assistantKey() && AI_OBJECTS[kind]) {
    selectAiObject(kind);
  } else {
    syncAssistantTaskUi();
  }
  if (productId && !_assistantKindForProductId(productId) && typeof hydrateProductsFromBackend === 'function') {
    void hydrateProductsFromBackend().then(() => {
      const hydratedKind = _assistantKindForProductId(productId);
      if (!hydratedKind || !AI_OBJECTS[hydratedKind]) return;
      if (typeof S !== 'undefined' && S.session && String(S.session.product_id || S.session.productId || '') !== productId) return;
      selectAiObject(hydratedKind);
      if (typeof refreshCurrentProductPreview === 'function') refreshCurrentProductPreview({silent:true, reason:'session-product-hydrate'});
    }).catch(err => console.debug('Failed to hydrate product for loaded session', err));
  }
  return kind;
}

function rememberAssistantTaskTitle(sessionId, title) {
  const sid = sessionId || (typeof S !== 'undefined' && S.session && (S.session.session_id || S.session.id));
  const nextTitle = _assistantTaskCompactDisplayTitle(title);
  if (!sid || !nextTitle) return;
  if (_assistantTaskLooksGenericTitle(nextTitle)) return;
  const titles = _assistantTaskTitlesRead();
  if (_assistantTaskLooksProductUiCommand(nextTitle)) {
    const firstUserTitle = _assistantTaskCompactDisplayTitle(_assistantTaskFirstUserMessage());
    if (firstUserTitle && !_assistantTaskLooksGenericTitle(firstUserTitle) && !_assistantTaskLooksProductUiCommand(firstUserTitle)) {
      titles[sid] = firstUserTitle;
      _assistantTaskTitlesWrite(titles);
    }
    return;
  }
  const currentTitle = _assistantTaskNormalizeTitle(titles[sid]);
  if (currentTitle && !_assistantTaskLooksGenericTitle(currentTitle) && !_assistantTaskLooksProductUiCommand(currentTitle)) return;
  if (titles[sid] === nextTitle) return;
  titles[sid] = nextTitle;
  _assistantTaskTitlesWrite(titles);
}

function markSessionForCurrentAssistant(sessionId, taskTitle = '') {
  const sid = sessionId || (typeof S !== 'undefined' && S.session && (S.session.session_id || S.session.id));
  if (!sid) return;
  const kind = _assistantKey();
  const assignments = _assistantAssignmentsRead();
  assignments[sid] = kind;
  _assistantAssignmentsWrite(assignments);
  if (taskTitle) rememberAssistantTaskTitle(sid, taskTitle);
  if (typeof S !== 'undefined' && S.session && (S.session.session_id || S.session.id) === sid) {
    S.session.next_ai_assistant_kind = kind;
  }
}

function assistantTaskBelongsToCurrentAssistant(session) {
  if (!session || !session.session_id) return false;
  if (_isCreatorDraftSession(session)) return _assistantKey() === 'create';
  const productId = String(session.product_id || session.productId || '').trim();
  if (productId) {
    const productKind = _assistantKindForProductId(productId);
    if (productKind && _assistantKindExists(productKind)) return productKind === _assistantKey();
    return false;
  }
  const assignedKind = session.next_ai_assistant_kind || assistantKindForSession(session.session_id);
  if (!assignedKind) {
    const inferredKind = _assistantKindFromLegacySession(session);
    const validInferredKind = _assistantKindExists(inferredKind) ? inferredKind : '';
    return validInferredKind ? validInferredKind === _assistantKey() : _assistantKey() === 'general';
  }
  if (!_assistantKindExists(assignedKind)) {
    _clearAssistantAssignment(session.session_id);
    const inferredKind = _assistantKindFromLegacySession(session);
    const validInferredKind = _assistantKindExists(inferredKind) ? inferredKind : '';
    return validInferredKind ? validInferredKind === _assistantKey() : _assistantKey() === 'general';
  }
  return assignedKind === _assistantKey();
}

function filterSessionsForCurrentAssistant(sessions) {
  if (!Array.isArray(sessions)) return [];
  return sessions.filter(assistantTaskBelongsToCurrentAssistant);
}

function assistantProductLabelForSession(session) {
  const kind = assistantKindForLoadedSession(session);
  const object = AI_OBJECTS[kind] || AI_OBJECTS.general || AI_OBJECTS.ppt;
  return object && object.title ? object.title : 'General AI';
}

function _assistantAvatarLabel(kind = _assistantKey(), object) {
  if (kind === 'create') return '+';
  const title = object && object.title ? object.title : (window._currentAiAssistantTitle || 'AI product');
  const avatar = object && object.avatar ? String(object.avatar).trim() : '';
  if (avatar) return avatar.slice(0, 2).toUpperCase();
  if (/ppt/i.test(kind) || /PPT/.test(title)) return 'P';
  if (kind === 'research') return 'R';
  if (kind === 'data') return 'D';
  if (kind === 'general') return 'G';
  return String(title).trim().slice(0, 1).toUpperCase() || 'A';
}

function _assistantIconName(kind = _assistantKey(), object) {
  const title = String(object && object.title || '').toLowerCase();
  const type = String(object && (object.productType || object.product_type) || '').toLowerCase();
  const label = `${kind || ''} ${title} ${type}`;
  if (object && object.iconName) return object.iconName;
  if (kind === 'create') return 'plus';
  if (kind === 'general' || type === 'general') return 'message-square';
  if (/ppt|deck|slide|presentation|演示|幻灯|汇报/.test(label)) return 'presentation';
  if (/game|角色|character|role|c\\.ai|chatbot|interactive/.test(label)) return 'gamepad-2';
  if (/image|avatar|poster|illustration|海报|头像|图片|图像|生图|插画/.test(label)) return 'image';
  if (/research|report|search|研究|调研|报告|竞品/.test(label)) return 'search';
  if (/data|analytics|table|chart|运营|数据|指标|表格/.test(label)) return 'chart-column';
  if (/timer|time|pomodoro|番茄|计时/.test(label)) return 'clock';
  return '';
}

function _renderAssistantAvatar(el, kind = _assistantKey(), object, size = 16) {
  if (!el) return;
  const iconName = _assistantIconName(kind, object);
  el.classList.toggle('has-product-icon', !!iconName);
  el.classList.toggle('has-avatar-label', !iconName);
  if (iconName) el.dataset.productIcon = iconName;
  else delete el.dataset.productIcon;
  if (iconName && typeof li === 'function') {
    el.innerHTML = li(iconName, size);
    return;
  }
  el.textContent = _assistantAvatarLabel(kind, object);
}

function _renderAssistantHomeActionBar(el, text, actionLabel = '', actionHandler = null) {
  if (!el) return;
  el.hidden = false;
  el.innerHTML = '';
  const copy = document.createElement('span');
  copy.textContent = text;
  el.appendChild(copy);
  if (actionLabel && typeof actionHandler === 'function') {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'assistant-home-inline-action';
    btn.textContent = actionLabel;
    btn.title = actionLabel;
    btn.setAttribute('aria-label', actionLabel);
    btn.onclick = actionHandler;
    el.appendChild(btn);
  }
}

function focusAssistantComposerForFirstTask() {
  const input = $('msg');
  if (!input) return;
  try {
    input.scrollIntoView({ block: 'center', behavior: 'smooth' });
  } catch (_err) {}
  setTimeout(() => input.focus(), 80);
}

window.focusAssistantComposerForFirstTask = focusAssistantComposerForFirstTask;

function _syncAssistantHome(object = AI_OBJECTS[_assistantKey()] || AI_OBJECTS.ppt) {
  const kind = _assistantKey();
  const isCreate = kind === 'create' || object === AI_OBJECTS.create || _isCreatorDraftSession();
  const assistantTitle = object.title || 'AI product';
  const home = $('assistantHome');
  const title = $('assistantHomeTitle');
  const desc = $('assistantHomeDesc');
  const avatar = $('assistantHomeAvatar');
  const eyebrow = $('assistantHomeEyebrow');
  const guide = $('assistantHomeGuide');
  const origin = $('assistantHomeOrigin');
  const nextStep = $('assistantHomeNextStep');
  const manage = $('assistantHomeManage');
  const newTaskLabel = $('newTaskPrimaryLabel');
  const newTaskBtn = $('newTaskPrimaryBtn');
  const newTaskIcon = $('newTaskPrimaryIcon');
  const isChatOnlyProduct = _assistantIsChatOnlyProduct(object);
  const usesProductCanvas = typeof _assistantCanShowProductCanvas === 'function'
    ? _assistantCanShowProductCanvas(object)
    : typeof _assistantUsesProductCanvas === 'function'
    ? _assistantUsesProductCanvas(object)
    : !isChatOnlyProduct;
  if (home) home.classList.toggle('is-create', isCreate);
  if (title) title.textContent = assistantTitle;
  if (desc) {
    desc.textContent = isCreate
      ? (object.desc || 'Describe a repeatable job.')
      : (object.homeDesc || object.desc || 'Say what you want to finish. A workspace appears when the task needs structure.');
  }
  _renderAssistantAvatar(avatar, kind, object, 22);
  if (eyebrow) eyebrow.textContent = isCreate ? 'Knead one' : object.custom ? 'Your AI' : 'Selected';
  if (guide) {
    guide.textContent = isCreate
      ? 'Say what it should own over time.'
      : 'Start with one sentence.';
  }
  if (origin) {
    if (isCreate) {
      origin.hidden = false;
      origin.textContent = 'Creator drafts first. It appears in the AI shelf only after you choose Add to shelf.';
      origin.removeAttribute('title');
    } else {
      origin.hidden = true;
      origin.textContent = '';
      origin.removeAttribute('title');
    }
  }
  if (nextStep) {
    if (isCreate) {
      _renderAssistantHomeActionBar(nextStep, 'Describe the reusable AI you want. Creator will ask only what it needs, then prepare a draft.');
    } else if (!usesProductCanvas) {
      nextStep.hidden = true;
      nextStep.innerHTML = '';
    } else if (object.productId && String(object.uiStatus || 'empty') === 'failed') {
      const failureReason = String(object.uiErrorMessage || '').trim();
      _renderAssistantHomeActionBar(
        nextStep,
        failureReason
          ? `${failureReason} Keep chatting, or rebuild the workspace first.`
          : 'Workspace generation failed. Keep chatting, or rebuild it first.',
        'Rebuild workspace',
        () => requestCurrentProductUiGeneration()
      );
    } else if (object.productId && String(object.uiStatus || 'empty') === 'empty') {
      _renderAssistantHomeActionBar(
        nextStep,
        'This AI does not have a fixed workspace yet. Chat first, or create the first version.',
        'Create workspace',
        () => requestCurrentProductUiGeneration()
      );
    } else if (object.productId && String(object.uiStatus || 'empty') === 'generating') {
      _renderAssistantHomeActionBar(nextStep, 'Creating this AI workspace. It will refresh when ready.');
    } else {
      nextStep.hidden = true;
      nextStep.innerHTML = '';
    }
  }
  if (manage) manage.hidden = true;
  if (newTaskLabel) newTaskLabel.textContent = isCreate ? 'Back to current AI' : 'New task';
  if (newTaskBtn) {
    const lastObject = AI_OBJECTS[_lastTaskAssistantKind] || AI_OBJECTS.general || AI_OBJECTS.ppt;
    const lastTitle = lastObject && lastObject.title ? lastObject.title : 'Current AI';
    newTaskBtn.title = isCreate ? `Back to a new task with ${lastTitle}` : `Start a new task with ${assistantTitle}`;
    newTaskBtn.setAttribute('aria-label', newTaskBtn.title);
    newTaskBtn.classList.toggle('is-return', isCreate);
  }
  if (newTaskIcon) {
    newTaskIcon.innerHTML = isCreate
      ? '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M19 12H5"/><path d="m12 19-7-7 7-7"/></svg>'
      : '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14"/><path d="M5 12h14"/></svg>';
  }
}

function selectAiObject(kind = 'ppt') {
  const object = AI_OBJECTS[kind] || AI_OBJECTS.ppt;
  const previousKind = window._currentAiAssistantKind || '';
  window._currentAiAssistantKind = kind;
  window._currentAiAssistantTitle = object.title;
  window._currentAiProductTitle = object.title;
  if (previousKind && previousKind !== kind && document.body && document.body.dataset) {
    document.body.dataset.nextAiProductAdjust = 'closed';
    document.body.dataset.nextAiChatPanel = 'closed';
    delete document.body.dataset.nextAiChatPanelManual;
  }
  document.body.dataset.nextAiProductLayout = typeof _assistantProductLayout === 'function'
    ? _assistantProductLayout(object)
    : (_assistantIsChatOnlyProduct(object) ? 'chat_only' : 'chat_center');
  if (kind !== 'create') _lastTaskAssistantKind = kind;
  document.querySelectorAll('.ai-object-item[data-ai-object]').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.aiObject === kind);
  });
  const title = $('aiObjectEmptyTitle');
  const desc = $('aiObjectEmptyDesc');
  const topTitle = $('productModeTitle');
  const input = $('msg');
  if (title) title.textContent = object.title;
  if (desc) desc.textContent = object.desc;
  if (topTitle) topTitle.textContent = object.title;
  if (input) input.placeholder = object.placeholder;
  _syncAssistantHome(object);
  const buttons = Array.from(document.querySelectorAll('[data-ai-suggestion]'));
  object.suggestions.forEach((item, index) => {
    const btn = buttons[index];
    if (!btn) return;
    btn.dataset.msg = item[0];
    const label = btn.querySelector('span:last-child');
    if (label) label.textContent = item[1];
  });
  syncAssistantTaskUi();
  syncAssistantListMeta();
  const previewUrl = typeof currentAssistantPreviewUrl === 'function'
    ? currentAssistantPreviewUrl(kind)
    : (object.previewUrl || '');
  if (previewUrl && _assistantTaskHasActiveTask() && typeof refreshCurrentProductPreview === 'function') refreshCurrentProductPreview({silent:true});
  else _hideProductPreviewIfActive();
  if (typeof renderSessionListFromCache === 'function') renderSessionListFromCache();
}

function startAssistantNewTask() {
  const kind = _isCreatorMode() ? (_lastTaskAssistantKind || 'general') : _assistantKey();
  openAssistantHome(kind);
}

function openAssistantLanding(options = {}) {
  const kind = _isCreatorMode() ? (_lastTaskAssistantKind || 'general') : _assistantKey();
  openAssistantHome(kind, { ...options, directory: 'library' });
}

function _setAssistantHomeUrl() {
  if (typeof window === 'undefined' || !window.history) return;
  try {
    const current = new URL(window.location.href);
    const base = new URL(document.baseURI || '/', window.location.origin);
    current.searchParams.delete('session');
    const path = base.pathname || '/';
    const next = path + current.search + current.hash;
    const currentPath = window.location.pathname + window.location.search + window.location.hash;
    if (next && next !== currentPath) window.history.replaceState({}, '', next);
  } catch (_err) {}
}

function openAssistantHome(kind, options = {}) {
  if (typeof S !== 'undefined' && (S.busy || S.activeStreamId)) {
    if (typeof showToast === 'function') showToast('This task is still running. Start a new one when it finishes.');
    return;
  }
  _setAssistantDirectoryMode(options.directory === 'library' ? 'library' : 'product');
  if (kind) selectAiObject(kind);
  if (typeof S !== 'undefined') {
    S.session = null;
    S.messages = [];
    S.entries = [];
    S.toolCalls = [];
    S.activeStreamId = null;
    S.busy = false;
  }
  try { localStorage.removeItem('hermes-webui-session'); } catch (_err) {}
  if (options.replaceUrl !== false) _setAssistantHomeUrl();
  const inner = $('msgInner');
  const empty = $('emptyState');
  if (inner) inner.innerHTML = '';
  if (empty) empty.style.display = 'none';
  _hideProductPreviewIfActive();
  syncAssistantTaskUi();
  const input = $('msg');
  if (input) {
    const object = AI_OBJECTS[_assistantKey()] || AI_OBJECTS.ppt;
    input.placeholder = object.placeholder || input.placeholder;
    setTimeout(() => input.focus(), 0);
  }
  if (typeof syncTopbar === 'function') syncTopbar();
  if (typeof updateSendBtn === 'function') updateSendBtn();
}

function _assistantTaskNormalizeTitle(value) {
  return String(value == null ? '' : value).replace(/\s+/g, ' ').trim();
}

function _assistantTaskClampTitle(value, max = 36) {
  const title = _assistantTaskNormalizeTitle(value);
  if (!title) return '';
  return title.length > max ? `${title.slice(0, Math.max(1, max - 3))}...` : title;
}

function _assistantTaskCollapseRepeatedPrefix(value) {
  let title = _assistantTaskNormalizeTitle(value);
  for (let i = 0; i < 3; i += 1) {
    const next = title.replace(/^(.{1,12}版)\1+/, '$1');
    if (next === title) break;
    title = next;
  }
  return title;
}

function _assistantTaskCompactDisplayTitle(value) {
  const title = _assistantTaskCollapseRepeatedPrefix(value);
  if (!title) return '';

  const topicMatch = title.match(/主题\s*[：:]?\s*[「“"']([^」”"']{2,48})[」”"']/);
  if (topicMatch && topicMatch[1]) {
    const topic = _assistantTaskNormalizeTitle(topicMatch[1]);
    const audienceMatch = title.match(/受众\s*[：:]?\s*[「“"']([^」”"']{2,24})[」”"']/);
    const audience = audienceMatch ? _assistantTaskNormalizeTitle(audienceMatch[1]) : '';
    if (audience && !/^(客户|用户|大众|普通用户|所有人)$/i.test(audience)) {
      return _assistantTaskClampTitle(`${audience}版${topic}`);
    }
    return _assistantTaskClampTitle(topic);
  }

  const firstClause = title.split(/[，,。；;]/)[0] || title;
  let cleaned = firstClause
    .replace(/^(请|麻烦)?\s*(你)?\s*(帮我|给我|为我)?\s*(做|制作|生成|创建|设计|写|整理|优化|继续优化)\s*(一份|一个|一套|一下)?\s*/i, '')
    .replace(/^(把|将)\s*/, '')
    .replace(/\s*(吧|好吗|可以吗)$/i, '')
    .trim();
  if (/^这份\s*PPT/i.test(cleaned)) cleaned = '优化 PPT';
  return _assistantTaskClampTitle(cleaned || title);
}

function _assistantTaskLooksDefaultTitle(value) {
  const title = _assistantTaskNormalizeTitle(value);
  return !title || title === 'Untitled' || title === 'New Chat' || title === 'Session' || title === '未命名任务' || title === '刚开始的任务';
}

function _assistantTaskLooksGenericTitle(value) {
  const title = _assistantTaskNormalizeTitle(value);
  if (_assistantTaskLooksDefaultTitle(title)) return true;
  if (/^(AI productivity discussion|PowerPoint assistance|Presentation task|PPT task|Slide deck task)$/i.test(title)) return true;
  return /^(ppt|PPT|幻灯片|演示文稿|presentation|deck|slide deck)$/i.test(title);
}

function _assistantTaskLooksProductUiCommand(value) {
  const title = _assistantTaskNormalizeTitle(value);
  if (!title) return false;
  if (/^(请)?基于.*(产品画布|产品界面|工作界面|PPT 工作界面|继续优化)/.test(title)) return true;
  if (/^生成.*产品(画布|界面)$/.test(title)) return true;
  if (/^(请)?同步更新右侧/.test(title)) return true;
  if (/^(请)?(继续)?优化当前 PPT/.test(title)) return true;
  if (/^(生成页面|重排|收敛成|写\s*\d+\s*分钟讲稿|投资人审阅)/.test(title)) return true;
  return false;
}

function _assistantTaskFirstUserTitle() {
  const messages = (typeof S !== 'undefined' && Array.isArray(S.messages)) ? S.messages : [];
  const first = messages.find(message => message && message.role === 'user' && message.content);
  const title = first ? _assistantTaskCompactDisplayTitle(first.content) : '';
  if (title && typeof S !== 'undefined' && S.session && S.session.session_id) {
    rememberAssistantTaskTitle(S.session.session_id, title);
  }
  return title;
}

function _assistantTaskFirstUserMessage() {
  const messages = (typeof S !== 'undefined' && Array.isArray(S.messages)) ? S.messages : [];
  const first = messages.find(message => message && message.role === 'user' && message.content);
  if (!first) return '';
  const raw = typeof msgContent === 'function' ? msgContent(first) : first.content;
  return _assistantTaskNormalizeTitle(raw).slice(0, 160);
}

function _assistantTaskTitle() {
  const session = (typeof S !== 'undefined') ? S.session : null;
  const sessionTitle = session ? _assistantTaskNormalizeTitle(session.title) : '';
  const storedTitle = session && session.session_id ? _assistantTaskNormalizeTitle(_assistantTaskTitlesRead()[session.session_id]) : '';
  if (!_assistantTaskLooksGenericTitle(sessionTitle) && !_assistantTaskLooksProductUiCommand(sessionTitle)) return _assistantTaskCompactDisplayTitle(sessionTitle) || sessionTitle.slice(0, 48);
  const stableStoredTitle = !_assistantTaskLooksProductUiCommand(storedTitle) ? storedTitle : '';
  return (_assistantTaskCompactDisplayTitle(stableStoredTitle) || _assistantTaskFirstUserTitle() || 'Current task').slice(0, 48);
}

function assistantChromeTitleState() {
  const assistantTitle = window._currentAiAssistantTitle || window._currentAiProductTitle || 'PPT Designer';
  const hasTask = _assistantTaskHasActiveTask();
  const taskTitle = hasTask ? _assistantTaskTitle() : '';
  const main = hasTask ? taskTitle : assistantTitle;
  const sub = hasTask ? assistantTitle : 'AI product';
  return {
    main,
    sub,
    documentTitle: hasTask ? `${taskTitle} — ${assistantTitle} — Knead` : `${assistantTitle} — Knead`,
  };
}

function assistantDisplayTitleForSession(session) {
  const rawTitle = session ? _assistantTaskNormalizeTitle(session.display_title || session._state_db_title || session.title) : '';
  if (!_assistantTaskLooksGenericTitle(rawTitle) && !_assistantTaskLooksProductUiCommand(rawTitle)) return _assistantTaskCompactDisplayTitle(rawTitle) || rawTitle || 'Untitled';
  const storedTitle = session && session.session_id ? _assistantTaskNormalizeTitle(_assistantTaskTitlesRead()[session.session_id]) : '';
  if (storedTitle && !_assistantTaskLooksGenericTitle(storedTitle) && !_assistantTaskLooksProductUiCommand(storedTitle)) return _assistantTaskCompactDisplayTitle(storedTitle) || storedTitle;
  const hintedTitle = _assistantTaskTitleFromSessionHints(session);
  if (hintedTitle) return hintedTitle;
  return rawTitle && !_assistantTaskLooksGenericTitle(rawTitle) && !_assistantTaskLooksProductUiCommand(rawTitle) ? rawTitle : 'New task';
}

function _assistantTaskTitleFromSessionHints(session) {
  if (!session) return '';
  const candidates = [
    session.pending_user_message,
    session.first_user_message,
    session.last_user_message,
    session.user_message,
    session.initial_message,
    session.preview,
    session.last_message,
    session.summary
  ];
  for (const value of candidates) {
    const title = _assistantTaskCompactDisplayTitle(value);
    if (!title) continue;
    if (_assistantTaskLooksGenericTitle(title) || _assistantTaskLooksProductUiCommand(title)) continue;
    if (/^(好的|可以|当然|收到|明白|我先|我会|我可以|已|已经|下面|这里|这是)/.test(title)) continue;
    return title;
  }
  return '';
}

const _assistantTitleHydrationDone = new Set();
const _assistantTitleHydrationInFlight = new Set();

function _assistantMessageTextForTitle(message) {
  if (!message || message.role !== 'user') return '';
  if (typeof msgContent === 'function') {
    const text = _assistantTaskNormalizeTitle(msgContent(message));
    if (text) return text;
  }
  const content = message.content || message.text || '';
  if (Array.isArray(content)) {
    return _assistantTaskNormalizeTitle(content
      .filter(part => part && part.type === 'text')
      .map(part => part.text || part.content || '')
      .join(' '));
  }
  return _assistantTaskNormalizeTitle(content);
}

async function _hydrateAssistantDisplayTitle(session) {
  const sid = session && session.session_id;
  if (!sid || _assistantTitleHydrationDone.has(sid) || _assistantTitleHydrationInFlight.has(sid)) return false;
  const rawTitle = _assistantTaskNormalizeTitle(session.display_title || session._state_db_title || session.title);
  const storedTitle = _assistantTaskNormalizeTitle(_assistantTaskTitlesRead()[sid]);
  if (storedTitle && !_assistantTaskLooksGenericTitle(storedTitle) && !_assistantTaskLooksProductUiCommand(storedTitle)) {
    _assistantTitleHydrationDone.add(sid);
    return false;
  }
  if (!_assistantTaskLooksGenericTitle(rawTitle) && !_assistantTaskLooksProductUiCommand(rawTitle)) {
    _assistantTitleHydrationDone.add(sid);
    return false;
  }
  _assistantTitleHydrationInFlight.add(sid);
  try {
    const data = await api(`/api/session?session_id=${encodeURIComponent(sid)}&messages=1&resolve_model=0&msg_limit=6`);
    const messages = data && data.session && Array.isArray(data.session.messages) ? data.session.messages : [];
    const title = messages
      .filter(message => message && message.role === 'user')
      .map(message => _assistantTaskCompactDisplayTitle(_assistantMessageTextForTitle(message)))
      .find(candidate => candidate && !_assistantTaskLooksGenericTitle(candidate) && !_assistantTaskLooksProductUiCommand(candidate));
    if (title) {
      rememberAssistantTaskTitle(sid, title);
      _assistantTitleHydrationDone.add(sid);
      return true;
    }
    _assistantTitleHydrationDone.add(sid);
  } catch (_err) {
    _assistantTitleHydrationDone.add(sid);
  } finally {
    _assistantTitleHydrationInFlight.delete(sid);
  }
  return false;
}

function hydrateAssistantDisplayTitlesForSessions(sessions) {
  if (!Array.isArray(sessions) || typeof api !== 'function') return;
  const candidates = sessions
    .filter(session => session && session.session_id)
    .filter(session => !_assistantTitleHydrationDone.has(session.session_id))
    .filter(session => {
      const rawTitle = _assistantTaskNormalizeTitle(session.display_title || session._state_db_title || session.title);
      const storedTitle = _assistantTaskNormalizeTitle(_assistantTaskTitlesRead()[session.session_id]);
      if (storedTitle && !_assistantTaskLooksGenericTitle(storedTitle) && !_assistantTaskLooksProductUiCommand(storedTitle)) return false;
      return _assistantTaskLooksGenericTitle(rawTitle) || _assistantTaskLooksProductUiCommand(rawTitle);
    })
    .slice(0, 6);
  if (!candidates.length) return;
  Promise.all(candidates.map(session => _hydrateAssistantDisplayTitle(session)))
    .then(results => {
      if (results.some(Boolean) && typeof renderSessionListFromCache === 'function') renderSessionListFromCache();
    })
    .catch(() => {});
}

function _assistantTaskHasActiveTask() {
  if (typeof S === 'undefined' || !S.session) return false;
  const messages = Array.isArray(S.messages) ? S.messages : [];
  if (messages.some(message => message && message.role && message.role !== 'tool')) return true;
  return Number(S.session.message_count || 0) > 0 || !!S.session.pending_user_message || !!S.session.active_stream_id;
}

function _syncAssistantTaskContextStrip(hasTask = _assistantTaskHasActiveTask()) {
  const strip = $('assistantTaskContextStrip');
  if (!strip) return;
  const kicker = $('assistantTaskContextKicker');
  const title = $('assistantTaskContextTitle');
  const desc = $('assistantTaskContextDesc');
  const hasProductPreview = !!(_activeProductPreview && _activeProductPreview.product_preview);
  if (!hasTask || !hasProductPreview) {
    strip.hidden = true;
    if (kicker) kicker.textContent = 'Workspace';
    if (title) title.textContent = '';
    if (desc) desc.textContent = '';
    return;
  }
  strip.hidden = false;
  if (kicker) kicker.textContent = 'Workspace';
  if (title) title.textContent = (_activeProductPreview && (_activeProductPreview.name || _activeProductPreview.id)) || 'Current workspace';
  if (desc) {
    desc.textContent = 'The workspace is open. Keep chatting to refine the task.';
  }
}

function _syncAssistantTaskProgress(hasTask = _assistantTaskHasActiveTask()) {
  const progress = $('assistantTaskProgress');
  if (!progress) return;
  const title = $('assistantTaskProgressTitle');
  const desc = $('assistantTaskProgressDesc');
  const dot = $('assistantTaskProgressDot');
  const productUi = $('assistantTaskProgressProduct');
  const productUiKicker = $('assistantTaskProgressProductKicker');
  const productUiItem = document.querySelector('.assistant-task-progress-product-ui');
  const isRunning = !!(typeof S !== 'undefined' && (S.busy || S.activeStreamId || (S.session && S.session.active_stream_id)));
  if (!hasTask || !isRunning) {
    progress.hidden = true;
    progress.classList.remove('is-running', 'is-idle');
    return;
  }
  progress.hidden = false;
  const hasProductPreview = !!(_activeProductPreview && _activeProductPreview.product_preview);
  const productScope = String((S.session && S.session.product_scope) || '').trim();
  const isInit = productScope === 'product_init';
  const assistantTitle = window._currentAiAssistantTitle || window._currentAiProductTitle || 'current AI';
  const object = _assistantObject();
  const usesProductCanvas = typeof _assistantCanShowProductCanvas === 'function'
    ? _assistantCanShowProductCanvas(object)
    : typeof _assistantUsesProductCanvas === 'function'
    ? _assistantUsesProductCanvas(object)
    : !_assistantIsChatOnlyProduct(object);
  progress.classList.toggle('is-running', isRunning);
  progress.classList.remove('is-idle');
  if (dot) dot.setAttribute('aria-label', '任务运行中');
  if (title) title.textContent = isInit ? 'Creating the first workspace' : 'Working on this task';
  if (desc) {
    desc.textContent = isInit
      ? 'Keep adding topic, style, and output requirements.'
      : `"${assistantTitle}" is working. You can keep adding requirements.`;
  }
  if (productUiItem) productUiItem.hidden = !usesProductCanvas;
  if (productUiKicker) productUiKicker.textContent = 'Workspace';
  if (usesProductCanvas && productUi) {
    if (hasProductPreview) {
      productUi.textContent = (_activeProductPreview && _activeProductPreview.name) || 'Current workspace';
    } else if (isInit) {
      productUi.textContent = 'Creating first version';
    } else {
      productUi.textContent = '按需生成';
    }
  }
}

function _syncProductPreviewCopy() {
  const kicker = $('activeProductKicker');
  const nameEl = $('activeProductPreviewName');
  const versionEl = $('activeProductVersion');
  const note = $('activeProductNote');
  const regenerateBtn = $('regenerateProductUiBtn');
  const rollbackBtn = $('rollbackActiveProductBtn');
  const productCapabilitiesBtn = $('productCapabilitiesBtn');
  const collapseBtn = $('collapseActiveProductBtn');
  const moreBtn = $('activeProductMoreBtn');
  const moreWrap = document.querySelector('.active-product-more');
  const assistantTitle = window._currentAiAssistantTitle || window._currentAiProductTitle || 'Current AI';
  const taskTitle = _assistantTaskTitle();
  const isProductPreview = !!(_activeProductPreview && _activeProductPreview.product_preview);
  const productPreviewName = _activeProductPreview
    ? (_activeProductPreview.name || _activeProductPreview.id)
    : 'Workspace';
  const previousVersion = _activeProductPreview && _activeProductPreview.previous_version ? _activeProductPreview.previous_version : '';
  const canRollback = !!(_activeProductPreview && _activeProductPreview.can_rollback && previousVersion);
  if (kicker) kicker.textContent = isProductPreview ? 'Workspace' : assistantTitle;
  if (nameEl) nameEl.textContent = productPreviewName;
  if (versionEl) {
    versionEl.textContent = isProductPreview && canRollback ? ' · previous version available' : '';
    versionEl.title = isProductPreview && canRollback ? `可以恢复到上一版 ${previousVersion}` : '';
  }
  if (note) {
    if (isProductPreview) {
      const uiStatus = String(_activeProductPreview && _activeProductPreview.ui_status || '');
      note.textContent = uiStatus === 'generating'
        ? 'Creating workspace'
        : uiStatus === 'failed'
          ? (_activeProductPreview.ui_error_message || 'Workspace needs to be rebuilt')
          : !_activeProductPreview.entry_generated
            ? 'No workspace yet. Keep chatting, or create the first version.'
            : canRollback
              ? 'Ready. Keep chatting to shape it, or restore the previous version.'
              : 'Ready. Keep chatting to shape it.';
    } else {
      note.textContent = _assistantTaskHasActiveTask()
        ? `Current task: ${taskTitle}`
        : 'Workspace appears when needed';
    }
  }
  if (regenerateBtn) {
    regenerateBtn.hidden = !isProductPreview;
    regenerateBtn.textContent = _activeProductPreview && _activeProductPreview.entry_generated ? 'Rebuild workspace' : 'Create first version';
    regenerateBtn.title = `Create a workspace for "${productPreviewName}" from the current chat`;
    regenerateBtn.setAttribute('aria-label', regenerateBtn.title);
  }
  if (rollbackBtn) {
    rollbackBtn.hidden = !isProductPreview || !canRollback;
    rollbackBtn.disabled = !canRollback;
    rollbackBtn.textContent = 'Restore previous';
    rollbackBtn.title = canRollback
      ? `把「${productPreviewName}」恢复到上一版 ${previousVersion}`
      : `「${productPreviewName}」还没有上一版可恢复`;
    rollbackBtn.setAttribute('aria-label', rollbackBtn.title);
  }
  if (productCapabilitiesBtn) {
    productCapabilitiesBtn.hidden = !isProductPreview;
    productCapabilitiesBtn.textContent = 'Skills and tools';
    productCapabilitiesBtn.title = `调整「${productPreviewName}」的长期能力和可用工具`;
    productCapabilitiesBtn.setAttribute('aria-label', productCapabilitiesBtn.title);
  }
  if (collapseBtn) {
    collapseBtn.textContent = 'Hide';
    collapseBtn.title = `Hide "${assistantTitle}" workspace. Chat stays available.`;
    collapseBtn.setAttribute('aria-label', collapseBtn.title);
  }
  if (moreBtn) {
    moreBtn.textContent = 'More';
    moreBtn.title = 'Workspace actions';
    moreBtn.disabled = false;
    moreBtn.setAttribute('aria-label', moreBtn.title);
    moreBtn.onclick = toggleActiveProductPreviewMenu;
  }
  if (moreWrap) {
    moreWrap.hidden = !isProductPreview;
  }
}

function _focusActiveProductPreviewSurface() {
  const surface = $('activeProductSurface');
  if (!surface || surface.hidden) return false;
  surface.scrollIntoView({ behavior: 'smooth', block: 'start' });
  try { surface.focus({ preventScroll: true }); } catch (_err) {}
  return true;
}

async function openOrFocusTaskProductPreviewFromHeader() {
  if (_activeProductPreview && _focusActiveProductPreviewSurface()) return;
  if (typeof refreshCurrentProductPreview === 'function') {
    const opened = await refreshCurrentProductPreview({ focus: true, reason: 'header-open-product-preview' });
    if (opened) return;
  }
  if (typeof showToast === 'function') showToast('This task does not have a workspace yet.');
}

async function toggleTaskProductPreviewFromHeader() {
  if (_activeProductPreview) {
    if (typeof _hideProductPreviewIfActive === 'function') {
      _hideProductPreviewIfActive();
    } else {
      deactivateProductPreviewInChat();
    }
    return;
  }
  await openOrFocusTaskProductPreviewFromHeader();
}

function _currentProductLayoutForTaskHeader(object = _assistantObject()) {
  if (typeof _assistantEffectiveProductLayout === 'function') return _assistantEffectiveProductLayout(object);
  if (typeof _assistantProductLayout === 'function') return _assistantProductLayout(object);
  return _assistantIsChatOnlyProduct(object) ? 'chat_only' : 'chat_center';
}

function _isCanvasFullProductUseMode(object = _assistantObject()) {
  return _assistantTaskHasActiveTask() && _currentProductLayoutForTaskHeader(object) === 'canvas_full' && !!_activeProductPreview;
}

function _currentSessionIsProductBuilderLine(object = _assistantObject()) {
  if (!object || !object.productId || typeof S === 'undefined' || !S.session || !S.session.session_id) return false;
  const matchesProduct = typeof _currentSessionMatchesProduct === 'function'
    ? _currentSessionMatchesProduct(object)
    : String(S.session.product_id || S.session.productId || '') === String(object.productId || object.product_id || '');
  if (!matchesProduct) return false;
  const scope = String(S.session.product_scope || S.session.productScope || '').trim();
  return scope === 'product_builder' || scope === 'product_init';
}

async function ensureCurrentProductBuilderSession(object = _assistantObject(), options = {}) {
  if (!object || !object.productId) return false;
  if (_currentSessionIsProductBuilderLine(object)) {
    if (typeof S !== 'undefined' && S.session) {
      S.session.product_scope = 'product_builder';
      S.session.product_line = 'build';
    }
    return true;
  }
  if (typeof newSession !== 'function') return false;
  const assistantTitle = object.title || 'this AI';
  const taskTitle = options && options.taskTitle ? String(options.taskTitle) : `Shape ${assistantTitle}`;
  const productIntent = options && options.intent ? String(options.intent) : '';
  await newSession(false, {
    workspace: object.workspacePath || '',
    productId: object.productId,
    productScope: 'product_builder',
    productIntent,
    productTaskTitle: taskTitle
  });
  if (typeof S !== 'undefined' && S.session && S.session.session_id) {
    S.session.title = taskTitle;
    S.session.product_scope = 'product_builder';
    S.session.product_line = 'build';
    S.session.product_intent = productIntent;
    rememberAssistantTaskTitle(S.session.session_id, taskTitle);
    if (typeof applySessionTitleUpdate === 'function') {
      applySessionTitleUpdate(S.session.session_id, taskTitle, {force:true, rememberProvisional:true});
    }
    if (typeof upsertActiveSessionForLocalTurn === 'function') {
      upsertActiveSessionForLocalTurn({title:taskTitle, messageCount:S.messages && S.messages.length || 0, timestampMs:Date.now()});
    }
  }
  if (typeof renderSessionList === 'function') await renderSessionList();
  return true;
}

async function setCurrentProductAdjustMode(open, options = {}) {
  const next = !!open;
  if (next && typeof syncAssistantSelectionToSessionProduct === 'function') {
    syncAssistantSelectionToSessionProduct();
  }
  const object = _assistantObject();
  if (next && (_isCreatorMode() || !object || !object.productId)) {
    if (typeof showToast === 'function') showToast('Open a created AI before shaping it.');
    return;
  }
  if (next && typeof S !== 'undefined' && (S.busy || S.activeStreamId)) {
    if (typeof showToast === 'function') showToast('This task is still running. Shape it when it finishes.');
    return;
  }
  if (next) {
    try {
      const ready = await ensureCurrentProductBuilderSession(object, options);
      if (!ready) {
        if (typeof showToast === 'function') showToast('Could not open the shaping workspace for this AI.');
        return;
      }
    } catch (err) {
      if (typeof showToast === 'function') showToast(`Could not open Shape it: ${err && err.message || err}`, 3600, 'error');
      return;
    }
  }
  document.body.dataset.nextAiProductAdjust = next ? 'open' : 'closed';
  if (next) document.body.dataset.nextAiChatPanel = 'closed';
  const adjustHeader = $('productAdjustPanelHeader');
  if (adjustHeader) adjustHeader.hidden = !next;
  // 走完整同步,让侧画布(PPT)的 composer 文案、开关按钮标签随用/调切换刷新。
  if (typeof syncAssistantTaskUi === 'function') syncAssistantTaskUi();
  else _syncTaskHeaderStatus();
  if (next && options.focus !== false) {
    const input = $('msg');
    if (input) {
      setTimeout(() => {
        try { input.focus(); } catch (_err) {}
      }, 0);
    }
  }
}

function toggleCurrentProductAdjustMode() {
  void setCurrentProductAdjustMode(document.body.dataset.nextAiProductAdjust !== 'open');
}

function setCurrentProductChatPanelMode(open, options = {}) {
  const next = !!open;
  document.body.dataset.nextAiChatPanel = next ? 'open' : 'closed';
  if (!(options && options.auto)) {
    document.body.dataset.nextAiChatPanelManual = next ? 'open' : 'closed';
  }
  if (next) {
    document.body.dataset.nextAiProductAdjust = 'closed';
    const adjustHeader = $('productAdjustPanelHeader');
    if (adjustHeader) adjustHeader.hidden = true;
  }
  if (typeof syncAssistantTaskUi === 'function') syncAssistantTaskUi();
  else _syncTaskHeaderStatus();
  if (next && options.focus !== false) {
    const input = $('msg');
    if (input) {
      setTimeout(() => {
        try { input.focus(); } catch (_err) {}
      }, 0);
    }
  }
}

function toggleCurrentProductChatPanelMode() {
  setCurrentProductChatPanelMode(document.body.dataset.nextAiChatPanel !== 'open');
}

window.setCurrentProductAdjustMode = setCurrentProductAdjustMode;
window.toggleCurrentProductAdjustMode = toggleCurrentProductAdjustMode;
window.setCurrentProductChatPanelMode = setCurrentProductChatPanelMode;
window.toggleCurrentProductChatPanelMode = toggleCurrentProductChatPanelMode;

function _syncTaskHeaderProductPreviewChipAction({ isCreate, canOpenProductPreview, canCreateWorkspace, label, createDraftReady, createDraftPublished }) {
  const productPreviewStatus = $('taskHeaderProductStatus');
  if (!productPreviewStatus) return;
  const actionable = isCreate
    ? !!(createDraftReady && !createDraftPublished)
    : (canOpenProductPreview || canCreateWorkspace);
  productPreviewStatus.classList.toggle('is-actionable', actionable);
  if (actionable) {
    productPreviewStatus.setAttribute('role', 'button');
    productPreviewStatus.setAttribute('tabindex', '0');
    productPreviewStatus.setAttribute(
      'aria-label',
      isCreate
        ? 'Add this AI to the shelf'
        : canOpenProductPreview
        ? (_activeProductPreview ? `Close workspace: ${label}` : `Open workspace: ${label}`)
        : `Create workspace: ${label}`
    );
    productPreviewStatus.onclick = () => {
      if (isCreate && createDraftReady && !createDraftPublished && typeof publishCreatorDraft === 'function') {
        publishCreatorDraft({silent:false});
      } else if (canOpenProductPreview) {
        toggleTaskProductPreviewFromHeader();
      } else if (canCreateWorkspace && typeof requestCurrentProductUiGeneration === 'function') {
        requestCurrentProductUiGeneration();
      }
    };
    productPreviewStatus.onkeydown = event => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      productPreviewStatus.click();
    };
  } else {
    productPreviewStatus.removeAttribute('role');
    productPreviewStatus.removeAttribute('tabindex');
    productPreviewStatus.removeAttribute('aria-label');
    productPreviewStatus.onclick = null;
    productPreviewStatus.onkeydown = null;
  }
}

function _syncTaskHeaderStatus(hasTask = _assistantTaskHasActiveTask()) {
  const chatStatus = $('taskHeaderChatStatus');
  const productPreviewStatus = $('taskHeaderProductStatus');
  const chatText = chatStatus ? chatStatus.querySelector('span:last-child') : null;
  const productPreviewText = productPreviewStatus ? productPreviewStatus.querySelector('span:last-child') : null;
  const isCreate = _isCreatorMode();
  const creatorDraftStatus = isCreate ? _currentCreatorDraftStatus() : null;
  const creatorDraftPhase = isCreate ? _creatorDraftPhase(creatorDraftStatus) : null;
  const creatorDraftReady = !!(creatorDraftStatus && creatorDraftStatus.ready);
  const creatorDraftPublished = !!(creatorDraftStatus && creatorDraftStatus.published);
  const object = isCreate ? AI_OBJECTS.create : _assistantObject();
  const assistantTitle = (object && object.title) || window._currentAiAssistantTitle || window._currentAiProductTitle || 'Current AI';
  const canAdjustProduct = !isCreate && !!(object && object.productId);
  const usesProductCanvas = isCreate || (
    typeof _assistantCanShowProductCanvas === 'function'
      ? _assistantCanShowProductCanvas(object)
      : typeof _assistantUsesProductCanvas === 'function'
      ? _assistantUsesProductCanvas(object)
      : !_assistantIsChatOnlyProduct(object)
  );
  const activeProductPreviewName = _activeProductPreview
    ? (_activeProductPreview.name || _activeProductPreview.id || 'Workspace')
    : '';
  const adjustOpen = document.body.dataset.nextAiProductAdjust === 'open';
  const chatPanelOpen = document.body.dataset.nextAiChatPanel === 'open';
  const canvasOpen = usesProductCanvas && !!_activeProductPreview;
  const canToggleChatPanel = !isCreate && hasTask && canvasOpen && _currentProductLayoutForTaskHeader(object) === 'chat_left_canvas_right';
  const canOpenProductPreview = usesProductCanvas && !!(
    _activeProductPreview ||
    typeof _assistantHasGeneratedProductCanvas === 'function' && _assistantHasGeneratedProductCanvas(object)
  );
  const workspaceStatus = String(object && (object.uiStatus || object.ui_status) || '').toLowerCase();
  const canCreateWorkspace = !isCreate && !!(object && object.productId) && usesProductCanvas && !canOpenProductPreview && (
    !workspaceStatus || workspaceStatus === 'empty' || workspaceStatus === 'failed'
  );
  // 用/调是产品级入口:不依赖是否已经长出画布。
  const adjustToggle = $('taskHeaderAdjustToggle');
  if (adjustToggle) {
    adjustToggle.hidden = !canAdjustProduct;
    adjustToggle.disabled = !canAdjustProduct;
    if (canAdjustProduct) {
      adjustToggle.classList.toggle('is-adjust-product', adjustOpen);
      adjustToggle.classList.toggle('is-actionable', true);
      adjustToggle.setAttribute('aria-pressed', adjustOpen ? 'true' : 'false');
      adjustToggle.setAttribute('aria-label', adjustOpen ? `Stop shaping ${assistantTitle}` : `Shape ${assistantTitle}`);
      const adjustLabel = adjustToggle.querySelector('span:last-child');
      if (adjustLabel) adjustLabel.textContent = adjustOpen ? 'Done shaping' : 'Shape it';
      adjustToggle.title = adjustOpen ? 'Go back to using this AI' : 'Tell the AI how this product should work better';
    } else {
      adjustToggle.classList.remove('is-adjust-product', 'is-actionable');
      adjustToggle.setAttribute('aria-pressed', 'false');
      adjustToggle.removeAttribute('aria-label');
      adjustToggle.title = '';
    }
  }
  if (productPreviewStatus) productPreviewStatus.classList.remove('is-adjust-product');
  if (chatStatus) chatStatus.hidden = false;
  if (chatText) {
    chatText.textContent = isCreate
      ? creatorDraftPhase.chatLabel
      : adjustOpen
        ? 'Shaping'
        : chatPanelOpen
          ? 'Chatting'
        : 'Using';
  }
  if (productPreviewStatus) {
    productPreviewStatus.hidden = !isCreate && !canAdjustProduct && !usesProductCanvas;
  }
  if (productPreviewText) {
    if (isCreate) {
      productPreviewText.textContent = creatorDraftPhase.shelfLabel;
    } else if (_activeProductPreview) {
      productPreviewText.textContent = 'Close workspace';
    } else if (canOpenProductPreview) {
      productPreviewText.textContent = 'Open workspace';
    } else if (workspaceStatus === 'generating') {
      productPreviewText.textContent = 'Workspace building';
    } else if (canCreateWorkspace) {
      productPreviewText.textContent = workspaceStatus === 'failed' ? 'Rebuild workspace' : 'Create workspace';
    } else if (canAdjustProduct) {
      productPreviewText.textContent = 'Chat only';
    } else {
      productPreviewText.textContent = 'Workspace off';
    }
  }
  if (productPreviewStatus) {
    productPreviewStatus.classList.toggle('is-active-product', !isCreate && !!_activeProductPreview);
    const label = productPreviewText ? productPreviewText.textContent : '';
    const workspaceName = activeProductPreviewName || (typeof _assistantCanvasLabel === 'function' ? _assistantCanvasLabel(object) : '') || 'workspace';
    productPreviewStatus.title = usesProductCanvas && !isCreate && canOpenProductPreview
      ? (_activeProductPreview ? `Close ${workspaceName}` : `Open ${workspaceName}`)
      : canCreateWorkspace
        ? `Create ${workspaceName}`
        : canAdjustProduct && !usesProductCanvas
          ? 'This AI currently uses the default chat page. Use Shape it if it needs its own workspace.'
          : label;
    _syncTaskHeaderProductPreviewChipAction({
      isCreate,
      canOpenProductPreview,
      canCreateWorkspace,
      label: workspaceName,
      createDraftReady: creatorDraftReady,
      createDraftPublished: creatorDraftPublished
    });
  }
  if (chatStatus) {
    chatStatus.classList.toggle('is-actionable', canToggleChatPanel);
    chatStatus.title = isCreate
      ? creatorDraftPhase.composer
      : canToggleChatPanel
        ? (chatPanelOpen ? 'Collapse chat' : 'Open chat')
        : adjustOpen
          ? `Shaping ${assistantTitle}`
        : hasTask
          ? `Current task handled by "${assistantTitle}"`
          : `Start using "${assistantTitle}" here`;
    if (canToggleChatPanel) {
      chatStatus.setAttribute('role', 'button');
      chatStatus.setAttribute('tabindex', '0');
      chatStatus.setAttribute('aria-label', chatPanelOpen ? 'Hide chat' : 'Open chat');
      chatStatus.onclick = () => toggleCurrentProductChatPanelMode();
      chatStatus.onkeydown = event => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        event.preventDefault();
        toggleCurrentProductChatPanelMode();
      };
    } else {
      chatStatus.removeAttribute('role');
      chatStatus.removeAttribute('tabindex');
      chatStatus.removeAttribute('aria-label');
      chatStatus.onclick = null;
      chatStatus.onkeydown = null;
    }
  }
}

function _syncAssistantSidebarIntro(hasTask = _assistantTaskHasActiveTask()) {
  const sub = $('assistantPanelSub');
  if (!sub) return;
  const assistantTitle = window._currentAiAssistantTitle || window._currentAiProductTitle || 'Current AI';
  const isCreate = _isCreatorMode();
  const directoryMode = _assistantDirectoryMode(hasTask);
  if (directoryMode === 'library' && !hasTask) {
    sub.textContent = 'Choose an AI, then open its tasks.';
  } else if (isCreate) {
    sub.textContent = 'Describe the AI you want to create.';
  } else if (hasTask) {
    sub.textContent = `${assistantTitle} 的任务`;
  } else {
    sub.textContent = 'Start a new task, or open a previous one.';
  }
}

function _syncAssistantSidebarDirectory(hasTask = _assistantTaskHasActiveTask()) {
  const mode = hasTask ? 'product' : _assistantDirectoryMode(hasTask);
  _setAssistantDirectoryMode(mode);
  const isLibrary = mode === 'library';
  const isCreate = _isCreatorMode();
  const object = isCreate ? AI_OBJECTS.create : _assistantObject();
  const assistantTitle = (object && object.title) || window._currentAiAssistantTitle || 'Current AI';
  const panelTitle = $('assistantPanelTitle');
  const back = $('assistantProductBackBtn');
  const listTitle = $('assistantTaskListTitle');
  const search = $('sessionSearch');
  const newTaskBtn = $('newTaskPrimaryBtn');
  if (panelTitle) panelTitle.textContent = isLibrary ? 'AI shelf' : assistantTitle;
  if (back) back.hidden = isLibrary;
  if (listTitle) {
    listTitle.textContent = isLibrary
      ? 'Recent activity'
      : isCreate
        ? 'Create'
        : 'Tasks';
  }
  if (search) {
    search.placeholder = isLibrary
      ? 'Search recent activity'
      : isCreate
      ? 'Search tasks after creating it...'
      : `Search ${assistantTitle} tasks`;
  }
  if (newTaskBtn) {
    newTaskBtn.hidden = isLibrary;
  }
}

function syncAssistantTaskUi() {
  const creatorMode = _isCreatorMode();
  if (creatorMode) _maybeRefreshCreatorDraftStatus();
  const creatorDraftStatus = creatorMode ? _currentCreatorDraftStatus() : null;
  const creatorDraftPhase = creatorMode ? _creatorDraftPhase(creatorDraftStatus) : null;
  const currentObject = creatorMode ? AI_OBJECTS.create : _assistantObject();
  const assistantTitle = creatorMode
    ? 'Knead Creator'
    : ((currentObject && currentObject.title) || window._currentAiAssistantTitle || window._currentAiProductTitle || 'PPT Designer');
  const productLayout = _currentProductLayoutForTaskHeader(currentObject);
  const canAdjustProduct = !creatorMode && !!(currentObject && currentObject.productId);
  const usesProductCanvas = typeof _assistantCanShowProductCanvas === 'function'
    ? _assistantCanShowProductCanvas(currentObject)
    : typeof _assistantUsesProductCanvas === 'function'
    ? _assistantUsesProductCanvas(currentObject)
    : productLayout !== 'chat_only';
  const root = $('productCrumbRoot');
  const title = $('productModeTitle');
  const listTitle = $('assistantTaskListTitle');
  const search = $('sessionSearch');
  const input = $('msg');
  const home = $('assistantHome');
  const messagesShell = document.querySelector('.messages-shell');
  const adjustHeader = $('productAdjustPanelHeader');
  const activeProductSurface = $('activeProductSurface');
  const body = $('productChatBody');
  const hasTask = _assistantTaskHasActiveTask();
  const taskTitle = _assistantTaskTitle();
  if (!usesProductCanvas && _activeProductPreview && _activeProductPreview.product_preview) {
    if (typeof _hideProductPreviewIfActive === 'function') {
      _hideProductPreviewIfActive({sync:false});
    } else {
      const frame = $('activeProductFrame');
      const previewState = $('productPreviewState');
      if (activeProductSurface) activeProductSurface.hidden = true;
      if (frame) frame.removeAttribute('src');
      if (previewState) previewState.hidden = true;
      if (body) body.classList.remove('has-active-product');
      _activeProductPreview = null;
      _syncProductPreviewMode(null);
    }
  }
  document.body.dataset.nextAiView = hasTask ? 'task' : 'assistant';
  document.body.dataset.nextAiProductLayout = productLayout;
  document.body.dataset.nextAiCanvas = usesProductCanvas && _activeProductPreview ? 'open' : 'closed';
  const canvasFullUseMode = hasTask && productLayout === 'canvas_full' && usesProductCanvas && !!_activeProductPreview;
  const canvasOpen = usesProductCanvas && !!_activeProductPreview;
  const sideCanvasUseMode = hasTask && productLayout === 'chat_left_canvas_right' && canvasOpen;
  const adjustableUseMode = canAdjustProduct;
  if (!adjustableUseMode) document.body.dataset.nextAiProductAdjust = 'closed';
  else if (!document.body.dataset.nextAiProductAdjust) document.body.dataset.nextAiProductAdjust = 'closed';
  const adjustOpen = adjustableUseMode && document.body.dataset.nextAiProductAdjust === 'open';
  if (!hasTask || !canvasOpen || canvasFullUseMode) {
    document.body.dataset.nextAiChatPanel = 'closed';
    delete document.body.dataset.nextAiChatPanelManual;
  } else if (adjustOpen) {
    document.body.dataset.nextAiChatPanel = 'closed';
  } else if (sideCanvasUseMode) {
    const manualChatPanel = document.body.dataset.nextAiChatPanelManual;
    document.body.dataset.nextAiChatPanel = manualChatPanel === 'closed' ? 'closed' : 'open';
  } else if (!document.body.dataset.nextAiChatPanel) {
    document.body.dataset.nextAiChatPanel = 'closed';
  }
  if (adjustHeader) adjustHeader.hidden = !adjustOpen;
  if (body) body.dataset.nextAiView = hasTask ? 'task' : 'assistant';
  if (title) title.textContent = assistantTitle;
  if (root) {
    root.hidden = !hasTask || canvasFullUseMode;
    root.textContent = hasTask ? taskTitle : '';
    root.title = hasTask ? taskTitle : '';
  }
  if (listTitle) listTitle.textContent = creatorMode ? 'Create' : 'Tasks';
  if (search) search.placeholder = creatorMode
    ? 'Search tasks after creating it...'
    : 'Search tasks';
  if (input) {
    const object = creatorMode ? AI_OBJECTS.create : (AI_OBJECTS[_assistantKey()] || AI_OBJECTS.ppt);
    input.placeholder = adjustOpen
      ? `Tell "${assistantTitle}" how this AI should work better...`
      : creatorMode
        ? creatorDraftPhase.composer
      : hasTask
        ? `Continue "${taskTitle}"...`
        : (object.placeholder || input.placeholder);
  }
  if (home) home.hidden = hasTask || adjustOpen;
  if (messagesShell) messagesShell.hidden = !hasTask && !adjustOpen;
  if (!hasTask && !adjustOpen) {
    if (activeProductSurface) activeProductSurface.hidden = true;
    if (body) body.classList.remove('has-active-product');
  }
  if (!hasTask) {
    const empty = $('emptyState');
    if (empty) empty.style.display = 'none';
    _syncAssistantHome(creatorMode ? AI_OBJECTS.create : (AI_OBJECTS[_assistantKey()] || AI_OBJECTS.ppt));
  }
  _syncAssistantTaskContextStrip(hasTask);
  _syncAssistantTaskProgress(hasTask);
  if (_activeProductPreview) _syncProductPreviewCopy();
  _syncAssistantSidebarDirectory(hasTask);
  _syncAssistantSidebarIntro(hasTask);
  _syncTaskHeaderStatus(hasTask);
  return true;
}

function deactivateProductPreviewInChat() {
  const activeProductPreviewName = _activeProductPreview ? (_activeProductPreview.name || _activeProductPreview.id) : '';
  const surface = $('activeProductSurface');
  const frame = $('activeProductFrame');
  const body = $('productChatBody');
  if (surface) surface.hidden = true;
  if (frame) frame.removeAttribute('src');
  if (body) body.classList.remove('has-active-product');
  if (document.body && document.body.dataset) {
    document.body.dataset.nextAiChatPanel = 'closed';
    delete document.body.dataset.nextAiChatPanelManual;
  }
  _activeProductPreview = null;
  _syncProductPreviewMode(null);
  _syncAssistantTaskContextStrip();
  _syncAssistantTaskProgress();
  if (typeof showToast === 'function' && activeProductPreviewName) {
    showToast(`Hidden "${activeProductPreviewName}"`);
  }
}

function openActiveProductPreviewWindow() {
  if (_activeProductPreview && _activeProductPreview.preview_url) {
    window.open(_activeProductPreview.preview_url, '_blank');
  }
}

function initNextAiAssistants() {
  try { localStorage.removeItem('next-ai-custom-assistants'); } catch (_err) {}
  renderAssistantList();
  hydrateProductsFromBackend();
  syncAssistantListMeta();
  syncAssistantTaskUi();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => initNextAiAssistants(), { once: true });
} else {
  initNextAiAssistants();
}

// ── Draggable chat/canvas splitter (two-pane chat_left_canvas_right) ──
(function wirePaneResizer() {
  function init() {
    const r = document.getElementById('paneResizer');
    const body = document.getElementById('productChatBody');
    if (!r || !body) return;
    try { const w = localStorage.getItem('nextai-chat-pane-w'); if (w) body.style.setProperty('--chat-pane-w', w); } catch (_) {}
    let dragging = false;
    const onMove = (e) => {
      if (!dragging) return;
      const rect = body.getBoundingClientRect();
      const min = 300, max = Math.max(min, rect.width - 360);
      let w = Math.max(min, Math.min(max, e.clientX - rect.left));
      body.style.setProperty('--chat-pane-w', w + 'px');
    };
    const stop = () => {
      if (!dragging) return;
      dragging = false; r.classList.remove('is-dragging');
      document.body.style.userSelect = ''; document.body.style.cursor = '';
      try { localStorage.setItem('nextai-chat-pane-w', body.style.getPropertyValue('--chat-pane-w')); } catch (_) {}
    };
    r.addEventListener('mousedown', (e) => {
      dragging = true; r.classList.add('is-dragging');
      document.body.style.userSelect = 'none'; document.body.style.cursor = 'col-resize';
      e.preventDefault();
    });
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', stop);
    // Double-click resets to the default ratio.
    r.addEventListener('dblclick', () => { body.style.removeProperty('--chat-pane-w'); try { localStorage.removeItem('nextai-chat-pane-w'); } catch (_) {} });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
