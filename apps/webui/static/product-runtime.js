let _productPreviewPollTimer = null;
let _productPreviewPollProductId = '';
const PRODUCT_BUILDER_INTENT_RE = new RegExp([
  '界面', '页面', 'UI', '布局', '工作流', '表单',
  '右侧', '左侧', '上方', '下方', '顶部', '底部', '侧栏', '顶栏',
  '预览区', '工作台', '改自己', '产品自己', '长出来', '长出',
  '按钮', '字段', '默认项', '以后', '每次', '下次', '固定', '常驻',
  '流程', '交互', '面板', '模块', '导航', '入口', '参数区', '历史', '样式',
  '区域', '卡片', '工具栏', '输入框', '下拉', '筛选器', '上传区', '导出', '下载',
  '资料栏', '参考资料栏', '讲稿区', '大纲区', '缩略图', '模板选择', '风格选择', '页数选择',
  '头像', '名称', '名字', '简介', '职责', '人设', '身份', '提示词', 'prompt', '技能', '工具', '能力',
  '放上面', '放下面', '放到', '放在', '移到', '挪到',
  'workflow', 'layout', 'interface', 'form', 'panel', 'sidebar', 'toolbar', 'card',
  'default', 'always', 'next\\s*time'
].join('|'), 'i');
const PRODUCT_BUILDER_NEGATION_RE = new RegExp([
  '(不要|不用|不必|不需要|无需|别|先别|不要再|不用再).{0,16}(改|修改|调整|重写|更新|生成|设计|动|写|编辑).{0,16}(界面|页面|UI|布局|工作流|流程|表单|面板|模块|产品界面|产品UI)',
  '(不改|不动|不调整|不修改|不更新).{0,16}(界面|页面|UI|布局|工作流|流程|表单|面板|模块|产品界面|产品UI)'
].join('|'), 'i');

function currentAssistantWorkspacePath(kind = _assistantKey()) {
  const object = _assistantObject(kind);
  return object && object.workspacePath ? String(object.workspacePath) : '';
}

function currentAssistantPreviewUrl(kind = _assistantKey()) {
  const object = _assistantObject(kind);
  if (object && String(object.uiMode || object.ui_mode || '') === 'chat_only') return '';
  return object && object.previewUrl ? String(object.previewUrl) : '';
}

function _inferProductScopeFromText(text = '') {
  const seed = String(text || '');
  if (PRODUCT_BUILDER_NEGATION_RE.test(seed)) {
    return 'product_usage';
  }
  if (PRODUCT_BUILDER_INTENT_RE.test(seed)) {
    return 'product_builder';
  }
  return 'product_usage';
}

function _productUiNeedsInitialGeneration(object) {
  const status = String(object && (object.uiStatus || object.ui_status) || '').toLowerCase();
  return !status || status === 'empty' || status === 'failed';
}

function _productUiGenerationScopeForObject(object) {
  if (!object || !object.productId) return 'product_usage';
  const productId = String(object.productId || object.product_id || '');
  const activeGenerated = !!(
    _activeProductPreview &&
    String(_activeProductPreview.product_id || '') === productId &&
    _activeProductPreview.entry_generated
  );
  return !activeGenerated && _productUiNeedsInitialGeneration(object) ? 'product_init' : 'product_builder';
}

function _shouldInitializeProductUiForMessage(object) {
  if (object && String(object.uiMode || object.ui_mode || '') === 'chat_only') return false;
  return !!(object && object.productId && _productUiNeedsInitialGeneration(object));
}

function _assistantProductInitTaskTitle(object = _assistantObject()) {
  const title = object && object.title ? String(object.title).trim() : '这个 AI 产品';
  return `生成${title}界面`.slice(0, 64);
}

function _assistantProductInitUserMessage(object = _assistantObject()) {
  const title = object && object.title ? String(object.title).trim() : '这个 AI 产品';
  return `开始生成「${title}」的第一版产品界面，先做一个简单可用的版本。`;
}

