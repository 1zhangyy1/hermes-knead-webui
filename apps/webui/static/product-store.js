const NEXT_AI_PRODUCT_SKILL_OPTIONS = [
  { id: 'presentations', label: 'Presentations', desc: 'Create and edit decks' },
  { id: 'office', label: 'Office files', desc: 'Work with PPTX, docs, and exports' },
  { id: 'imagegen', label: 'Image generation', desc: 'Create or edit images' },
  { id: 'browser', label: 'Web research', desc: 'Browse and collect sources' },
  { id: 'spreadsheets', label: 'Spreadsheets', desc: 'Analyze sheets and data' }
];
const NEXT_AI_PRODUCT_TOOL_OPTIONS = [
  { id: 'skills', label: 'Skills', desc: 'Use installed specialist skills' },
  { id: 'file', label: 'Files', desc: 'Read and update product files' },
  { id: 'terminal', label: 'Terminal', desc: 'Run local commands' },
  { id: 'code_execution', label: 'Code', desc: 'Run code and scripts' },
  { id: 'browser', label: 'Browser', desc: 'Open pages and gather context' },
  { id: 'web', label: 'Web search', desc: 'Search the public web' },
  { id: 'image_gen', label: 'Image generation', desc: 'Create or edit images' }
];
const NEXT_AI_PRODUCT_TOOLSET_ALIASES = {
  officecli: ['skills', 'file', 'terminal', 'code_execution'],
  'office-cli': ['skills', 'file', 'terminal', 'code_execution'],
  'image-generation': ['image_gen'],
  imagegen: ['image_gen'],
  'web-research': ['browser', 'web'],
  'spreadsheet-analysis': ['skills', 'file', 'terminal', 'code_execution']
};

function _assistantUniqueCapabilityList(items) {
  const seen = new Set();
  const result = [];
  for (const item of Array.isArray(items) ? items : []) {
    const value = String(item || '').trim();
    if (!value || seen.has(value)) continue;
    seen.add(value);
    result.push(value);
  }
  return result;
}

function _assistantNormalizeToolsets(items) {
  const result = [];
  const seen = new Set();
  for (const item of _assistantUniqueCapabilityList(items)) {
    const replacements = NEXT_AI_PRODUCT_TOOLSET_ALIASES[item] || [item];
    for (const replacement of replacements) {
      const value = String(replacement || '').trim();
      if (!value || seen.has(value)) continue;
      seen.add(value);
      result.push(value);
    }
  }
  return result;
}

function _assistantProductBacked(item) {
  return !!(item && (item.backendProduct || item.productId || item.product_id));
}

function _assistantNormalizeProductLayout(value = '', productType = '', uiMode = '') {
  const raw = String(value || '').trim();
  if (String(uiMode || '').trim() === 'chat_only') return 'chat_only';
  if (raw === 'chat_only' || raw === 'chat_center' || raw === 'chat_left_canvas_right' || raw === 'canvas_full') return raw;
  if (productType === 'ppt' || productType === 'research' || productType === 'data' || productType === 'image') {
    return 'chat_left_canvas_right';
  }
  return 'chat_center';
}

function _assistantProductLayout(object) {
  if (!object) return 'chat_center';
  return _assistantNormalizeProductLayout(
    object.productLayout || object.product_layout || object.layout,
    object.productType || object.product_type || '',
    object.uiMode || object.ui_mode || ''
  );
}

function _assistantUsesProductCanvas(object) {
  const layout = _assistantProductLayout(object);
  return layout === 'chat_left_canvas_right' || layout === 'canvas_full';
}

function _assistantHasGeneratedProductCanvas(object) {
  const productId = String(object && (object.productId || object.product_id) || '').trim();
  // 通用 AI 是产品孵化场,永不就地长画布:可复用的东西走升格成独立产品(B),
  // 保持它作为「什么都能问」入口的稳定身份。其它自建 chat_only 产品仍可经调态长画布。
  if (productId === 'general' || String(object && object.kind || '') === 'general') return false;
  const activeMatches = !!(
    productId &&
    typeof _activeProductPreview !== 'undefined' &&
    _activeProductPreview &&
    String(_activeProductPreview.product_id || '') === productId &&
    _activeProductPreview.product_preview
  );
  return !!(
    object && (
      object.entryGenerated ||
      object.entry_generated ||
      object.productCanvasAvailable ||
      object.product_canvas_available
    ) ||
    activeMatches
  );
}

