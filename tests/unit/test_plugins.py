import pytest

from example_plugins import EchoPlugin, WordCountPlugin, default_registry
from plugin_sdk import CONTRACT_VERSION, Plugin, PluginError, PluginManifest, PluginRegistry


def test_manifest_validation_rejects_unknown_permission():
    m = PluginManifest(id="x", name="X", version="1.0", description="", permissions=frozenset({"telepathy"}))
    with pytest.raises(PluginError, match="unknown permissions"):
        m.validate()


def test_manifest_validation_rejects_wrong_contract():
    m = PluginManifest(id="x", name="X", version="1.0", description="", contract_version="999")
    with pytest.raises(PluginError, match="contract"):
        m.validate()


def test_registry_runs_permissionless_plugin():
    reg = default_registry()
    assert reg.run("echo", {"text": "hi"}) == {"echo": "hi"}
    assert reg.run("word-count", {"text": "a b c"}) == {"words": 3}


def test_schema_validation_rejects_bad_payload():
    reg = default_registry()
    with pytest.raises(PluginError, match="required"):
        reg.run("echo", {})
    with pytest.raises(PluginError, match="should be string"):
        reg.run("echo", {"text": 123})


def test_disabled_plugin_refuses_to_run():
    reg = default_registry()
    reg.set_enabled("echo", False)
    with pytest.raises(PluginError, match="disabled"):
        reg.run("echo", {"text": "x"})


def test_plugin_without_granted_permission_is_refused():
    class Netty(Plugin):
        manifest = PluginManifest(id="netty", name="Net", version="1.0", description="",
                                  permissions=frozenset({"network"}),
                                  input_schema={"type": "object", "properties": {}, "required": []})

        def run(self, payload, granted):
            return {"ok": True}

    reg = PluginRegistry()
    reg.install(Netty(), enabled=True)
    with pytest.raises(PluginError, match="not granted required permissions"):
        reg.run("netty", {})  # declared 'network' but host granted nothing
    reg.grant("netty", frozenset({"network"}))
    assert reg.run("netty", {}) == {"ok": True}


def test_upgrade_replaces_version():
    reg = PluginRegistry()
    reg.install(EchoPlugin(), enabled=True)
    with pytest.raises(PluginError, match="already installed"):
        reg.install(EchoPlugin())  # same version
    assert reg.list()[0]["contract_version"] == CONTRACT_VERSION


def test_grant_cannot_exceed_declared_permissions():
    reg = default_registry()
    reg.grant("echo", frozenset({"network", "run_command"}))  # echo declares none
    assert reg.list()[0]["granted"] == []  # intersection with declared (empty) -> nothing granted
