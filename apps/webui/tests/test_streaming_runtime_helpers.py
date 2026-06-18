import os
import sys
import types

from api.streaming_runtime_helpers import (
    discover_mcp_tools_for_profile,
    restore_agent_process_env,
    restore_env_snapshot,
    resolve_streaming_profile_runtime,
)


class DummyLock:
    def __init__(self):
        self.entered = False
        self.exited = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc, tb):
        self.exited = True


def test_restore_env_snapshot_restores_and_removes_values(monkeypatch):
    monkeypatch.setenv('KEEP_ME', 'new')
    monkeypatch.setenv('DROP_ME', 'new')

    restore_env_snapshot({
        'KEEP_ME': 'old',
        'DROP_ME': None,
    })

    assert os.environ['KEEP_ME'] == 'old'
    assert 'DROP_ME' not in os.environ


def test_restore_agent_process_env_uses_lock_and_restores_both_snapshots(monkeypatch):
    monkeypatch.setenv('PROFILE_KEY', 'new')
    monkeypatch.setenv('TERMINAL_CWD', '/new')
    monkeypatch.setenv('HERMES_SESSION_ID', 'new-session')
    lock = DummyLock()

    restore_agent_process_env(
        {'PROFILE_KEY': 'old-profile'},
        {
            'TERMINAL_CWD': '/old',
            'HERMES_SESSION_ID': None,
        },
        env_lock=lock,
    )

    assert lock.entered is True
    assert lock.exited is True
    assert os.environ['PROFILE_KEY'] == 'old-profile'
    assert os.environ['TERMINAL_CWD'] == '/old'
    assert 'HERMES_SESSION_ID' not in os.environ


def test_discover_mcp_tools_for_profile_runs_best_effort(monkeypatch):
    calls = []
    tools_pkg = types.ModuleType("tools")
    mcp_tool = types.ModuleType("tools.mcp_tool")
    mcp_tool.discover_mcp_tools = lambda: calls.append("discover")
    monkeypatch.setitem(sys.modules, "tools", tools_pkg)
    monkeypatch.setitem(sys.modules, "tools.mcp_tool", mcp_tool)

    assert discover_mcp_tools_for_profile() is True
    assert calls == ["discover"]

    mcp_tool.discover_mcp_tools = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    assert discover_mcp_tools_for_profile() is False


def test_resolve_streaming_profile_runtime_uses_session_profile(monkeypatch, tmp_path):
    from api import profiles

    profile_home = tmp_path / "profiles" / "work"
    patcher = object()
    monkeypatch.setattr(profiles, "get_hermes_home_for_profile", lambda profile: profile_home)
    monkeypatch.setattr(profiles, "get_profile_runtime_env", lambda home: {"PROFILE_HOME": str(home)})
    monkeypatch.setattr(profiles, "patch_skill_home_modules", patcher)
    monkeypatch.setattr(profiles, "get_active_profile_name", lambda: "active")

    runtime = resolve_streaming_profile_runtime(types.SimpleNamespace(profile="work"))

    assert runtime.profile_home == str(profile_home)
    assert runtime.profile_runtime_env == {"PROFILE_HOME": str(profile_home)}
    assert runtime.resolved_profile_name == "work"
    assert runtime.patch_skill_home_modules is patcher


def test_resolve_streaming_profile_runtime_falls_back_to_active_profile(monkeypatch, tmp_path):
    from api import profiles

    profile_home = tmp_path / "default-home"
    monkeypatch.setattr(profiles, "get_hermes_home_for_profile", lambda profile: profile_home)
    monkeypatch.setattr(profiles, "get_profile_runtime_env", lambda home: {})
    monkeypatch.setattr(profiles, "get_active_profile_name", lambda: "active")

    runtime = resolve_streaming_profile_runtime(types.SimpleNamespace(profile=None))

    assert runtime.profile_home == str(profile_home)
    assert runtime.resolved_profile_name == "active"
