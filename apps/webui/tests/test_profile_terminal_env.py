import os
from pathlib import Path

import yaml

WEBUI_ROOT = Path(__file__).resolve().parent.parent


def test_profile_runtime_env_includes_terminal_config_and_dotenv(tmp_path):
    from api.profiles import get_profile_runtime_env

    home = tmp_path / "profiles" / "server-ops"
    home.mkdir(parents=True)
    (home / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "terminal": {
                    "backend": "ssh",
                    "cwd": "/home/dso2ng/repos",
                    "timeout": 180,
                    "ssh_host": "pollux",
                    "ssh_user": "dso2ng",
                    "persistent_shell": True,
                    "lifetime_seconds": 300,
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (home / ".env").write_text(
        "TERMINAL_TIMEOUT=60\n"
        "TERMINAL_SSH_HOST=pollux-from-env\n"
        "HERMES_MAX_ITERATIONS=90\n",
        encoding="utf-8",
    )

    env = get_profile_runtime_env(home)

    assert env["TERMINAL_ENV"] == "ssh"
    assert env["TERMINAL_CWD"] == "/home/dso2ng/repos"
    assert env["TERMINAL_SSH_USER"] == "dso2ng"
    assert env["TERMINAL_PERSISTENT_SHELL"] == "true"
    assert env["TERMINAL_LIFETIME_SECONDS"] == "300"
    # .env remains the final override source, matching CLI/profile behaviour.
    assert env["TERMINAL_TIMEOUT"] == "60"
    assert env["TERMINAL_SSH_HOST"] == "pollux-from-env"
    assert env["HERMES_MAX_ITERATIONS"] == "90"


def test_streaming_applies_profile_runtime_env_to_agent_run():
    streaming_src = (WEBUI_ROOT / "api" / "streaming.py").read_text(encoding="utf-8")
    helper_src = (WEBUI_ROOT / "api" / "streaming_runtime_helpers.py").read_text(encoding="utf-8")

    assert "get_profile_runtime_env" in helper_src
    assert "_profile_runtime = resolve_profile_runtime_fn(session)" in helper_src
    assert "_profile_runtime_env" in helper_src
    assert "old_profile_env = _profile_activation.profile_env_snapshot" in streaming_src
    assert "os.environ.update(profile_runtime_env)" in helper_src


def test_streaming_thread_env_allows_profile_terminal_cwd_override():
    from api.streaming_runtime_helpers import build_agent_thread_env

    helper_src = (WEBUI_ROOT / "api" / "streaming_runtime_helpers.py").read_text(encoding="utf-8")

    assert "_thread_env = build_thread_env_fn(" in helper_src
    assert "set_thread_env(**_thread_env)" in helper_src
    assert "set_thread_env(\n            **_profile_runtime_env,\n            TERMINAL_CWD" not in helper_src

    env = build_agent_thread_env(
        {
            "TERMINAL_CWD": "/profile/config/cwd",
            "HERMES_EXEC_ASK": "0",
            "HERMES_SESSION_KEY": "old-session",
            "HERMES_SESSION_ID": "old-session",
            "HERMES_SESSION_PLATFORM": "cli",
            "HERMES_HOME": "/old/profile/home",
            "TERMINAL_ENV": "ssh",
        },
        "/active/workspace",
        "active-session",
        "/active/profile/home",
    )

    assert env["TERMINAL_CWD"] == "/active/workspace"
    assert env["HERMES_EXEC_ASK"] == "1"
    assert env["HERMES_SESSION_KEY"] == "active-session"
    assert env["HERMES_SESSION_ID"] == "active-session"
    assert env["HERMES_SESSION_PLATFORM"] == "webui"
    assert env["HERMES_HOME"] == "/active/profile/home"
    assert env["TERMINAL_ENV"] == "ssh"