function _assistantCanShowProductCanvas(object) {
  return _assistantUsesProductCanvas(object) || _assistantHasGeneratedProductCanvas(object);
}

function _assistantEffectiveProductLayout(object) {
  const layout = _assistantProductLayout(object);
  if (layout === 'chat_only' && _assistantHasGeneratedProductCanvas(object)) return 'chat_left_canvas_right';
  return layout;
}

function _assistantCanvasLabel(object) {
  const explicit = String(object && (object.canvasLabel || object.canvas_label) || '').trim();
  if (explicit) return explicit;
  const productType = String(object && (object.productType || object.product_type) || '').trim();
  if (productType === 'ppt') return 'PPT workspace';
  if (productType === 'image') return 'Image workspace';
  if (productType === 'research') return 'Research workspace';
  if (productType === 'data') return 'Data workspace';
  return 'Workspace';
}

function _normalizeBuiltinProductCopy(product) {
  const id = String(product && (product.id || product.productId) || '').trim();
  const kind = String(product && product.kind || '').trim();
  if (id === 'ppt-designer' || kind === 'ppt') {
    return {
      title: 'PPT Designer',
      desc: 'Tell me the topic, audience, and goal. I will shape the outline, slides, and speaker notes.',
      canvasLabel: 'PPT workspace'
    };
  }
  if (id === 'general' || kind === 'general') {
    return {
      title: 'General AI',
      desc: 'Use chat for one-off work. Repeated workflows can become their own AI.',
      canvasLabel: 'Workspace'
    };
  }
  return null;
}

function _assistantDateToMs(value) {
  const parsed = Date.parse(String(value || ''));
  return Number.isFinite(parsed) ? parsed : Date.now();
}

function _productToCustomAssistant(product) {
  if (!product || !product.id) return null;
  const builtinCopy = _normalizeBuiltinProductCopy(product);
  const title = (builtinCopy && builtinCopy.title) || product.title || 'AI product';
  const sourcePrompt = product.source_prompt || product.sourcePrompt || '';
  const productType = product.product_type || product.productType || 'custom';
  const uiMode = product.ui_mode || product.uiMode || 'workspace';
  const productLayout = product.product_layout || product.productLayout || product.layout || '';
  const uiStatus = product.ui_status || 'empty';
  const entryGenerated = !!(product.entry_generated || product.entryGenerated);
  const hasReadyPreview = !!(product.preview_url || product.previewUrl) && uiStatus === 'ready' && uiMode !== 'chat_only';
  const productCanvasAvailable = entryGenerated || !!(product.product_canvas_available || product.productCanvasAvailable) || uiStatus === 'generating' || hasReadyPreview;
  const starterKit = _assistantStarterKit(title, sourcePrompt || product.desc || '');
  return {
    kind: product.kind || `custom-${product.id}`,
    title,
    avatar: product.avatar || '',
    desc: (builtinCopy && builtinCopy.desc) || product.desc || 'Describe the job it should own. A workspace appears when structure helps.',
    placeholder: product.placeholder || starterKit.placeholder,
    suggestions: Array.isArray(product.suggestions) && product.suggestions.length ? product.suggestions : starterKit.suggestions,
    sourcePrompt,
    titleSource: 'backend-product',
    createdAt: product.created_at ? _assistantDateToMs(product.created_at) : Date.now(),
    productType,
    uiMode,
    productLayout,
    canvasLabel: (builtinCopy && builtinCopy.canvasLabel) || product.canvas_label || product.canvasLabel || '',
    productId: product.id,
    workspacePath: product.workspace_path || '',
    previewUrl: product.preview_url || '',
    uiStatus,
    uiErrorType: product.ui_error_type || '',
    uiErrorMessage: product.ui_error_message || '',
    entryGenerated,
    entry_generated: entryGenerated,
    productCanvasAvailable,
    product_canvas_available: productCanvasAvailable,
    skills: Array.isArray(product.skills) ? product.skills : [],
    tools: _assistantNormalizeToolsets(product.tools),
    backendProduct: true
  };
}

