// AI product UI recovery actions.
// Product UI generation and edits happen through normal chat turns
// (`product_init` / `product_builder`).

async function rollbackCurrentProductUiVersion() {
  if (!_activeProductPreview || !_activeProductPreview.product_preview) {
    if (typeof showToast === 'function') showToast('当前没有可恢复的产品画布');
    return;
  }
  const productId = String(_activeProductPreview.product_id || '').trim();
  if (!productId || !_activeProductPreview.can_rollback) {
    if (typeof showToast === 'function') showToast('这个 AI 产品还没有上一版画布可恢复');
    return;
  }
  try {
    const data = await api(`/api/products/${encodeURIComponent(productId)}/rollback`, {
      method: 'POST',
      body: JSON.stringify({ version_id: _activeProductPreview.previous_version || '' })
    });
    if (data && data.product && typeof _applyBackendProductToLocal === 'function') {
      _applyBackendProductToLocal(data.product);
    }
    if (typeof refreshCurrentProductPreview === 'function') {
      await refreshCurrentProductPreview({ silent: true, reason: 'product-rollback' });
    }
    if (typeof showToast === 'function') showToast('已恢复上一版产品画布');
  } catch (e) {
    if (typeof showToast === 'function') showToast('恢复上一版产品画布失败：' + (e.message || e));
  }
}

window.rollbackCurrentProductUiVersion = rollbackCurrentProductUiVersion;
