from api.streaming_product_turn import ProductTurnFinalizer


class _Logger:
    def __init__(self):
        self.warnings = []

    def warning(self, *args, **kwargs):
        self.warnings.append((args, kwargs))


def test_product_turn_finalizer_skips_non_build_contexts():
    calls = []

    ProductTurnFinalizer(None, finalize_fn=lambda *a, **k: calls.append((a, k))).finalize()
    ProductTurnFinalizer({"scope": "product_usage", "id": "demo"}, finalize_fn=lambda *a, **k: calls.append((a, k))).finalize()
    ProductTurnFinalizer({"scope": "product_builder", "id": ""}, finalize_fn=lambda *a, **k: calls.append((a, k))).finalize()

    assert calls == []


def test_product_turn_finalizer_writes_status_once():
    calls = []
    finalizer = ProductTurnFinalizer(
        {"scope": "product_builder", "id": "demo"},
        finalize_fn=lambda *a, **k: calls.append((a, k)),
    )

    finalizer.finalize(failed=True, error_type="quota", error_message="out")
    finalizer.finalize(failed=False)

    assert calls == [
        (("demo",), {"failed": True, "error_type": "quota", "error_message": "out"})
    ]
    assert finalizer.finalized is True


def test_product_turn_finalizer_retries_after_write_failure():
    logger = _Logger()
    calls = []

    def finalize_fn(*args, **kwargs):
        calls.append((args, kwargs))
        if len(calls) == 1:
            raise RuntimeError("temporary write failure")

    finalizer = ProductTurnFinalizer(
        {"scope": "product_init", "id": "demo"},
        logger=logger,
        finalize_fn=finalize_fn,
    )

    finalizer.finalize(failed=True, error_type="error", error_message="boom")
    assert finalizer.finalized is False

    finalizer.finalize(failed=False)
    assert finalizer.finalized is True
    assert len(calls) == 2
    assert logger.warnings
