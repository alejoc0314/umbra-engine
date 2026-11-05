import json
from datetime import date

import pytest
from typer.testing import CliRunner

from umbra import __version__
from umbra.cli import selfupdate
from umbra.cli.main import app
from umbra.unified import version

LS_REMOTE = """\
aaa\trefs/tags/v0.8.0
bbb\trefs/tags/v0.10.0
ccc\trefs/tags/v0.9.1
ddd\trefs/tags/v0.9.1^{}
eee\trefs/tags/nightly
"""

CHANGELOG = """# Cambios

## Sin publicar

- Algo nuevo.

## v0.8.0 — 2026-10-30

- Primera.
"""


def test_published_versions_sort_numerically_and_ignore_other_tags():
    assert version.published(LS_REMOTE) == ["0.8.0", "0.9.1", "0.10.0"]


def test_bump():
    assert version.bump("0.8.3", "patch") == "0.8.4"
    assert version.bump("0.8.3", "minor") == "0.9.0"
    assert version.bump("0.8.3", "major") == "1.0.0"
    with pytest.raises(version.VersionError):
        version.bump("0.8.3", "huge")


def test_changelog_roll_and_section():
    rolled = version.roll_changelog(CHANGELOG, "0.9.0", date(2026, 11, 2))
    assert "## Sin publicar\n\n## v0.9.0 — 2026-11-02\n\n- Algo nuevo." in rolled
    assert version.changelog_section(rolled, "0.9.0") == "- Algo nuevo."
    assert version.changelog_section(rolled, "0.8.0") == "- Primera."
    with pytest.raises(version.VersionError):  # sin nada que publicar
        version.roll_changelog(rolled, "0.9.1")


def test_the_repo_changelog_has_the_current_version():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[2] / "CHANGELOG.md").read_text(encoding="utf-8")
    assert version.changelog_section(text, __version__)


def test_windows_handoff_installs_the_tag_and_reports_back():
    script = version.handoff_script("0.9.0", r"C:\Users\x\.local\bin\uv.exe", r"C:\log's.txt")
    assert "tool install --force 'git+https://github.com/alejoc0314/umbra-engine@v0.9.0'" in script
    assert "C:\\log''s.txt" in script  # comilla simple escapada para PowerShell
    assert "Ya estás en v0.9.0" in script and "no se pudo actualizar" in script
    assert "@" + "VERSION@" not in script and "@" + "PID@" not in script  # sin marcadores
    assert "if ($false)" in script  # sin puente que esperar


def test_handoff_waits_for_the_bridge_checks_the_version_and_rolls_back():
    script = version.handoff_script(
        "0.22.0", "uv.exe", "log.txt", previous="0.21.1",
        bridge={"pid": 4321, "root": "C:/apps/repo"},
        tg={"token_env": "MI_TOKEN", "chat_id": "77"},
        tool=r"C:\uv\tools\umbra-engine", launcher=r"C:\bin\umbra.exe")
    order = ["Get-Process -Id 4321", "Stop-Process -Id 4321", "(Busy).Count",
             "umbra-engine@v0.22.0", "--version", "umbra-engine@v0.21.1"]
    pos = [script.index(s) for s in order]
    assert pos == sorted(pos)  # espera al puente, a que nada use umbra, instala, comprueba, vuelve
    assert r"$tool = 'C:\uv\tools\umbra-engine'" in script
    assert "-WorkingDirectory 'C:/apps/repo'" in script  # relanza el puente en su carpeta
    assert "GetEnvironmentVariable('MI_TOKEN')" in script and "$chat = '77'" in script
    assert "sigues en v0.21.1" in script and "El puente de Telegram volvió" in script
    assert r"v0\.22\.0\b" in script


def test_handoff_without_previous_version_has_no_rollback():
    script = version.handoff_script("0.22.0", "uv.exe", "log.txt")
    assert script.count("tool install --force") == 1 and "sigues en" not in script


def test_label_marks_the_development_copy(monkeypatch):
    monkeypatch.setattr(version, "is_dev", lambda: True)
    assert version.label() == f"v{__version__} (desarrollo)"
    monkeypatch.setattr(version, "is_dev", lambda: False)
    assert version.label() == f"v{__version__}"


@pytest.fixture
def remote(monkeypatch):
    installed = []
    monkeypatch.setattr(version, "notes", lambda v: f"- notas de {v}")
    monkeypatch.setattr(version, "install", lambda v, *a: installed.append(v) or "instalando")
    monkeypatch.setattr(version, "is_dev", lambda: False)
    monkeypatch.setattr(selfupdate, "_busy_here", lambda: [])
    return installed


def test_self_update_check_shows_whats_new(remote, monkeypatch):
    monkeypatch.setattr(version, "latest", lambda: "99.0.0")
    out = CliRunner().invoke(app, ["self-update", "--check"]).output
    assert "Última publicada: v99.0.0" in out and "notas de 99.0.0" in out
    assert remote == []


def test_self_update_check_reflows_wrapped_notes(remote, monkeypatch):
    monkeypatch.setattr(version, "latest", lambda: "99.0.0")
    monkeypatch.setattr(version, "notes", lambda v: "- **nuevo**: una frase cortada\n  a mano")
    out = CliRunner().invoke(app, ["self-update", "--check"]).output
    assert "una frase cortada a mano" in out


def test_self_update_installs_after_confirming(remote, monkeypatch):
    monkeypatch.setattr(version, "latest", lambda: "99.0.0")
    result = CliRunner().invoke(app, ["self-update"], input="y\n")
    assert result.exit_code == 0 and remote == ["99.0.0"]


def test_self_update_nothing_to_do_when_current(remote, monkeypatch):
    monkeypatch.setattr(version, "latest", lambda: __version__)
    assert "Ya tienes la última versión" in CliRunner().invoke(app, ["self-update"]).output
    assert remote == []


def test_self_update_waits_for_running_tasks(remote, monkeypatch):
    monkeypatch.setattr(version, "latest", lambda: "99.0.0")
    monkeypatch.setattr(selfupdate, "_busy_here", lambda: [7])
    result = CliRunner().invoke(app, ["self-update", "-y"])
    assert result.exit_code == 4 and remote == []


def test_dev_copy_can_switch_to_the_same_published_version(remote, monkeypatch):
    monkeypatch.setattr(version, "latest", lambda: __version__)
    monkeypatch.setattr(version, "is_dev", lambda: True)
    result = CliRunner().invoke(app, ["self-update", "-y"])
    assert result.exit_code == 0 and remote == [__version__]


def test_version_flag(monkeypatch):
    monkeypatch.setattr(version, "is_dev", lambda: False)
    assert CliRunner().invoke(app, ["--version"]).output.strip() == f"umbra v{__version__}"


def test_is_dev_reads_the_install_record(monkeypatch):
    class Dist:
        def __init__(self, data):
            self.data = data

        def read_text(self, name):
            return json.dumps(self.data)

    monkeypatch.setattr(version.metadata, "distribution",
                        lambda name: Dist({"dir_info": {"editable": True}}))
    assert version.is_dev()
    monkeypatch.setattr(version.metadata, "distribution",
                        lambda name: Dist({"vcs_info": {"commit_id": "abc"}}))
    assert not version.is_dev()
