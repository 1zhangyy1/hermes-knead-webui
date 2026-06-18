from api.streaming_errors import exception_error_copy


def test_exception_error_copy_uses_classifier_copy_for_terminal_types():
    classification = {
        'label': 'Out of credits',
        'type': 'quota_exhausted',
        'hint': 'Top up',
    }

    assert exception_error_copy(classification) == (
        'Out of credits',
        'quota_exhausted',
        'Top up',
    )


def test_exception_error_copy_preserves_outer_auth_error_copy():
    assert exception_error_copy({
        'label': 'Authentication failed',
        'type': 'auth_mismatch',
        'hint': 'ignored',
    }) == (
        'Authentication error',
        'auth_mismatch',
        'The selected model may not be supported by your configured provider. '
        'Run `hermes model` in your terminal to switch providers, then restart the WebUI.',
    )


def test_exception_error_copy_defaults_unknown_types_to_generic_error():
    assert exception_error_copy({'label': 'Something else', 'type': 'unexpected', 'hint': 'ignored'}) == (
        'Error',
        'error',
        '',
    )