function _currentSessionMatchesProduct(object) {
  if (!object || !object.productId || typeof S === 'undefined' || !S.session || !S.session.session_id) return false;
  const sessionProductId = String(S.session.product_id || S.session.productId || '').trim();
  const productId = String(object.productId || object.product_id || '').trim();
  if (!sessionProductId || sessionProductId !== productId) return false;
  const productWorkspace = String(object.workspacePath || object.workspace_path || '').trim();
  const sessionWorkspace = String(S.session.workspace || '').trim();
  return !productWorkspace || sessionWorkspace === productWorkspace;
}

function currentAssistantProductContextForMessage(text = '', options = {}) {
  const kind = _assistantKey();
  const object = _assistantObject(kind);
  if (!object || !object.productId || kind === 'create') return null;
  const pendingScope = typeof window !== 'undefined' ? String(window._nextAiPendingProductScope || '').trim() : '';
  const pendingIntent = typeof window !== 'undefined' ? String(window._nextAiPendingProductIntent || '').trim() : '';
  const consumePending = !options || options.consumePending !== false;
  if (consumePending && typeof window !== 'undefined') {
    window._nextAiPendingProductScope = '';
    window._nextAiPendingProductIntent = '';
  }
  const scope = pendingScope || (_shouldInitializeProductUiForMessage(object) ? 'product_init' : _inferProductScopeFromText(text));
  const context = {
    product_id: object.productId,
    product_title: object.title || 'AI 产品',
    product_scope: scope,
    product_intent: pendingIntent || String(text || '').trim()
  };
  if (scope === 'product_init') context.product_task_title = _assistantProductInitTaskTitle(object);
  return context;
}

function withCurrentProductContext(payload = {}, text = '', options = {}) {
  const base = payload && typeof payload === 'object' ? {...payload} : {};
  if (base.product_id || base.productId) return base;
  const sourceText = String(text || base.sendText || base.text || base.message || base.content || '').trim();
  const context = currentAssistantProductContextForMessage(sourceText, options);
  if (!context || !context.product_id) return base;
  return {...base, ...context};
}

window.currentAssistantWorkspacePath = currentAssistantWorkspacePath;
window.currentAssistantPreviewUrl = currentAssistantPreviewUrl;
window.currentAssistantProductContextForMessage = currentAssistantProductContextForMessage;
window.withCurrentProductContext = withCurrentProductContext;

async function _startProductInitializationTask(assistant, sourcePrompt) {
  if (!assistant || !assistant.productId || !assistant.workspacePath) return false;
  if (typeof newSession !== 'function' || typeof send !== 'function') {
    await _setProductUiStatus(assistant, 'failed', {persist: true});
    openAssistantHome(assistant.kind);
    await refreshCurrentProductPreview({silent:true, reason:'product-init-runtime-missing'});
    return false;
  }
  try {
    await _setProductUiStatus(assistant, 'generating', {persist: true});
    openAssistantHome(assistant.kind);
    await refreshCurrentProductPreview({silent:true, reason:'product-init-start'});
    const initTaskTitle = _assistantProductInitTaskTitle(assistant);
    await newSession(false, {
      workspace: assistant.workspacePath,
      productId: assistant.productId,
      productScope: 'product_init',
      productIntent: sourcePrompt,
      productTaskTitle: initTaskTitle
    });
    if (typeof S !== 'undefined' && S.session && S.session.session_id) {
      S.session.title = initTaskTitle;
      rememberAssistantTaskTitle(S.session.session_id, initTaskTitle);
      if (typeof applySessionTitleUpdate === 'function') {
        applySessionTitleUpdate(S.session.session_id, initTaskTitle, {force:true, rememberProvisional:true});
      }
      if (typeof upsertActiveSessionForLocalTurn === 'function') {
        upsertActiveSessionForLocalTurn({title:initTaskTitle, messageCount:S.messages && S.messages.length || 0, timestampMs:Date.now()});
      }
    }
    if (typeof renderSessionList === 'function') await renderSessionList();
    window._nextAiPendingProductScope = 'product_init';
    window._nextAiPendingProductIntent = String(sourcePrompt || '').trim();
    const input = $('msg');
    if (!input) {
      await _setProductUiStatus(assistant, 'failed', {persist: true});
      openAssistantHome(assistant.kind);
      await refreshCurrentProductPreview({silent:true, reason:'product-init-input-missing'});
      return false;
    }
    input.value = _assistantProductInitUserMessage(assistant);
    if (typeof autoResize === 'function') autoResize();
    await send();
    return true;
  } catch (err) {
    await _setProductUiStatus(assistant, 'failed', {persist: true});
    openAssistantHome(assistant.kind);
    await refreshCurrentProductPreview({silent:true, reason:'product-init-error'});
    if (typeof showToast === 'function') showToast(`首次生成产品界面失败：${err && err.message || err}`, 3600, 'error');
    return false;
  }
}

