"""Reference plugins demonstrating the SDK contract. They are deliberately small and self-contained.

- echo: no permissions; proves the registry + schema validation path.
- word-count: no permissions; a trivial text utility.
These show how a third party would package a capability (manifest + run) without touching core code.
Richer plugins (a new research provider, a new model backend) would declare web_search / model_call
permissions and receive host-approved handles — not shown here to avoid duplicating the core adapters.
"""
from __future__ import annotations

from plugin_sdk import Plugin, PluginManifest


class EchoPlugin(Plugin):
    manifest = PluginManifest(
        id="echo", name="Echo", version="1.0.0", description="Returns its input — contract smoke test.",
        permissions=frozenset(),
        input_schema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        output_schema={"type": "object", "properties": {"echo": {"type": "string"}}})

    def run(self, payload: dict, granted: frozenset[str]) -> dict:
        return {"echo": payload["text"]}


class WordCountPlugin(Plugin):
    manifest = PluginManifest(
        id="word-count", name="Word Count", version="1.0.0", description="Counts words in a text.",
        permissions=frozenset(),
        input_schema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        output_schema={"type": "object", "properties": {"words": {"type": "integer"}}})

    def run(self, payload: dict, granted: frozenset[str]) -> dict:
        return {"words": len(payload["text"].split())}


def default_registry():
    from plugin_sdk import PluginRegistry
    reg = PluginRegistry()
    reg.install(EchoPlugin(), enabled=True)
    reg.install(WordCountPlugin(), enabled=True)
    return reg
