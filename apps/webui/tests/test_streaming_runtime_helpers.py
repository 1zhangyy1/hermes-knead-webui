import builtins
import os
import sys
import types

from api.streaming_runtime_helpers import (
    apply_streaming_profile_process_env,
    activate_streaming_profile_runtime,
    discover_mcp_tools_for_profile,
    prewarm_skill_tool_modules,
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


def test_prewarm_skill_tool_modules_imports_best_effort(monkeypatch):
    imported = []
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        imported.append(name)
        if name == 'missing.module':
            raise ImportError(name)
        return real_import('types')

    monkeypatch.setattr(builtins, '__import__', fake_import)

    prewarm_skill_tool_modules(('tools.skills_tool', 'missing.module', 'tools.skill_manager_tool'))

    assert imported == ['tools.skills_tool', 'missing.module', 'tools.skill_manager_tool']


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


def test_apply_streaming_profile_process_env_sets_and_snapshots_process_env(monkeypatch, tmp_path):
    monkeypatch.setenv("PROFILE_KEY", "old-profile")
    monkeypatch.setenv("TERMINAL_CWD", "/old")
    monkeypatch.delenv("HERMES_SESSION_PLATFORM", raising=False)
    patched_homes = []
    lock = DummyLock()
    profile_home = tmp_path / "profile-home"

    snapshot = apply_streaming_profile_process_env(
        profile_runtime_env={"PROFILE_KEY": "new-profile"},
        workspace="/workspace",
        session_id="sid-1",
        profile_home=str(profile_home),
        patch_skill_home_modules=lambda home: patched_homes.append(home),
        env_lock=lock,
    )

    assert lock.entered is True
    assert lock.exited is True
    assert os.environ["PROFILE_KEY"] == "new-profile"
    assert os.environ["TERMINAL_CWD"] == "/workspace"
    assert os.environ["HERMES_EXEC_ASK"] == "1"
    assert os.environ["HERMES_SESSION_KEY"] == "sid-1"
    assert os.environ["HERMES_SESSION_ID"] == "sid-1"
    assert os.environ["HERMES_SESSION_PLATFORM"] == "webui"
    assert os.environ["HERMES_HOME"] == str(profile_home)
    assert patched_homes == [profile_home]
    assert snapshot.profile_env_snapshot == {"PROFILE_KEY": "old-profile"}
    assert snapshot.runtime_env_snapshot["TERMINAL_CWD"] == "/old"
    assert snapshot.runtime_env_snapshot["HERMES_SESSION_PLATFORM"] is None


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


def test_activate_streaming_profile_runtime_orders_thread_env_process_env_and_discovery():
    calls = []
    runtime = types.SimpleNamespace(
        profile_home="/profiles/work",
        profile_runtime_env={"PROFILE_KEY": "value"},
        resolved_profile_name="work",
        patch_skill_home_modules="patcher",
    )
    snapshot = types.SimpleNamespace(
        profile_env_snapshot={"PROFILE_KEY": "old"},
        runtime_env_snapshot={"HERMES_HOME": "old-home"},
    )

    activation = activate_streaming_profile_runtime(
        types.SimpleNamespace(profile="work"),
        workspace="/workspace",
        session_id="sid-1",
        set_thread_env=lambda **env: calls.append(("thread-env", env)),
        env_lock="env-lock",
        resolve_profile_runtime_fn=lambda session: calls.append(("resolve", session.profile)) or runtime,
        build_thread_env_fn=lambda runtime_env, workspace, session_id, profile_home: (
            calls.append(("build-thread-env", runtime_env, workspace, session_id, profile_home))
            or {"HERMES_HOME": profile_home, "TERMINAL_CWD": workspace}
        ),
        prewarm_skill_tool_modules_fn=lambda: calls.append(("prewarm",)),
        apply_profile_process_env_fn=lambda **kwargs: calls.append(("process-env", kwargs)) or snapshot,
        discover_mcp_tools_fn=lambda: calls.append(("discover",)),
    )

    assert activation.profile_home == "/profiles/work"
    assert activation.resolved_profile_name == "work"
    assert activation.profile_env_snapshot == {"PROFILE_KEY": "old"}
    assert activation.runtime_env_snapshot == {"HERMES_HOME": "old-home"}
    assert [call[0] for call in calls] == [
        "resolve",
        "build-thread-env",
        "thread-env",
        "prewarm",
        "process-env",
        "discover",
    ]
    assert calls[4][1]["profile_runtime_env"] == {"PROFILE_KEY": "value"}
    assert calls[4][1]["patch_skill_home_modules"] == "patcher"
    assert calls[4][1]["env_lock"] == "env-lock"
