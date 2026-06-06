(function () {
  const pending = new Map();
  let hostContext = {};

  function createMemoryStorage() {
    const values = new Map();
    const storage = {
      key(index) {
        const keys = Array.from(values.keys());
        const key = keys[Number(index)];
        return typeof key === 'string' ? key : null;
      },
      getItem(key) {
        const normalized = String(key);
        return values.has(normalized) ? values.get(normalized) : null;
      },
      setItem(key, value) {
        values.set(String(key), String(value));
      },
      removeItem(key) {
        values.delete(String(key));
      },
      clear() {
        values.clear();
      }
    };
    Object.defineProperty(storage, 'length', {
      get() {
        return values.size;
      }
    });
    return storage;
  }

  function installStorageFallback(name) {
    try {
      const storage = window[name];
      const probe = `__nextai_${name}_probe__`;
      storage.setItem(probe, '1');
      storage.removeItem(probe);
      return storage;
    } catch (_) {
      const fallback = createMemoryStorage();
      try {
        Object.defineProperty(window, name, {
          value: fallback,
          configurable: true
        });
      } catch (_) {
        // Some browser contexts may not let us shadow the property. In that
        // case callers can still use NextAI.storage.
      }
      return fallback;
    }
  }

  const safeLocalStorage = installStorageFallback('localStorage');
  const safeSessionStorage = installStorageFallback('sessionStorage');

  function requestId() {
    return `nextai-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  }

  function postToHost(payload) {
    window.parent.postMessage({
      source: 'nextai-product-canvas',
      ...payload
    }, '*');
  }

  function createPendingRequest(payload, timeoutMs) {
    const id = String(payload.requestId || requestId());
    const requestTimeoutMs = Number(timeoutMs || payload.timeoutMs || 120000);
    payload.requestId = id;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        if (!pending.has(id)) return;
        pending.delete(id);
        reject(new Error('Next AI bridge timed out'));
      }, requestTimeoutMs);
      pending.set(id, {resolve, reject, timer});
      postToHost(payload);
    });
  }

  function send(payload) {
    const data = typeof payload === 'string' ? {text: payload} : {...(payload || {})};
    return createPendingRequest({
      type: 'nextai:product:send',
      ...data
    }, Number(data.timeoutMs || 120000)).then(response => ({
      content: String(response && response.content || ''),
      raw: response
    }));
  }

  function fallbackStateKey(key, options = {}) {
    const scope = String(options.scope || 'session').trim() || 'session';
    return `nextai:state:${scope}:${String(key)}`;
  }

  function fallbackStateGet(key, fallbackValue, options = {}) {
    try {
      const raw = safeLocalStorage.getItem(fallbackStateKey(key, options));
      return raw == null ? fallbackValue : JSON.parse(raw);
    } catch (_) {
      return fallbackValue;
    }
  }

  function fallbackStateSet(key, value, options = {}) {
    try {
      safeLocalStorage.setItem(fallbackStateKey(key, options), JSON.stringify(value));
    } catch (_) {}
    return value;
  }

  function fallbackStateRemove(key, options = {}) {
    try {
      safeLocalStorage.removeItem(fallbackStateKey(key, options));
    } catch (_) {}
  }

  async function stateRequest(action, payload = {}) {
    const data = {
      type: 'nextai:product:state',
      action,
      ...payload
    };
    return createPendingRequest(data, Number(payload.timeoutMs || 5000));
  }

  const state = {
    context() {
      return {...hostContext};
    },
    async get(key, fallbackValue = null, options = {}) {
      try {
        const response = await stateRequest('get', {
          key,
          scope: options.scope,
          fallback: fallbackValue,
          timeoutMs: options.timeoutMs
        });
        return Object.prototype.hasOwnProperty.call(response || {}, 'value') ? response.value : fallbackValue;
      } catch (_) {
        return fallbackStateGet(key, fallbackValue, options);
      }
    },
    async set(key, value, options = {}) {
      try {
        await stateRequest('set', {
          key,
          value,
          scope: options.scope,
          timeoutMs: options.timeoutMs
        });
      } catch (_) {
        fallbackStateSet(key, value, options);
      }
      return value;
    },
    async remove(key, options = {}) {
      try {
        await stateRequest('remove', {
          key,
          scope: options.scope,
          timeoutMs: options.timeoutMs
        });
      } catch (_) {
        fallbackStateRemove(key, options);
      }
    }
  }

  function settlePending(data) {
    const id = String(data.requestId || '');
    if (!id || !pending.has(id)) return false;
    const item = pending.get(id);
    if (data.type === 'nextai:host:ack') {
      window.dispatchEvent(new CustomEvent('nextai:ack', {detail: data}));
      return true;
    }
    pending.delete(id);
    clearTimeout(item.timer);
    if (data.type === 'nextai:host:reply' || data.type === 'nextai:host:state') {
      item.resolve(data);
      return true;
    }
    if (data.type === 'nextai:host:error') {
      item.reject(new Error(String(data.error || 'Next AI bridge error')));
      return true;
    }
    return false;
  }

  window.addEventListener('message', event => {
    const data = event && event.data;
    if (!data || typeof data !== 'object' || data.source !== 'nextai-host') return;
    if (data.type === 'nextai:host:ready') {
      hostContext = {...data};
      window.dispatchEvent(new CustomEvent('nextai:ready', {detail: data}));
      return;
    }
    settlePending(data);
  });

  window.NextAI = {
    chat: {send},
    product: {send},
    state,
    storage: {
      local: safeLocalStorage,
      session: safeSessionStorage,
      getItem(key) {
        return safeLocalStorage.getItem(key);
      },
      setItem(key, value) {
        safeLocalStorage.setItem(key, value);
      },
      removeItem(key) {
        safeLocalStorage.removeItem(key);
      },
      clear() {
        safeLocalStorage.clear();
      }
    }
  };
})();
