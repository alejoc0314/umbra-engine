"""Versión instalada, versiones publicadas (etiquetas vX.Y.Z) e instalación estable.

La instalación de diario sale de una versión publicada, no de la carpeta donde se desarrolla
umbra: así lo que está a medias en una rama no afecta a las tareas en marcha.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from importlib import metadata
from pathlib import Path

from umbra import __version__
from umbra.blocks import notify
from umbra.blocks.process import background_kwargs
from umbra.unified import config as cfg

REPO = os.environ.get("UMBRA_REPO", "https://github.com/alejoc0314/umbra-engine")
_TAG = re.compile(r"refs/tags/v(\d+\.\d+\.\d+)$")
UNRELEASED = "## Sin publicar"


class VersionError(Exception):
    pass


def parse(version: str) -> tuple[int, int, int]:
    major, minor, patch = (int(p) for p in version.lstrip("v").split("."))
    return major, minor, patch


def bump(version: str, part: str) -> str:
    major, minor, patch = parse(version)
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise VersionError(f"parte desconocida: {part} (major, minor o patch)")


def is_dev() -> bool:
    """¿Instalado en modo editable, apuntando a una carpeta de desarrollo?"""
    try:
        direct = metadata.distribution("umbra-engine").read_text("direct_url.json")
    except metadata.PackageNotFoundError:
        return True  # ejecutado desde el código fuente sin instalar
    return bool(direct and json.loads(direct).get("dir_info", {}).get("editable"))


def label() -> str:
    return f"v{__version__}" + (" (desarrollo)" if is_dev() else "")


def published(ls_remote: str) -> list[str]:
    """Versiones publicadas, de la más antigua a la más nueva."""
    found = {m.group(1) for line in ls_remote.splitlines()
             if (m := _TAG.search(line.split("\t")[-1].strip()))}
    return sorted(found, key=parse)


def latest(repo: str = REPO) -> str | None:
    proc = subprocess.run(["git", "ls-remote", "--tags", repo], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise VersionError("no se pudo consultar las versiones publicadas: "
                           + (proc.stderr.strip() or "git ls-remote falló"))
    versions = published(proc.stdout)
    return versions[-1] if versions else None


def notes(version: str, repo: str = REPO) -> str:
    """Notas de la versión publicada (vacío si no se pueden leer)."""
    slug = "/".join(repo.rstrip("/").split("/")[-2:])
    try:
        proc = subprocess.run(["gh", "release", "view", f"v{version}", "--repo", slug,
                               "--json", "body", "-q", ".body"], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def install_spec(version: str, repo: str = REPO) -> str:
    return f"git+{repo}@v{version}"


BRIDGE_WAIT_S = 60  # el puente sale tras su espera de Telegram (25 s); luego se fuerza
BUSY_WAIT_S = 600  # watch abierto o tareas en marcha: hasta 10 min, luego se desiste

_SCRIPT = r"""$log = '@LOG@'
function Tell($text) {
  Add-Content -Path $log -Value $text -Encoding UTF8
  $chat = '@CHAT@'
  $tok = [Environment]::GetEnvironmentVariable('@TOKEN_ENV@')
  if ($chat -and $tok) {
    $api = 'https://api.telegram.org'
    if ($env:UMBRA_TELEGRAM_API) { $api = $env:UMBRA_TELEGRAM_API }
    $body = [Text.Encoding]::UTF8.GetBytes((@{chat_id = $chat; text = $text} | ConvertTo-Json))
    $type = 'application/json; charset=utf-8'
    try {
      Invoke-RestMethod -Method Post -Uri "$api/bot$tok/sendMessage" -ContentType $type `
        -Body $body | Out-Null
    } catch {}
  }
}
function Busy {
  # el lanzador, el python de la instalación y el python base que este arranca (su línea de
  # comandos nombra la instalación): todos dejan archivos de umbra en uso
  $tool = '@TOOL@'
  @(Get-CimInstance Win32_Process | Where-Object {
    $p = $_.ExecutablePath; $c = $_.CommandLine
    ($p -and $p -ieq '@LAUNCHER@') -or ($tool -and (
      ($p -and $p.StartsWith($tool, 'OrdinalIgnoreCase')) -or
      ($c -and $c.IndexOf($tool, [StringComparison]::OrdinalIgnoreCase) -ge 0)))
  })
}
function Bridge {
  if ('@ROOT@') {
    Start-Process -FilePath '@LAUNCHER@' -ArgumentList 'bridge' -WorkingDirectory '@ROOT@' `
      -WindowStyle Hidden
  }
}
Set-Content -Path $log -Value "umbra: actualizar a v@VERSION@" -Encoding UTF8
Start-Sleep -Seconds 2
if (@PID@) {
  $t = 0
  while ((Get-Process -Id @PID@ -ErrorAction SilentlyContinue) -and $t -lt @BRIDGE_WAIT@) {
    Start-Sleep -Seconds 1; $t++
  }
  Stop-Process -Id @PID@ -Force -ErrorAction SilentlyContinue
}
$t = 0
while ((Busy).Count -gt 0 -and $t -lt @BUSY_WAIT@) { Start-Sleep -Seconds 5; $t += 5 }
if ((Busy).Count -gt 0) {
  Bridge
@TOAST_BUSY@
  Tell ("umbra no se actualizó a v@VERSION@: hay umbra abierto (watch o tareas en marcha). " +
        "Ciérralo y vuelve a intentarlo.")
  exit 1
}
& '@UV@' tool install --force '@SPEC@' *>> $log
$ok = $LASTEXITCODE -eq 0
if ($ok) { $ok = ((& '@LAUNCHER@' --version 2>&1) | Out-String) -match 'v@VERSION_RE@\b' }
if ($ok) {
  Bridge
@TOAST_OK@
  Tell "Ya estoy en v@VERSION@.@BACK@"
  exit 0
}
@ROLLBACK@
Bridge
@TOAST_BAD@
Tell "umbra no se pudo actualizar a v@VERSION@@STILL@. Detalle: @LOG@"
exit 1
"""


def handoff_script(version: str, uv: str, log: str, repo: str = REPO, *,
                   previous: str | None = None, bridge: dict | None = None,
                   tg: dict | None = None, tool: str = "", launcher: str = "umbra") -> str:
    """PowerShell que instala cuando nada usa umbra: en Windows un programa en uso no se puede
    reemplazar, y umbra corre desde la misma instalación que va a cambiar. Espera al puente,
    instala, comprueba que la versión nueva arranca (si no, vuelve a la anterior), relanza el
    puente y avisa por Windows y Telegram (el token se lee del entorno, nunca se escribe)."""
    q = lambda s: str(s).replace("'", "''")  # noqa: E731 — comilla simple de PowerShell
    rollback = (f"& '{q(uv)}' tool install --force '{q(install_spec(previous, repo))}' *>> $log"
                if previous else "")
    bridge = bridge or {}
    back = " El puente de Telegram volvió." if bridge.get("root") else ""
    values = {
        "LOG": q(log), "CHAT": q((tg or {}).get("chat_id", "")),
        "TOKEN_ENV": q((tg or {}).get("token_env", "")), "TOOL": q(tool),
        "LAUNCHER": q(launcher), "ROOT": q(bridge.get("root") or ""),
        "PID": str(int(bridge["pid"])) if bridge.get("pid") else "$false",
        "BRIDGE_WAIT": str(BRIDGE_WAIT_S), "BUSY_WAIT": str(BUSY_WAIT_S), "UV": q(uv),
        "SPEC": q(install_spec(version, repo)), "VERSION": version,
        "VERSION_RE": re.escape(version), "BACK": back, "ROLLBACK": rollback,
        "STILL": f"; sigues en v{previous}" if previous else "",
        "TOAST_OK": notify.toast_script("umbra actualizado", f"Ya estás en v{version}."),
        "TOAST_BAD": notify.toast_script("umbra no se pudo actualizar", f"Detalle: {log}"),
        "TOAST_BUSY": notify.toast_script("umbra no se actualizó",
                                          "Cierra umbra watch o espera a que terminen las "
                                          "tareas y vuelve a intentarlo."),
    }
    script = _SCRIPT
    for key, value in values.items():
        script = script.replace(f"@{key}@", value)
    return script


def tool_dir(uv: str, bin_: bool = False) -> str:
    """Carpeta de la instalación de umbra (`uv tool dir`/umbra-engine) o, con `bin_`, la de
    los lanzadores: lo que no puede estar en uso al instalar."""
    args = [uv, "tool", "dir", *(["--bin"] if bin_ else [])]
    proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    base = proc.stdout.strip() if proc.returncode == 0 else ""
    if not base:
        return ""
    return str(Path(base) / ("umbra.exe" if bin_ else "umbra-engine"))


def install(version: str, previous: str | None = None, bridge: dict | None = None,
            tg: dict | None = None) -> str:
    """Instala la versión publicada. `bridge` (de `bridge.handoff()`) es el puente detenido que
    hay que esperar y relanzar; `tg`, a quién avisar. Devuelve qué pasó."""
    uv = shutil.which("uv")
    if not uv:
        raise VersionError("no encuentro `uv` en el PATH; instálalo o añádelo y reintenta")
    if sys.platform != "win32":  # sin bloqueo de archivos: se instala ya
        launcher = shutil.which("umbra") or "umbra"
        proc = subprocess.run([uv, "tool", "install", "--force", install_spec(version)])
        if bridge and bridge.get("root"):
            subprocess.Popen([launcher, "bridge"], cwd=bridge["root"],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, **background_kwargs())
        if proc.returncode != 0:
            raise VersionError("uv no pudo instalar la versión (mira el mensaje de arriba)")
        return f"Instalada v{version}."
    home = cfg.umbra_home()
    home.mkdir(parents=True, exist_ok=True)
    script, log = home / "self-update.ps1", home / "self-update.log"
    script.write_text(handoff_script(version, uv, str(log), previous=previous, bridge=bridge,
                                     tg=tg, tool=tool_dir(uv),
                                     launcher=tool_dir(uv, bin_=True) or "umbra"),
                      encoding="utf-8-sig")
    subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                      "Bypass", "-File", str(script)], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **background_kwargs())
    return (f"Actualizando a v{version} en segundo plano: espero a que nada use umbra (el "
            "puente, watch o tareas en marcha), instalo y te aviso"
            + (" por Windows y Telegram." if tg else ".")
            + (" El puente de Telegram vuelve solo." if bridge else ""))


# ---------- CHANGELOG ----------
def changelog_section(text: str, version: str) -> str:
    """El texto de una versión en el CHANGELOG (sin su título)."""
    m = re.search(rf"^## v{re.escape(version)}\b.*?\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1).strip() if m else ""


def roll_changelog(text: str, version: str, today: date | None = None) -> str:
    """Convierte «Sin publicar» en la versión nueva y deja «Sin publicar» vacío encima."""
    m = re.search(rf"^{UNRELEASED}\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m or not m.group(1).strip():
        raise VersionError("el CHANGELOG no tiene nada en «Sin publicar»: escribe qué cambia")
    day = (today or date.today()).isoformat()
    head = f"{UNRELEASED}\n\n## v{version} — {day}\n\n{m.group(1).strip()}\n\n"
    return text[:m.start()] + head + text[m.end():]