function _withPreviewTimestamp(url) {
  if (!url) return '';
  const join = url.includes('?') ? '&' : '?';
  return `${url}${join}t=${Date.now()}`;
}

function _stopProductPreviewPolling(productId = '') {
  if (productId && _productPreviewPollProductId && _productPreviewPollProductId !== productId) return;
  if (_productPreviewPollTimer) {
    clearTimeout(_productPreviewPollTimer);
    _productPreviewPollTimer = null;
  }
  if (!productId || _productPreviewPollProductId === productId) _productPreviewPollProductId = '';
}

function _scheduleProductPreviewPolling(productId) {
  const id = String(productId || '').trim();
  if (!id) return;
  if (_productPreviewPollTimer && _productPreviewPollProductId === id) return;
  _stopProductPreviewPolling();
  _productPreviewPollProductId = id;
  _productPreviewPollTimer = setTimeout(async () => {
    _productPreviewPollTimer = null;
    const current = _assistantObject();
    if (!current || String(current.productId || '') !== id) {
      _stopProductPreviewPolling(id);
      return;
    }
    await refreshCurrentProductPreview({silent:true, reason:'product-poll'});
  }, 2000);
}

function _hideProductPreviewIfActive() {
  if (!_activeProductPreview || !_activeProductPreview.product_preview) return false;
  _stopProductPreviewPolling(_activeProductPreview.product_id || '');
  const surface = $('activeProductSurface');
  const frame = $('activeProductFrame');
  const previewState = $('productPreviewState');
  const body = $('productChatBody');
  if (surface) surface.hidden = true;
  if (frame) {
    frame.hidden = false;
    frame.removeAttribute('src');
  }
  if (previewState) previewState.hidden = true;
  if (body) body.classList.remove('has-active-product');
  _activeProductPreview = null;
  _syncProductPreviewMode(null);
  syncAssistantTaskUi();
  return true;
}

