"""Registro de adaptadores. El núcleo solo conoce nombres, nunca clases concretas."""

from pathlib import Path

from umbra.adapters.base import Adapter
from umbra.adapters.claude_code import ClaudeCodeAdapter
from umbra.adapters.codex import CodexAdapter
from umbra.adapters.script import ScriptAdapter
from umbra.unified import agents

ADAPTERS: dict[str, type] = {
    "claude-code": ClaudeCodeAdapter,
    "codex": CodexAdapter,
}


class UnknownAgent(Exception):
    pass


def get_adapter(name: str, udir: Path | None = None, require_verified: bool = True) -> Adapter:
    if name in ADAPTERS:
        return ADAPTERS[name]()
    agent_dir = agents.find(name, udir)
    if agent_dir is None:
        raise UnknownAgent(f"agente desconocido: {name} (regístralo con `umbra agent add`)")
    if require_verified and not agents.is_verified(agent_dir):
        raise agents.AgentNotVerified(
            f"agente no verificado: {name} (ejecuta `umbra agent test {name}`)")
    return ScriptAdapter(agents.load_manifest(agent_dir), agent_dir)
