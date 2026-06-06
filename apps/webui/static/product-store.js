const NEXT_AI_PRODUCT_SKILL_OPTIONS = [
  { id: 'presentations', label: '演示文稿', desc: '生成和修改 PPT' },
  { id: 'office', label: '文档处理', desc: '处理 PPTX、文档和导出' },
  { id: 'imagegen', label: '图片生成', desc: '生成或编辑图片' },
  { id: 'browser', label: '网页研究', desc: '浏览网页和收集资料' },
  { id: 'spreadsheets', label: '表格数据', desc: '分析表格和数据' }
];
const NEXT_AI_PRODUCT_TOOL_OPTIONS = [
  { id: 'skills', label: '技能', desc: '使用已安装的专业能力' },
  { id: 'file', label: '文件', desc: '读取和修改产品文件' },
  { id: 'terminal', label: '命令', desc: '执行本地命令' },
  { id: 'code_execution', label: '代码', desc: '运行代码和脚本' },
  { id: 'browser', label: '浏览', desc: '打开网页并收集资料' },
  { id: 'web', label: '搜索', desc: '搜索公开网页' },
  { id: 'image_gen', label: '生图', desc: '生成或编辑图片' }
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

function _assistantDefaultCapabilities(productType = '', seedText = '') {
  const seed = `${productType || ''} ${seedText || ''}`;
  const lower = seed.toLowerCase();
  const skills = [];
  const tools = [];
  const add = (nextSkills, nextTools) => {
    skills.push(...nextSkills);
    tools.push(...nextTools);
  };
  if (productType === 'ppt' || /ppt|powerpoint|slide|slides|deck|演示|幻灯|路演|汇报/i.test(seed)) {
    add(['presentations', 'office'], ['skills', 'file', 'terminal', 'code_execution']);
  }
  if (productType === 'image' || /图片|图像|生图|绘图|文生图|画图|生成图|海报|封面|插画|头像|视觉|image|photo|poster|visual/i.test(seed)) {
    add(['imagegen'], ['skills', 'file', 'image_gen']);
  }
  if (productType === 'research' || /研究|调研|资料|报告|竞品|行业|research|browser|web/i.test(lower)) {
    add(['browser'], ['skills', 'browser', 'web', 'file']);
  }
  if (productType === 'data' || /数据|运营|指标|表格|看板|报表|data|sheet|spreadsheet|table/i.test(lower)) {
    add(['spreadsheets'], ['skills', 'file', 'terminal', 'code_execution']);
  }
  return {
    skills: _assistantUniqueCapabilityList(skills),
    tools: _assistantNormalizeToolsets(tools)
  };
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

function _assistantCanvasLabel(object) {
  const explicit = String(object && (object.canvasLabel || object.canvas_label) || '').trim();
  if (explicit) return explicit;
  const productType = String(object && (object.productType || object.product_type) || '').trim();
  if (productType === 'ppt') return 'PPT 工作区';
  if (productType === 'image') return '图片画布';
  if (productType === 'research') return '研究工作区';
  if (productType === 'data') return '数据工作区';
  return '产品画布';
}

function _assistantDateToMs(value) {
  const parsed = Date.parse(String(value || ''));
  return Number.isFinite(parsed) ? parsed : Date.now();
}

function _productToCustomAssistant(product) {
  if (!product || !product.id) return null;
  const title = product.title || 'AI 产品';
  const sourcePrompt = product.source_prompt || product.sourcePrompt || '';
  const productType = product.product_type || product.productType || 'custom';
  const starterKit = _assistantStarterKit(title, sourcePrompt || product.desc || '');
  return {
    kind: product.kind || `custom-${product.id}`,
    title,
    avatar: product.avatar || '',
    desc: product.desc || '按照你描述的职责处理任务，需要时生成自己的产品画布。',
    placeholder: product.placeholder || starterKit.placeholder,
    suggestions: Array.isArray(product.suggestions) && product.suggestions.length ? product.suggestions : starterKit.suggestions,
    sourcePrompt,
    titleSource: 'backend-product',
    createdAt: product.created_at ? _assistantDateToMs(product.created_at) : Date.now(),
    productType,
    uiMode: product.ui_mode || product.uiMode || 'workspace',
    productLayout: product.product_layout || product.productLayout || product.layout || '',
    canvasLabel: product.canvas_label || product.canvasLabel || '',
    productId: product.id,
    workspacePath: product.workspace_path || '',
    previewUrl: product.preview_url || '',
    uiStatus: product.ui_status || 'empty',
    uiErrorType: product.ui_error_type || '',
    uiErrorMessage: product.ui_error_message || '',
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
    const current = _assistantKey();
    if (AI_OBJECTS[current]) selectAiObject(current);
    else selectAiObject('general');
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
    if (typeof showToast === 'function') showToast('当前不是可配置的 AI 产品');
    return;
  }
  _setActiveProductPreviewMenuOpen(false);
  const skills = _assistantUniqueCapabilityList(object.skills || []);
  const tools = _assistantNormalizeToolsets(object.tools || []);
  const title = $('productCapabilitiesTitle');
  const desc = $('productCapabilitiesDesc');
  const extraSkills = $('productCapabilitiesExtraSkills');
  const extraTools = $('productCapabilitiesExtraTools');
  if (title) title.textContent = object.title || 'AI 产品';
  if (desc) desc.textContent = '给当前产品补充长期偏好和可用工具。保存后，之后的任务会按这些能力处理。';
  _renderProductCapabilityOptions('productCapabilitiesSkills', NEXT_AI_PRODUCT_SKILL_OPTIONS, skills, 'skills');
  _renderProductCapabilityOptions('productCapabilitiesTools', NEXT_AI_PRODUCT_TOOL_OPTIONS, tools, 'tools');
  if (extraSkills) extraSkills.value = _unknownCapabilityItems(skills, NEXT_AI_PRODUCT_SKILL_OPTIONS).join(', ');
  if (extraTools) extraTools.value = _unknownCapabilityItems(tools, NEXT_AI_PRODUCT_TOOL_OPTIONS).join(', ');
  _setProductCapabilitiesStatus('保存后，当前产品会在后续任务里使用这些设置。');
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
    _setProductCapabilitiesStatus('当前不是可配置的 AI 产品。', 'error');
    return;
  }
  const saveBtn = $('productCapabilitiesSave');
  const skills = _collectProductCapabilitySelection('skills', 'productCapabilitiesExtraSkills');
  const tools = _assistantNormalizeToolsets(_collectProductCapabilitySelection('tools', 'productCapabilitiesExtraTools'));
  if (saveBtn) saveBtn.disabled = true;
  _setProductCapabilitiesStatus('正在保存能力与工具...');
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
    _setProductCapabilitiesStatus('已保存。之后的任务会使用新的能力与工具。', 'success');
    if (typeof showToast === 'function') showToast('能力与工具已保存');
    setTimeout(closeCurrentProductCapabilities, 360);
  } catch (err) {
    _setProductCapabilitiesStatus(`保存失败：${err && err.message || err}`, 'error');
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