function _syncProductPreviewState(statusData = {}, object = _assistantObject()) {
  const state = $('productPreviewState');
  const title = $('productPreviewStateTitle');
  const desc = $('productPreviewStateDesc');
  const kicker = $('productPreviewStateKicker');
  const action = $('productPreviewStateAction');
  const frame = $('activeProductFrame');
  if (!state || !frame) return true;
  const uiStatus = String(
    (statusData && statusData.ui_status) ||
    (statusData && statusData.product && statusData.product.ui_status) ||
    (object && object.uiStatus) ||
    (_activeProductPreview && _activeProductPreview.ui_status) ||
    'empty'
  );
  const entryGenerated = !!(
    statusData && statusData.entry_generated ||
    _activeProductPreview && _activeProductPreview.entry_generated
  );
  const failureMessage = String(
    (statusData && statusData.product && statusData.product.ui_error_message) ||
    (object && object.uiErrorMessage) ||
    (_activeProductPreview && _activeProductPreview.ui_error_message) ||
    ''
  ).trim();
  const ready = entryGenerated && uiStatus !== 'generating' && uiStatus !== 'failed';
  state.classList.remove('is-generating', 'is-failed', 'is-empty');
  if (ready) {
    state.hidden = true;
    frame.hidden = false;
    return true;
  }
  frame.hidden = true;
  frame.removeAttribute('src');
  state.hidden = false;
  if (uiStatus === 'generating') {
    state.classList.add('is-generating');
    if (kicker) kicker.textContent = '产品界面';
    if (title) title.textContent = '正在生成第一版产品界面';
    if (desc) desc.textContent = 'Agent 正在写这个产品的 index.html、style.css 和 app.js；完成后右侧会自动刷新。';
    if (action) action.hidden = true;
    return false;
  }
  if (uiStatus === 'failed') {
    state.classList.add('is-failed');
    if (kicker) kicker.textContent = '产品界面';
    if (title) title.textContent = '产品界面生成失败';
    if (desc) desc.textContent = failureMessage
      ? `${failureMessage} 可以直接重试，或继续说明你想让这个界面怎么工作。`
      : '可以继续对话让它重试，或直接说明你想让这个界面长什么样。';
    if (action) {
      action.hidden = false;
      action.textContent = '重新生成界面';
    }
    return false;
  }
  state.classList.add('is-empty');
  if (kicker) kicker.textContent = '产品界面';
  if (title) title.textContent = '这个 AI 产品还没有界面';
  if (desc) desc.textContent = '继续对话，让它生成第一版产品界面。对话仍然是主入口。';
  if (action) {
    action.hidden = false;
    action.textContent = '生成产品界面';
  }
  return false;
}

async function requestCurrentProductUiGeneration() {
  const object = _assistantObject();
  if (!object || !object.productId) return false;
  if (typeof S !== 'undefined' && (S.busy || S.activeStreamId)) {
    if (typeof showToast === 'function') showToast('当前任务还在运行，完成后再生成界面');
    return false;
  }
  const prompt = object.sourcePrompt
    ? `请重新生成「${object.title || '这个 AI 产品'}」的产品界面。原始需求：${object.sourcePrompt}`
    : `请为「${object.title || '这个 AI 产品'}」生成第一版产品界面。界面要服务它的真实任务，不要写成介绍页。`;
  try {
    const generationScope = _productUiGenerationScopeForObject(object);
    await _setProductUiStatus(object, 'generating', {persist: true});
    if (typeof refreshCurrentProductPreview === 'function') await refreshCurrentProductPreview({silent:true, reason:'manual-product-generation-start'});
    const hasProductSession = _currentSessionMatchesProduct(object);
    if (!hasProductSession && typeof newSession === 'function') {
      const initTaskTitle = _assistantProductInitTaskTitle(object);
      await newSession(false, {
        workspace: object.workspacePath || '',
        productId: object.productId,
        productScope: generationScope,
        productIntent: prompt,
        productTaskTitle: generationScope === 'product_init' ? initTaskTitle : ''
      });
      if (typeof S !== 'undefined' && S.session && S.session.session_id) {
        if (generationScope === 'product_init') {
          S.session.title = initTaskTitle;
          rememberAssistantTaskTitle(S.session.session_id, initTaskTitle);
          if (typeof applySessionTitleUpdate === 'function') {
            applySessionTitleUpdate(S.session.session_id, initTaskTitle, {force:true, rememberProvisional:true});
          }
        }
      }
      if (typeof renderSessionList === 'function') await renderSessionList();
    }
    window._nextAiPendingProductScope = generationScope;
    window._nextAiPendingProductIntent = prompt;
    const input = $('msg');
    if (input) {
      input.value = prompt;
      if (typeof autoResize === 'function') autoResize();
    }
    if (typeof send === 'function') await send();
    return true;
  } catch (err) {
    await _setProductUiStatus(object, 'failed', {persist: true});
    await refreshCurrentProductPreview({silent:true, reason:'manual-product-generation-error'});
    if (typeof showToast === 'function') showToast(`生成产品界面失败：${err && err.message || err}`, 3600, 'error');
    return false;
  }
}