function _customAssistantMergeKey(item) {
  if (!item) return '';
  if (item.productId || item.product_id) return `product:${item.productId || item.product_id}`;
  return `kind:${item.kind || ''}`;
}

function _mergeCustomAssistants(existing, incoming) {
  const merged = new Map();
  for (const item of Array.isArray(existing) ? existing : []) {
    const key = _customAssistantMergeKey(item);
    if (key) merged.set(key, item);
  }
  for (const item of Array.isArray(incoming) ? incoming : []) {
    const key = _customAssistantMergeKey(item);
    if (!key) continue;
    const previous = merged.get(key) || {};
    merged.set(key, {
      ...previous,
      ...item,
    });
  }
  return Array.from(merged.values()).filter(item => item && item.kind && item.title);
}

function _isBuiltinAssistantKind(kind) {
  const key = String(kind || '').trim();
  return !!(key && AI_OBJECTS[key] && !AI_OBJECTS[key].custom && key !== 'create');
}

function _applyBackendProductToBuiltin(product, assistant = null) {
  const payload = assistant || _productToCustomAssistant(product);
  const kind = payload && payload.kind ? payload.kind : '';
  if (!_isBuiltinAssistantKind(kind)) return null;
  const object = AI_OBJECTS[kind];
  object.title = payload.title || object.title;
  object.avatar = payload.avatar || object.avatar || '';
  object.desc = payload.desc || object.desc;
  object.placeholder = payload.placeholder || object.placeholder;
  object.suggestions = Array.isArray(payload.suggestions) && payload.suggestions.length ? payload.suggestions : object.suggestions;
  object.sourcePrompt = payload.sourcePrompt || object.sourcePrompt || '';
  object.productType = payload.productType || object.productType || '';
  object.uiMode = payload.uiMode || payload.ui_mode || object.uiMode || 'workspace';
  object.productLayout = payload.productLayout || payload.product_layout || object.productLayout || '';
  object.canvasLabel = payload.canvasLabel || payload.canvas_label || object.canvasLabel || '';
  object.productId = payload.productId || object.productId || '';
  object.workspacePath = payload.workspacePath || object.workspacePath || '';
  object.previewUrl = payload.previewUrl || object.previewUrl || '';
  object.uiStatus = payload.uiStatus || payload.ui_status || object.uiStatus || 'empty';
  object.uiErrorType = payload.uiErrorType || payload.ui_error_type || '';
  object.uiErrorMessage = payload.uiErrorMessage || payload.ui_error_message || '';
  object.entryGenerated = !!(payload.entryGenerated || payload.entry_generated);
  object.entry_generated = object.entryGenerated;
  object.productCanvasAvailable = !!(payload.productCanvasAvailable || payload.product_canvas_available || object.entryGenerated);
  object.product_canvas_available = object.productCanvasAvailable;
  object.skills = Array.isArray(payload.skills) ? payload.skills : (Array.isArray(object.skills) ? object.skills : []);
  object.tools = Array.isArray(payload.tools) ? _assistantNormalizeToolsets(payload.tools) : _assistantNormalizeToolsets(object.tools);
  object.backendProduct = true;
  object.builtinProduct = true;
  object.custom = false;
  return object;
}

function _assistantKindForProductId(productId) {
  const id = String(productId || '').trim();
  if (!id) return '';
  for (const [kind, object] of Object.entries(AI_OBJECTS)) {
    if (object && String(object.productId || object.product_id || '') === id) return kind;
  }
  const stored = _customAssistantsRead().find(item => item && String(item.productId || item.product_id || '') === id);
  return stored && stored.kind ? stored.kind : '';
}

