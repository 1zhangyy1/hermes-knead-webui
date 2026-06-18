"""Path resolution helpers for session/profile-backed state."""

import os
from pathlib import Path


def profile_home(profile, *, environ=None) -> Path:
    """Resolve the Hermes agent home directory for a profile."""
    try:
        from api.profiles import get_hermes_home_for_profile
        return Path(get_hermes_home_for_profile(profile))
    except ImportError:
        env = environ if environ is not None else os.environ
        return Path(env.get('HERMES_HOME') or '~/.hermes').expanduser()


def active_state_db_path(*, home, environ=None) -> Path:
    """Return state.db for the active Hermes profile, degrading to HERMES_HOME."""
    try:
        from api.profiles import get_active_hermes_home
        hermes_home = Path(get_active_hermes_home()).expanduser().resolve()
    except Exception:
        env = environ if environ is not None else os.environ
        hermes_home = Path(env.get('HERMES_HOME', str(home / '.hermes'))).expanduser().resolve()
    return hermes_home / 'state.db'