window.requestCurrentProductUiGeneration = requestCurrentProductUiGeneration;

function currentProductPreviewRuntimeState() {
  if (!_activeProductPreview || !_activeProductPreview.product_preview) {
    return {active:false};
  }
  return {
    active:true,
    productId: _activeProductPreview.product_id || '',
    uiStatus: _activeProductPreview.ui_status || '',
    failureReason: _activeProductPreview.ui_error_message || '',
    entryGenerated: !!_activeProductPreview.entry_generated,
    canRollback: !!_activeProductPreview.can_rollback,
    previousVersion: _activeProductPreview.previous_version || '',
    versionCount: Number(_activeProductPreview.version_count || 0) || 0
  };
}

window.currentProductPreviewRuntimeState = currentProductPreviewRuntimeState;

async function refreshCurrentProductPreview(options = {}) {
  const object = _assistantObject();
  const productId = object && object.productId ? String(object.productId) : '';
  const previewUrl = object && object.previewUrl ? String(object.previewUrl) : '';
  if (!productId || !previewUrl) {
    _hideProductPreviewIfActive();
    return false;
  }
  const surface = $('activeProductSurface');
  const frame = $('activeProductFrame');
  const body = $('productChatBody');
  if (!surface || !frame || !body) return false;
  let nextPreviewUrl = previewUrl;
  let statusData = null;
  try {
    const status = await api(`/api/products/${encodeURIComponent(productId)}/status`);
    statusData = status;
    if (status && status.preview_url) nextPreviewUrl = status.preview_url;
    if (status && status.product) {
      const nextObject = _applyBackendProductToLocal(status.product);
      object.uiStatus = status.product.ui_status || object.uiStatus || '';
      object.uiErrorType = status.product.ui_error_type || '';
      object.uiErrorMessage = status.product.ui_error_message || '';
      object.previewUrl = status.product.preview_url || object.previewUrl || '';
      object.workspacePath = status.product.workspace_path || object.workspacePath || '';
      if (nextObject && object !== nextObject) {
        nextObject.uiStatus = object.uiStatus;
        nextObject.uiErrorType = object.uiErrorType;
        nextObject.uiErrorMessage = object.uiErrorMessage;
        nextObject.previewUrl = object.previewUrl;
        nextObject.workspacePath = object.workspacePath;
      }
    }
  } catch (_err) {}
  _activeProductPreview = {
    id: `product:${productId}`,
    name: object.title || 'AI 产品',
    preview_url: nextPreviewUrl,
    product_preview: true,
    product_id: productId,
    ui_status: object.uiStatus || '',
    ui_error_type: object.uiErrorType || '',
    ui_error_message: object.uiErrorMessage || '',
    entry_generated: !!(statusData && statusData.entry_generated),
    version_count: Array.isArray(statusData && statusData.product && statusData.product.versions) ? statusData.product.versions.length : 0,
    previous_version: Array.isArray(statusData && statusData.product && statusData.product.versions) && statusData.product.versions[0] ? statusData.product.versions[0].id || '' : '',
    can_rollback: !!(Array.isArray(statusData && statusData.product && statusData.product.versions) && statusData.product.versions.length)
  };
  _syncProductPreviewMode(_activeProductPreview);
  _syncProductPreviewCopy();
  surface.hidden = false;
  body.classList.add('has-active-product');
  const previewReady = _syncProductPreviewState(statusData || {}, object);
  if (previewReady) frame.src = _withPreviewTimestamp(nextPreviewUrl);
  const uiStatus = String(statusData && (statusData.ui_status || statusData.product && statusData.product.ui_status) || object.uiStatus || '');
  if (uiStatus === 'generating') _scheduleProductPreviewPolling(productId);
  else _stopProductPreviewPolling(productId);
  syncAssistantTaskUi();
  if (options && options.focus) _focusActiveProductPreviewSurface();
  return true;
}

window.refreshCurrentProductPreview = refreshCurrentProductPreview;