function _applyBackendProductToLocal(product) {
  const assistant = _productToCustomAssistant(product);
  if (!assistant) return null;
  if (_isBuiltinAssistantKind(assistant.kind)) {
    const object = _applyBackendProductToBuiltin(product, assistant);
    renderAssistantList();
    document.querySelectorAll('.ai-object-item[data-ai-object]').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.aiObject === _assistantKey());
    });
    syncAssistantListMeta();
    return object;
  }
  const merged = _mergeCustomAssistants(_customAssistantsRead().filter(_assistantProductBacked), [assistant]);
  _customAssistantsWrite(merged);
  _registerCustomAssistant(assistant);
  renderAssistantList();
  document.querySelectorAll('.ai-object-item[data-ai-object]').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.aiObject === _assistantKey());
  });
  syncAssistantListMeta();
  return AI_OBJECTS[assistant.kind] || assistant;
}

function _setProductUiStatusLocal(target, status, options = {}) {
  const nextStatus = String(status || '').trim() || 'empty';
  const productId = String(target && (target.productId || target.product_id) || '').trim();
  const kind = target && target.kind ? target.kind : _assistantKindForProductId(productId);
  const failureType = nextStatus === 'failed' ? String(options.failureType || options.uiErrorType || '').trim() : '';
  const failureMessage = nextStatus === 'failed' ? String(options.failureMessage || options.uiErrorMessage || '').trim() : '';
  if (target) target.uiStatus = nextStatus;
  if (target) {
    target.uiErrorType = failureType;
    target.uiErrorMessage = failureMessage;
  }
  if (kind && AI_OBJECTS[kind]) {
    AI_OBJECTS[kind].uiStatus = nextStatus;
    AI_OBJECTS[kind].uiErrorType = failureType;
    AI_OBJECTS[kind].uiErrorMessage = failureMessage;
  }
  if (productId) {
    const nextItems = _customAssistantsRead().map(item => {
      if (!item || String(item.productId || item.product_id || '') !== productId) return item;
      return {...item, uiStatus: nextStatus, ui_status: nextStatus, uiErrorType: failureType, ui_error_type: failureType, uiErrorMessage: failureMessage, ui_error_message: failureMessage};
    });
    _customAssistantsWrite(nextItems);
  }
  if (_activeProductPreview && _activeProductPreview.product_id === productId) {
    _activeProductPreview.ui_status = nextStatus;
    _activeProductPreview.ui_error_type = failureType;
    _activeProductPreview.ui_error_message = failureMessage;
    _syncProductPreviewCopy();
  }
  syncAssistantListMeta();
  if (kind && kind === _assistantKey() && AI_OBJECTS[kind]) {
    _syncAssistantHome(AI_OBJECTS[kind]);
  }
  return nextStatus;
}

async function _setProductUiStatus(target, status, options = {}) {
  const productId = String(target && (target.productId || target.product_id) || '').trim();
  const nextStatus = _setProductUiStatusLocal(target, status, options);
  if (!productId || !(options && options.persist)) return nextStatus;
  try {
    const body = { product_id: productId, ui_status: nextStatus };
    if (nextStatus === 'failed') {
      body.ui_error_type = String(options.failureType || options.uiErrorType || '').trim();
      body.ui_error_message = String(options.failureMessage || options.uiErrorMessage || '').trim();
    }
    const data = await api('/api/products/update', {
      method: 'POST',
      body: JSON.stringify(body)
    });
    if (data && data.product) _applyBackendProductToLocal(data.product);
  } catch (err) {
    console.debug('Failed to persist product ui status', err);
  }
  return nextStatus;
}

