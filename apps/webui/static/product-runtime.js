let _productPreviewPollTimer = null;
let _productPreviewPollProductId = '';

function currentAssistantWorkspacePath(kind = _assistantKey()) {
  const object = _assistantObject(kind);
  return object && object.workspacePath ? String(object.workspacePath) : '';
}

function currentAssistantPreviewUrl(kind = _assistantKey()) {
  const object = _assistantObject(kind);
  if (typeof _assistantUsesProductCanvas === 'function') {
    if (!_assistantUsesProductCanvas(object)) return '';
  } else if (object && String(object.uiMode || object.ui_mode || '') === 'chat_only') {
    return '';
  }
  return object && object.previewUrl ? String(object.previewUrl) : '';
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
  if (typeof _assistantUsesProductCanvas === 'function') {
    if (!_assistantUsesProductCanvas(object)) return false;
  } else if (object && String(object.uiMode || object.ui_mode || '') === 'chat_only') {
    return false;
  }
  return !!(object && object.productId && _productUiNeedsInitialGeneration(object));
}

function _assistantProductInitTaskTitle(object = _assistantObject()) {
  const title = object && object.title ? String(object.title).trim() : '这个 AI 产品';
  return `生成${title}产品画布`.slice(0, 64);
}

function _assistantProductInitUserMessage(object = _assistantObject()) {
  const title = object && object.title ? String(object.title).trim() : '这个 AI 产品';
  return `开始生成「${title}」的第一版产品画布，先做一个简单可用的版本。`;
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
  // 用/调开关显式决定 scope；画布只是展示方式，不决定产品能不能被调整。
  const adjustModeOpen = typeof document !== 'undefined' &&
    document.body &&
    document.body.dataset.nextAiProductAdjust === 'open';
  const scope = pendingScope || (
    _shouldInitializeProductUiForMessage(object)
      ? 'product_init'
      : adjustModeOpen
        ? 'product_builder'
        : 'product_usage'
  );
  const context = {
    product_id: object.productId,
    product_title: object.title || 'AI 产品',
    product_scope: scope,
    // scope 由可见的用/调开关(或首次生成/bridge)决定,告诉后端别再用正则二次猜。
    product_scope_explicit: true,
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

const PRODUCT_CANVAS_BRIDGE_PENDING = new Map();

function _activeProductFrameWindow() {
  const frame = $('activeProductFrame');
  return frame && frame.contentWindow ? frame.contentWindow : null;
}

function _postProductCanvasBridgeMessage(payload = {}) {
  const target = _activeProductFrameWindow();
  if (!target) return false;
  target.postMessage({source:'nextai-host', ...payload}, '*');
  return true;
}

function _productCanvasStateContext(payload = {}) {
  const object = _assistantObject();
  const productId = String(
    payload.productId ||
    payload.product_id ||
    (_activeProductPreview && _activeProductPreview.product_id) ||
    (object && (object.productId || object.product_id)) ||
    ''
  ).trim();
  const sessionId = String(
    payload.sessionId ||
    payload.session_id ||
    (typeof S !== 'undefined' && S.session && S.session.session_id) ||
    ''
  ).trim();
  const requestedScope = String(payload.scope || 'session').trim();
  const scope = requestedScope === 'product'
    ? 'product'
    : `session:${sessionId || 'draft'}`;
  return {productId, sessionId, scope};
}

function _productCanvasStateStorageKey(productId, scope, key) {
  return [
    'nextai',
    'product-state',
    encodeURIComponent(String(productId || 'unknown')),
    encodeURIComponent(String(scope || 'session:draft')),
    encodeURIComponent(String(key || ''))
  ].join(':');
}

function _productCanvasStateRespond(requestId, payload = {}) {
  if (!requestId) return false;
  return _postProductCanvasBridgeMessage({
    type:'nextai:host:state',
    requestId,
    ...payload
  });
}

function _productCanvasStateError(requestId, error) {
  if (!requestId) return false;
  return _postProductCanvasBridgeMessage({
    type:'nextai:host:error',
    requestId,
    error:String(error || '产品状态读写失败')
  });
}

function _handleProductCanvasStateMessage(payload = {}, event = null) {
  const frameWindow = _activeProductFrameWindow();
  if (!frameWindow || (event && event.source !== frameWindow)) return false;
  const requestId = String(payload.requestId || payload.id || '').trim();
  const action = String(payload.action || 'get').trim();
  const key = String(payload.key || '').trim();
  const {productId, sessionId, scope} = _productCanvasStateContext(payload);
  if (!productId) {
    _productCanvasStateError(requestId, '当前产品上下文不可用');
    return true;
  }
  if (!key && action !== 'clear') {
    _productCanvasStateError(requestId, '产品状态 key 不能为空');
    return true;
  }
  try {
    if (action === 'clear') {
      const prefix = _productCanvasStateStorageKey(productId, scope, '').replace(/:$/, ':');
      const removeKeys = [];
      for (let i = 0; i < localStorage.length; i += 1) {
        const storageKey = localStorage.key(i);
        if (storageKey && storageKey.startsWith(prefix)) removeKeys.push(storageKey);
      }
      removeKeys.forEach(storageKey => localStorage.removeItem(storageKey));
      _productCanvasStateRespond(requestId, {action, productId, sessionId, scope});
      return true;
    }
    const storageKey = _productCanvasStateStorageKey(productId, scope, key);
    if (action === 'get') {
      const raw = localStorage.getItem(storageKey);
      const value = raw == null ? payload.fallback : JSON.parse(raw);
      _productCanvasStateRespond(requestId, {action, key, value, exists:raw != null, productId, sessionId, scope});
      return true;
    }
    if (action === 'set') {
      localStorage.setItem(storageKey, JSON.stringify(payload.value));
      _productCanvasStateRespond(requestId, {action, key, value:payload.value, productId, sessionId, scope});
      return true;
    }
    if (action === 'remove') {
      localStorage.removeItem(storageKey);
      _productCanvasStateRespond(requestId, {action, key, productId, sessionId, scope});
      return true;
    }
    _productCanvasStateError(requestId, `未知产品状态操作：${action}`);
    return true;
  } catch (err) {
    _productCanvasStateError(requestId, err && err.message || err);
    return true;
  }
}

function _resolveProductCanvasBridgePending(sessionId = '') {
  const sid = String(sessionId || '').trim();
  if (sid && PRODUCT_CANVAS_BRIDGE_PENDING.has(sid)) {
    return {sid, pending: PRODUCT_CANVAS_BRIDGE_PENDING.get(sid)};
  }
  if (PRODUCT_CANVAS_BRIDGE_PENDING.size === 1) {
    const [fallbackSid, pending] = PRODUCT_CANVAS_BRIDGE_PENDING.entries().next().value;
    return {sid:fallbackSid, pending};
  }
  return null;
}

function _clearProductCanvasBridgePending(sid) {
  const pending = PRODUCT_CANVAS_BRIDGE_PENDING.get(sid);
  if (pending && pending.timeoutId) {
    clearTimeout(pending.timeoutId);
  }
  PRODUCT_CANVAS_BRIDGE_PENDING.delete(sid);
}

function _productCanvasBridgeInstruction(payload = {}, object = _assistantObject()) {
  const context = payload && typeof payload.context === 'object' ? payload.context : {};
  const character = context && typeof context.character === 'object' ? context.character : {};
  const history = Array.isArray(context.history) ? context.history.slice(-12) : [];
  const lines = [
    '[[NEXT_AI_HIDDEN_CONTEXT]]',
    'This user message came from an AI product canvas embedded in Next AI.',
    `AI product: ${object && object.title || 'current product'}`,
    `Product layout: ${object && (object.productLayout || object.product_layout) || 'unknown'}`,
    payload.action && `Product action: ${payload.action}`,
    context.mode && `Canvas mode: ${context.mode}`,
    character.name && `Active character: ${character.name}`,
    character.desc && `Character description: ${character.desc}`,
    character.system && `Character instruction: ${character.system}`,
    history.length ? 'Recent product-local history:' : '',
    ...history.map(item => {
      const role = String(item && item.role || 'user');
      const content = String(item && item.content || '').replace(/\s+/g, ' ').trim();
      return content ? `- ${role}: ${content.slice(0, 500)}` : '';
    }).filter(Boolean),
    'If this is character chat, reply as the active character. Return only the character-facing message unless the user clearly asks to change the product interface or workflow.',
    '[[/NEXT_AI_HIDDEN_CONTEXT]]'
  ].filter(Boolean);
  return lines.join('\n');
}

async function _sendProductCanvasAgentMessage(payload = {}, event = null) {
  const frameWindow = _activeProductFrameWindow();
  if (!frameWindow || (event && event.source !== frameWindow)) return false;
  const text = String(payload.text || payload.message || '').trim();
  const requestId = String(payload.requestId || payload.id || `canvas-${Date.now().toString(36)}`).trim();
  if (!text) {
    _postProductCanvasBridgeMessage({type:'nextai:host:error', requestId, error:'消息不能为空'});
    return true;
  }
  if (typeof S !== 'undefined' && (S.busy || S.activeStreamId || (S.session && S.session.active_stream_id))) {
    _postProductCanvasBridgeMessage({type:'nextai:host:error', requestId, error:'Agent 正在处理上一条消息，稍后再发。'});
    return true;
  }
  const input = $('msg');
  if (!input || typeof send !== 'function') {
    _postProductCanvasBridgeMessage({type:'nextai:host:error', requestId, error:'宿主聊天运行时不可用'});
    return true;
  }
  try {
    if ((!S || !S.session) && typeof newSession === 'function') {
      await newSession();
      if (typeof renderSessionList === 'function') await renderSessionList();
    }
    const sid = S && S.session && S.session.session_id ? S.session.session_id : '';
    if (!sid) throw new Error('无法创建当前任务');
    const timeoutId = setTimeout(() => {
      PRODUCT_CANVAS_BRIDGE_PENDING.delete(sid);
    }, 125000);
    PRODUCT_CANVAS_BRIDGE_PENDING.set(sid, {
      requestId,
      sentAt: Date.now(),
      timeoutId,
      productId: payload.productId || (_assistantObject() && _assistantObject().productId) || ''
    });
    const requestedScope = String(payload.productScope || payload.scope || 'product_usage').trim();
    window._nextAiPendingProductScope = ['product_usage', 'product_builder', 'product_init'].includes(requestedScope)
      ? requestedScope
      : 'product_usage';
    window._nextAiPendingProductIntent = text;
    window._nextAiPendingHiddenAgentInstruction = _productCanvasBridgeInstruction(payload);
    input.value = text;
    if (typeof autoResize === 'function') autoResize();
    _postProductCanvasBridgeMessage({type:'nextai:host:ack', requestId, sessionId:sid});
    await send();
    return true;
  } catch (err) {
    const sid = S && S.session && S.session.session_id ? S.session.session_id : '';
    if (sid) _clearProductCanvasBridgePending(sid);
    _postProductCanvasBridgeMessage({
      type:'nextai:host:error',
      requestId,
      error:String(err && err.message || err || '发送失败')
    });
    return true;
  }
}

function notifyProductCanvasAgentReply(payload = {}) {
  const resolved = _resolveProductCanvasBridgePending(payload.sessionId || payload.session_id || '');
  if (!resolved) return false;
  const {sid, pending} = resolved;
  _clearProductCanvasBridgePending(sid);
  return _postProductCanvasBridgeMessage({
    type:'nextai:host:reply',
    requestId:pending.requestId,
    sessionId:sid,
    content:String(payload.content || '')
  });
}

function notifyProductCanvasAgentError(payload = {}) {
  const resolved = _resolveProductCanvasBridgePending(payload.sessionId || payload.session_id || '');
  if (!resolved) return false;
  const {sid, pending} = resolved;
  _clearProductCanvasBridgePending(sid);
  return _postProductCanvasBridgeMessage({
    type:'nextai:host:error',
    requestId:pending.requestId,
    sessionId:sid,
    error:String(payload.error || 'Agent 返回失败')
  });
}

window.addEventListener('message', event => {
  const data = event && event.data;
  if (!data || typeof data !== 'object') return;
  if (data.source !== 'nextai-product-canvas') return;
  if (data.type === 'nextai:product:state') {
    _handleProductCanvasStateMessage(data, event);
    return;
  }
  if (data.type === 'nextai:product:send') {
    void _sendProductCanvasAgentMessage(data, event);
  }
});

window.currentAssistantWorkspacePath = currentAssistantWorkspacePath;
window.currentAssistantPreviewUrl = currentAssistantPreviewUrl;
window.currentAssistantProductContextForMessage = currentAssistantProductContextForMessage;
window.withCurrentProductContext = withCurrentProductContext;
window.notifyProductCanvasAgentReply = notifyProductCanvasAgentReply;
window.notifyProductCanvasAgentError = notifyProductCanvasAgentError;

async function _startProductInitializationTask(assistant, sourcePrompt) {
  if (!assistant || !assistant.productId || !assistant.workspacePath) return false;
  if (typeof _assistantUsesProductCanvas === 'function' && !_assistantUsesProductCanvas(assistant)) return false;
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
    if (typeof showToast === 'function') showToast(`首次生成产品画布失败：${err && err.message || err}`, 3600, 'error');
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

function _hideProductPreviewIfActive(options = {}) {
  if (!_activeProductPreview || !_activeProductPreview.product_preview) return false;
  const shouldSync = !(options && options.sync === false);
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
  if (shouldSync) syncAssistantTaskUi();
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
    if (kicker) kicker.textContent = '产品画布';
    if (title) title.textContent = '正在生成第一版产品画布';
    if (desc) desc.textContent = 'Agent 正在写这个产品的 index.html、style.css 和 app.js；完成后右侧会自动刷新。';
    if (action) action.hidden = true;
    return false;
  }
  if (uiStatus === 'failed') {
    state.classList.add('is-failed');
    if (kicker) kicker.textContent = '产品画布';
    if (title) title.textContent = '产品画布生成失败';
    if (desc) desc.textContent = failureMessage
      ? `${failureMessage} 可以直接重试，或继续说明你想让这个产品画布怎么工作。`
      : '可以继续对话让它重试，或直接说明你想让这个产品画布长什么样。';
    if (action) {
      action.hidden = false;
      action.textContent = '重新生成产品画布';
    }
    return false;
  }
  state.classList.add('is-empty');
  if (kicker) kicker.textContent = '产品画布';
  if (title) title.textContent = '这个 AI 产品还没有产品画布';
  if (desc) desc.textContent = '继续对话，让它生成第一版产品画布。对话仍然是主入口。';
  if (action) {
    action.hidden = false;
    action.textContent = '生成产品画布';
  }
  return false;
}

async function requestCurrentProductUiGeneration() {
  const object = _assistantObject();
  if (!object || !object.productId) return false;
  if (typeof S !== 'undefined' && (S.busy || S.activeStreamId)) {
    if (typeof showToast === 'function') showToast('当前任务还在运行，完成后再生成产品画布');
    return false;
  }
  const prompt = object.sourcePrompt
    ? `请重新生成「${object.title || '这个 AI 产品'}」的产品画布。原始需求：${object.sourcePrompt}`
    : `请为「${object.title || '这个 AI 产品'}」生成第一版产品画布。产品画布要服务它的真实任务，不要写成介绍页。`;
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
    if (typeof showToast === 'function') showToast(`生成产品画布失败：${err && err.message || err}`, 3600, 'error');
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
  if (!productId) {
    _hideProductPreviewIfActive();
    return false;
  }
  const surface = $('activeProductSurface');
  const frame = $('activeProductFrame');
  const body = $('productChatBody');
  if (!surface || !frame || !body) return false;
  let nextPreviewUrl = object && object.previewUrl ? String(object.previewUrl) : '';
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
  const usesProductCanvas = typeof _assistantUsesProductCanvas === 'function'
    ? _assistantUsesProductCanvas(object)
    : !(object && String(object.uiMode || object.ui_mode || '') === 'chat_only');
  if (!usesProductCanvas || !nextPreviewUrl) {
    _hideProductPreviewIfActive();
    return false;
  }
  _activeProductPreview = {
    id: `product:${productId}`,
    name: typeof _assistantCanvasLabel === 'function' ? _assistantCanvasLabel(object) : (object.title || '产品画布'),
    preview_url: nextPreviewUrl,
    product_preview: true,
    product_id: productId,
    product_layout: typeof _assistantProductLayout === 'function' ? _assistantProductLayout(object) : '',
    canvas_label: typeof _assistantCanvasLabel === 'function' ? _assistantCanvasLabel(object) : '',
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
  frame.onload = () => {
    _postProductCanvasBridgeMessage({
      type:'nextai:host:ready',
      productId,
      sessionId:typeof S !== 'undefined' && S.session && S.session.session_id || '',
      layout:_activeProductPreview && _activeProductPreview.product_layout || '',
      canvasLabel:_activeProductPreview && _activeProductPreview.canvas_label || ''
    });
  };
  if (previewReady) frame.src = _withPreviewTimestamp(nextPreviewUrl);
  const uiStatus = String(statusData && (statusData.ui_status || statusData.product && statusData.product.ui_status) || object.uiStatus || '');
  if (uiStatus === 'generating') _scheduleProductPreviewPolling(productId);
  else _stopProductPreviewPolling(productId);
  syncAssistantTaskUi();
  if (options && options.focus) _focusActiveProductPreviewSurface();
  return true;
}

window.refreshCurrentProductPreview = refreshCurrentProductPreview;
