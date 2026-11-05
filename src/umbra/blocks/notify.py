"""Avisos del sistema cuando umbra necesita a la persona (Windows, macOS y Linux).

Nunca frenan nada: si el aviso no se puede mostrar, se ignora.
"""

import html
import json
import os
import shutil
import subprocess
import sys

from umbra.blocks.process import background_kwargs

# AppID de PowerShell: Windows muestra el aviso sin registrar una aplicación propia
_PS_APP = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
_PS_TOAST = """
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml('{xml}')
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{app}').Show([Windows.UI.Notifications.ToastNotification]::new($xml))
"""  # noqa: E501


def toast_script(title: str, body: str) -> str:
    """Código PowerShell que muestra un aviso de Windows."""
    xml = ('<toast><visual><binding template="ToastGeneric">'
           f"<text>{html.escape(title)}</text><text>{html.escape(body)}</text>"
           "</binding></visual></toast>").replace("'", "''")  # comilla simple de PowerShell
    return _PS_TOAST.format(xml=xml, app=_PS_APP)


def command(title: str, body: str, platform: str = sys.platform) -> list[str] | None:
    if platform == "win32":
        return ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                toast_script(title, body)]
    if platform == "darwin":
        return ["osascript", "-e",
                f"display notification {json.dumps(body)} with title {json.dumps(title)}"]
    if shutil.which("notify-send"):
        return ["notify-send", title, body]
    return None


def watch_open(conn) -> bool:
    """Hay un `umbra watch` abierto (renueva su lease) que ya avisa en pantalla."""
    from umbra.blocks.lease import _ts
    return conn.execute("SELECT 1 FROM lease WHERE name LIKE 'watch:%' AND expires_at > ?",
                        (_ts(),)).fetchone() is not None


def send(title: str, body: str) -> None:
    # bajo pytest jamás: una suite en paralelo abría decenas de PowerShell a la vez
    if "PYTEST_CURRENT_TEST" in os.environ or os.environ.get("UMBRA_NO_NOTIFY"):
        return
    cmd = command(title, body)
    if not cmd:
        return
    try:
        subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, **background_kwargs())
    except OSError:
        pass