async function hydrateProductsFromBackend() {
  try {
    const data = await api('/api/products');
    const products = data && Array.isArray(data.products) ? data.products : [];
    const incoming = products.map(_productToCustomAssistant).filter(Boolean);
    const builtinIncoming = incoming.filter(item => _isBuiltinAssistantKind(item.kind));
    const customIncoming = incoming.filter(item => !_isBuiltinAssistantKind(item.kind));
    const existing = _customAssistantsRead();
    const nextIncoming = customIncoming;
    const backendKeys = new Set(nextIncoming.map(_customAssistantMergeKey).filter(Boolean));
    for (const assistant of existing) {
      if (!backendKeys.has(_customAssistantMergeKey(assistant))) {
        _deleteCustomAssistantKind(assistant.kind);
      }
    }
    for (const assistant of builtinIncoming) _applyBackendProductToBuiltin(products.find(product => product && (product.kind || '') === assistant.kind) || null, assistant);
    const merged = _mergeCustomAssistants(_customAssistantsRead().filter(_assistantProductBacked), nextIncoming);
    _customAssistantsWrite(merged);
    for (const assistant of merged) _registerCustomAssistant(assistant);
    renderAssistantList();
    const sessionProductKind = typeof syncAssistantSelectionToSessionProduct === 'function'
      ? syncAssistantSelectionToSessionProduct()
      : '';
    if (!sessionProductKind) {
      const current = _assistantKey();
      if (AI_OBJECTS[current]) selectAiObject(current);
      else selectAiObject('general');
    }
    return merged;
  } catch (err) {
    console.debug('hydrateProductsFromBackend failed', err);
    return [];
  }
}

function _currentBackendProductObject() {
  const kind = _assistantKey();
  const object = _assistantObject(kind);
  if (object && object.productId) return object;
  const activeProductId = _activeProductPreview && _activeProductPreview.product_preview ? String(_activeProductPreview.product_id || '') : '';
  const activeKind = activeProductId ? _assistantKindForProductId(activeProductId) : '';
  return activeKind ? _assistantObject(activeKind) : null;
}

function _capabilityOptionIds(options) {
  return new Set((Array.isArray(options) ? options : []).map(item => item && item.id).filter(Boolean));
}

function _unknownCapabilityItems(selected, options) {
  const known = _capabilityOptionIds(options);
  return _assistantUniqueCapabilityList(selected).filter(item => !known.has(item));
}

function _splitCapabilityInput(value) {
  return _assistantUniqueCapabilityList(String(value || '').split(/[,，\n]/g));
}

function _setProductCapabilitiesStatus(text, tone = '') {
  const el = $('productCapabilitiesStatus');
  if (!el) return;
  el.textContent = text || '';
  el.dataset.tone = tone || '';
}

function _renderProductCapabilityOptions(containerId, options, selectedItems, kind) {
  const container = $(containerId);
  if (!container) return;
  const selected = new Set(_assistantUniqueCapabilityList(selectedItems));
  container.innerHTML = '';
  for (const option of options) {
    if (!option || !option.id) continue;
    const label = document.createElement('label');
    label.className = 'product-capability-option';
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.value = option.id;
    input.dataset.productCapabilityKind = kind;
    input.checked = selected.has(option.id);
    const copy = document.createElement('span');
    const title = document.createElement('strong');
    title.textContent = option.label || option.id;
    const desc = document.createElement('span');
    desc.textContent = option.desc || option.id;
    copy.appendChild(title);
    copy.appendChild(desc);
    label.appendChild(input);
    label.appendChild(copy);
    container.appendChild(label);
  }
}

