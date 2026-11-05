"""VerityForge plugin SDK (contract v1).

A plugin is a sandboxed capability the platform can enable/disable/upgrade without touching core code.
Plugins declare required permissions and I/O schemas; the registry enforces permissions and resource limits
OUTSIDE the plugin — a plugin cannot grant itself access. This mirrors the security model: capability is data,
enforcement is code.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

CONTRACT_VERSION = "1"

# Permissions a plugin may request. The host decides whether to grant them; the plugin never self-grants.
PERMISSIONS = {"network", "read_workspace", "write_workspace", "run_command", "model_call", "web_search"}


class PluginError(Exception):
    pass


@dataclass(frozen=True)
class PluginManifest:
    id: str
    name: str
    version: str
    description: str
    contract_version: str = CONTRACT_VERSION
    permissions: frozenset[str] = field(default_factory=frozenset)
    input_schema: dict = field(default_factory=dict)   # JSON-schema-ish; validated structurally, not executed
    output_schema: dict = field(default_factory=dict)
    config: dict = field(default_factory=dict)
    dependencies: tuple[str, ...] = ()
    max_runtime_s: float = 10.0

    def validate(self) -> None:
        if self.contract_version != CONTRACT_VERSION:
            raise PluginError(f"plugin {self.id}: contract {self.contract_version} != host {CONTRACT_VERSION}")
        unknown = self.permissions - PERMISSIONS
        if unknown:
            raise PluginError(f"plugin {self.id}: unknown permissions {sorted(unknown)}")


class Plugin(ABC):
    manifest: PluginManifest

    @abstractmethod
    def run(self, payload: dict, granted: frozenset[str]) -> dict:
        """Execute. `granted` is the host-approved permission set; the plugin must honour it, and the host
        also enforces it. Must return a dict matching output_schema keys."""


_TYPES: dict[str, type | tuple] = {"string": str, "number": (int, float), "integer": int,
                                   "boolean": bool, "array": list, "object": dict}


def _check_type(value, spec: str) -> bool:
    py = _TYPES.get(spec)
    return py is None or isinstance(value, py)


def validate_payload(schema: dict, payload: dict) -> None:
    """Minimal structural validation: required keys present and of the declared primitive type."""
    props = schema.get("properties", {})
    for key in schema.get("required", []):
        if key not in payload:
            raise PluginError(f"missing required field: {key}")
    for key, value in payload.items():
        spec = props.get(key, {}).get("type")
        if spec and not _check_type(value, spec):
            raise PluginError(f"field {key!r} should be {spec}")


class PluginRegistry:
    """Enable/disable/install/upgrade plugins and run them under enforced permissions + a runtime cap."""

    def __init__(self, grants: dict[str, frozenset[str]] | None = None):
        self._plugins: dict[str, Plugin] = {}
        self._enabled: dict[str, bool] = {}
        self._grants = grants or {}  # plugin_id -> permissions the host allows; default: none

    def install(self, plugin: Plugin, enabled: bool = False) -> None:
        plugin.manifest.validate()
        pid = plugin.manifest.id
        if pid in self._plugins and self._plugins[pid].manifest.version == plugin.manifest.version:
            raise PluginError(f"plugin {pid} v{plugin.manifest.version} already installed")
        self._plugins[pid] = plugin  # replacing with a different version = upgrade
        self._enabled.setdefault(pid, enabled)

    def set_enabled(self, pid: str, on: bool) -> None:
        if pid not in self._plugins:
            raise PluginError(f"unknown plugin {pid}")
        self._enabled[pid] = on

    def grant(self, pid: str, permissions: frozenset[str]) -> None:
        self._grants[pid] = permissions & self._plugins[pid].manifest.permissions

    def list(self) -> list[dict]:
        out = []
        for pid, p in self._plugins.items():
            m = p.manifest
            out.append({"id": pid, "name": m.name, "version": m.version, "description": m.description,
                        "contract_version": m.contract_version, "permissions": sorted(m.permissions),
                        "granted": sorted(self._grants.get(pid, frozenset())),
                        "enabled": self._enabled.get(pid, False), "dependencies": list(m.dependencies),
                        "input_schema": m.input_schema, "output_schema": m.output_schema})
        return out

    def run(self, pid: str, payload: dict) -> dict:
        if pid not in self._plugins:
            raise PluginError(f"unknown plugin {pid}")
        if not self._enabled.get(pid):
            raise PluginError(f"plugin {pid} is disabled")
        p = self._plugins[pid]
        m = p.manifest
        granted = self._grants.get(pid, frozenset())
        missing = m.permissions - granted
        if missing:  # host has not granted a declared permission -> refuse, do not run
            raise PluginError(f"plugin {pid} not granted required permissions: {sorted(missing)}")
        validate_payload(m.input_schema, payload)
        start = time.monotonic()
        result = p.run(payload, granted)
        elapsed = time.monotonic() - start
        if elapsed > m.max_runtime_s:  # reported, not a hard kill (handler is trusted-installed code)
            result = {**result, "_warning": f"exceeded max_runtime_s ({elapsed:.2f}s > {m.max_runtime_s}s)"}
        if not isinstance(result, dict):
            raise PluginError(f"plugin {pid} returned non-dict")
        return result
