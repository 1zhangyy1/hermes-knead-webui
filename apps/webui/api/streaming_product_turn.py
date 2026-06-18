"""Product-generation turn finalization for WebUI streaming."""

from __future__ import annotations

from typing import Callable


PRODUCT_BUILD_SCOPES = {"product_init", "product_builder"}


class ProductTurnFinalizer:
    """Finalize product-generation state once for a streaming turn."""

    def __init__(
        self,
        product_context: dict | None,
        *,
        logger=None,
        finalize_fn: Callable[..., object] | None = None,
    ):
        self.product_context = product_context
        self.logger = logger
        self.finalize_fn = finalize_fn
        self.finalized = False

    def finalize(
        self,
        *,
        failed: bool = False,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        if self.finalized:
            return
        product_id = self._product_id_to_finalize()
        if not product_id:
            self.finalized = True
            return
        try:
            self._finalize_fn()(
                product_id,
                failed=failed,
                error_type=error_type,
                error_message=error_message,
            )
            # Only mark complete after the status write succeeds. If the write
            # fails, a later terminal path can retry instead of leaving the
            # product stuck in "generating".
            self.finalized = True
        except Exception:
            if self.logger is not None:
                self.logger.warning(
                    "Failed to finalize product generation for %s",
                    product_id,
                    exc_info=True,
                )

    def _product_id_to_finalize(self) -> str:
        context = self.product_context
        if not context:
            return ""
        if str(context.get("scope") or "") not in PRODUCT_BUILD_SCOPES:
            return ""
        return str(context.get("id") or "").strip()

    def _finalize_fn(self):
        if self.finalize_fn is not None:
            return self.finalize_fn
        from api.products import finalize_product_generation

        return finalize_product_generation