function openCurrentProductCapabilities() {
  const object = _currentBackendProductObject();
  if (!object || !object.productId) {
    if (typeof showToast === 'function') showToast('This AI cannot be configured yet.');
    return;
  }
  _setActiveProductPreviewMenuOpen(false);
  const skills = _assistantUniqueCapabilityList(object.skills || []);
  const tools = _assistantNormalizeToolsets(object.tools || []);
  const title = $('productCapabilitiesTitle');
  const desc = $('productCapabilitiesDesc');
  const extraSkills = $('productCapabilitiesExtraSkills');
  const extraTools = $('productCapabilitiesExtraTools');
  if (title) title.textContent = object.title || 'AI product';
  if (desc) desc.textContent = 'Set the skills and tools this AI should prefer across future tasks.';
  _renderProductCapabilityOptions('productCapabilitiesSkills', NEXT_AI_PRODUCT_SKILL_OPTIONS, skills, 'skills');
  _renderProductCapabilityOptions('productCapabilitiesTools', NEXT_AI_PRODUCT_TOOL_OPTIONS, tools, 'tools');
  if (extraSkills) extraSkills.value = _unknownCapabilityItems(skills, NEXT_AI_PRODUCT_SKILL_OPTIONS).join(', ');
  if (extraTools) extraTools.value = _unknownCapabilityItems(tools, NEXT_AI_PRODUCT_TOOL_OPTIONS).join(', ');
  _setProductCapabilitiesStatus('Saved settings apply to future tasks for this AI.');
  const overlay = $('productCapabilitiesOverlay');
  if (overlay) {
    overlay.hidden = false;
    overlay.setAttribute('aria-hidden', 'false');
  }
}

function closeCurrentProductCapabilities() {
  const overlay = $('productCapabilitiesOverlay');
  if (!overlay) return;
  overlay.hidden = true;
  overlay.setAttribute('aria-hidden', 'true');
}

function _collectProductCapabilitySelection(kind, extraInputId) {
  const checked = Array.from(document.querySelectorAll(`input[data-product-capability-kind="${kind}"]:checked`))
    .map(input => input && input.value)
    .filter(Boolean);
  return _assistantUniqueCapabilityList([...checked, ..._splitCapabilityInput($(extraInputId) && $(extraInputId).value)]);
}

async function saveCurrentProductCapabilities() {
  const object = _currentBackendProductObject();
  if (!object || !object.productId) {
    _setProductCapabilitiesStatus('This AI cannot be configured yet.', 'error');
    return;
  }
  const saveBtn = $('productCapabilitiesSave');
  const skills = _collectProductCapabilitySelection('skills', 'productCapabilitiesExtraSkills');
  const tools = _assistantNormalizeToolsets(_collectProductCapabilitySelection('tools', 'productCapabilitiesExtraTools'));
  if (saveBtn) saveBtn.disabled = true;
  _setProductCapabilitiesStatus('Saving skills and tools...');
  try {
    const data = await api('/api/products/update', {
      method: 'POST',
      body: JSON.stringify({
        product_id: object.productId,
        skills,
        tools
      })
    });
    if (data && data.product) {
      _applyBackendProductToLocal(data.product);
      const nextKind = _assistantKindForProductId(data.product.id);
      const nextObject = nextKind ? _assistantObject(nextKind) : null;
      if (nextObject) {
        nextObject.skills = Array.isArray(data.product.skills) ? data.product.skills : [];
        nextObject.tools = Array.isArray(data.product.tools) ? data.product.tools : [];
      }
    } else {
      object.skills = skills;
      object.tools = tools;
    }
    _setProductCapabilitiesStatus('Saved. Future tasks will use these skills and tools.', 'success');
    if (typeof showToast === 'function') showToast('Skills and tools saved');
    setTimeout(closeCurrentProductCapabilities, 360);
  } catch (err) {
    _setProductCapabilitiesStatus(`Save failed: ${err && err.message || err}`, 'error');
  } finally {
    if (saveBtn) saveBtn.disabled = false;
  }
}

window.openCurrentProductCapabilities = openCurrentProductCapabilities;
window.closeCurrentProductCapabilities = closeCurrentProductCapabilities;
window.saveCurrentProductCapabilities = saveCurrentProductCapabilities;
window.currentAssistantProductToolsets = function currentAssistantProductToolsets(object = _currentBackendProductObject()) {
  if (!object || !object.productId) return [];
  return _assistantNormalizeToolsets(object.tools || []);
};
window.currentAssistantProductSessionDefaults = function currentAssistantProductSessionDefaults(object = _currentBackendProductObject()) {
  if (!object || !object.productId) return {};
  return {
    productId: object.productId,
    workspace: object.workspacePath || '',
    enabledToolsets: _assistantNormalizeToolsets(object.tools || [])
  };
};
