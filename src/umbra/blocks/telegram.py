"""Decidir desde el teléfono: avisos con botones por Telegram y lectura de las respuestas.

Solo librería estándar (urllib). El token nunca se guarda: vive en una variable de entorno
(`[notify.telegram] token_env`). Nada de aquí frena una ejecución: si Telegram no responde, el
aviso se pierde y el registro lo cuenta.
"""

import html
import json
import os
import re
import urllib.error
import urllib.request
import uuid
from pathlib import Path

DEFAULT_API = "https://api.telegram.org"
SEND_TIMEOUT_S = 10
UPLOAD_TIMEOUT_S = 60
POLL_TIMEOUT_S = 25


def settings(config: dict) -> dict | None:
    """`{token, chat_id}` si el proyecto configuró Telegram y el token está en el entorno."""
    tg = config.get("notify", {}).get("telegram") or {}
    token = os.environ.get(tg.get("token_env") or "UMBRA_TELEGRAM_TOKEN")
    chat_id = tg.get("chat_id")
    if not tg or not token or chat_id is None:
        return None
    return {"token": token, "chat_id": str(chat_id)}


def target(config: dict) -> dict | None:
    """A quién avisar desde fuera de umbra (el script de actualización): el nombre de la
    variable del token y el chat, nunca el token."""
    tg = config.get("notify", {}).get("telegram") or {}
    if not settings(config):
        return None
    return {"token_env": tg.get("token_env") or "UMBRA_TELEGRAM_TOKEN",
            "chat_id": str(tg["chat_id"])}


def call(token: str, method: str, params: dict, wait: float = SEND_TIMEOUT_S) -> dict | list | None:
    """Una llamada a la API de bots; None si falló (sin excepciones hacia fuera)."""
    base = os.environ.get("UMBRA_TELEGRAM_API", DEFAULT_API).rstrip("/")
    req = urllib.request.Request(f"{base}/bot{token}/{method}",
                                 data=json.dumps(params).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=wait) as resp:  # noqa: S310 (https fijo)
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None
    return data.get("result") if isinstance(data, dict) and data.get("ok") else None


_MD = re.compile(r"(```.*?```|`[^`\n]+`|\*\*[^*\n]+\*\*|^#{1,6} [^\n]+|^[ \t]*[-*] )",
                 re.M | re.S)


def to_html(text: str) -> str | None:
    """Markdown ligero (lo que devuelve `umbra chat`) → HTML de Telegram. None si no hay nada
    que formatear: entonces conviene mandar texto plano."""
    if not _MD.search(text):
        return None
    out, pos = [], 0
    for m in _MD.finditer(text):
        out.append(html.escape(text[pos:m.start()]))
        tok = m.group(0)
        if tok.startswith("```"):
            body = tok[3:-3]
            if "\n" in body:
                body = body.split("\n", 1)[1]  # sin el nombre del lenguaje
            out.append(f"<pre>{html.escape(body.strip(chr(10)))}</pre>")
        elif tok.startswith("`"):
            out.append(f"<code>{html.escape(tok[1:-1])}</code>")
        elif tok.startswith("**"):
            out.append(f"<b>{html.escape(tok[2:-2])}</b>")
        elif tok.startswith("#"):
            out.append(f"<b>{html.escape(tok.lstrip('#').strip())}</b>")
        else:  # viñeta
            out.append(tok.replace("-", "•").replace("*", "•"))
        pos = m.end()
    out.append(html.escape(text[pos:]))
    return "".join(out)


def send(tg: dict, text: str, buttons: list[list[tuple[str, str]]] | None = None) -> int | None:
    """Envía un mensaje (con botones en línea opcionales); devuelve el message_id o None.

    El Markdown ligero se manda como HTML; si Telegram lo rechaza, va en texto plano."""
    params = {"chat_id": tg["chat_id"], "text": text[:4000]}
    if buttons:
        params["reply_markup"] = {"inline_keyboard": [
            [{"text": label, "callback_data": data[:64]} for label, data in row]
            for row in buttons]}
    result = None
    if (rich := to_html(text[:4000])) and len(rich) <= 4096:
        result = call(tg["token"], "sendMessage", {**params, "text": rich, "parse_mode": "HTML"})
    if not isinstance(result, dict):
        result = call(tg["token"], "sendMessage", params)
    return result.get("message_id") if isinstance(result, dict) else None


def _multipart(fields: dict, files: list[tuple[str, Path]]) -> tuple[bytes, str]:
    boundary = "umbra" + uuid.uuid4().hex
    body = bytearray()
    for k, v in fields.items():
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n"
                 f"{v}\r\n").encode()
    for name, path in files:
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; "
                 f"filename=\"{path.name}\"\r\nContent-Type: application/octet-stream\r\n\r\n"
                 ).encode() + path.read_bytes() + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def upload(token: str, method: str, fields: dict, files: list[tuple[str, Path]],
           wait: float = UPLOAD_TIMEOUT_S) -> dict | list | None:
    """Como `call`, pero con archivos (multipart)."""
    base = os.environ.get("UMBRA_TELEGRAM_API", DEFAULT_API).rstrip("/")
    body, ctype = _multipart(fields, files)
    req = urllib.request.Request(f"{base}/bot{token}/{method}", data=body,
                                 headers={"Content-Type": ctype}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=wait) as resp:  # noqa: S310 (https fijo)
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None
    return data.get("result") if isinstance(data, dict) and data.get("ok") else None


def send_photos(tg: dict, paths: list, caption: str = "") -> bool:
    """Hasta diez capturas en un álbum (o una sola foto); False si no se pudo."""
    files = [Path(p) for p in paths if Path(p).is_file()][:10]
    if not files:
        return False
    if len(files) == 1:
        result = upload(tg["token"], "sendPhoto",
                        {"chat_id": tg["chat_id"], "caption": caption[:1000]},
                        [("photo", files[0])])
        return isinstance(result, dict)
    media = [{"type": "photo", "media": f"attach://f{i}",
              **({"caption": caption[:1000]} if i == 0 and caption else {})}
             for i in range(len(files))]
    result = upload(tg["token"], "sendMediaGroup",
                    {"chat_id": tg["chat_id"], "media": json.dumps(media)},
                    [(f"f{i}", f) for i, f in enumerate(files)])
    return isinstance(result, list)


def send_document(tg: dict, path, caption: str = "") -> bool:
    path = Path(path)
    if not path.is_file():
        return False
    result = upload(tg["token"], "sendDocument",
                    {"chat_id": tg["chat_id"], "caption": caption[:1000]},
                    [("document", path)])
    return isinstance(result, dict)


def set_commands(tg: dict, commands: list[tuple[str, str]]) -> None:
    """El menú de comandos del bot (lo que Telegram muestra al escribir «/»)."""
    call(tg["token"], "setMyCommands",
         {"commands": [{"command": c, "description": d[:256]} for c, d in commands]})


def deliver(config: dict, text: str, photos: list) -> None:
    """Una tarea lista: el informe y, si las hay, las capturas del navegador."""
    tg = settings(config)
    if not tg:
        return
    send(tg, text)
    if photos:
        send_photos(tg, photos, "Lo que se vio en el navegador")


def updates(tg: dict, offset: int, timeout: float = POLL_TIMEOUT_S) -> list[dict]:
    """Long polling: espera hasta `timeout` s a que llegue algo; [] si nada o si falló."""
    result = call(tg["token"], "getUpdates",
                  {"offset": offset, "timeout": int(timeout),
                   "allowed_updates": ["message", "callback_query"]}, wait=timeout + 5)
    return result if isinstance(result, list) else []


def ack(tg: dict, callback_id: str, text: str = "") -> None:
    call(tg["token"], "answerCallbackQuery", {"callback_query_id": callback_id,
                                              "text": text[:200]})


def clear_buttons(tg: dict, message_id: int) -> None:
    """Quita los botones de un mensaje ya atendido (evita pulsarlos dos veces)."""
    call(tg["token"], "editMessageReplyMarkup",
         {"chat_id": tg["chat_id"], "message_id": message_id,
          "reply_markup": {"inline_keyboard": []}})


# ---------- qué se envía en cada transición ----------
def decision_message(run, type_: str, payload: dict, project: str = ""
                     ) -> tuple[str, list[list[tuple[str, str]]]]:
    """Texto y botones para una tarea que necesita a la persona. `run` trae number y title;
    `project` (nombre del repo) viaja en el texto y en cada botón: un solo bot para todos."""
    n, title = run["number"], run["title"]
    where = f"umbra · {project} · " if project else "umbra · "
    head = f"{where}tarea #{n} {title}\n"
    at = f"@{project}" if project else ""
    code, details = payload.get("code"), payload.get("details") or {}
    if type_ == "run.waiting_approval":
        return (head + "Espera tu aprobación: tests, revisión y verificación en verde.",
                [[("✅ Integrar", f"approve:{n}{at}"), ("❌ Rechazar", f"reject:{n}{at}")],
                 [("🔍 Ver cambios", f"diff:{n}{at}")]])
    reason = payload.get("reason") or ("falló" if type_ == "run.failed" else "se detuvo")
    text = head + f"Se detuvo: {reason}"
    if code == "policy":
        paths = sorted({v["path"] for v in details.get("violations", []) if v.get("path")})
        return (text, [[("🔓 Autorizar " + ", ".join(paths)[:40], f"allow:{n}{at}")],
                       [("🔁 Reintentar", f"retry:{n}{at}"), ("🆕 De cero", f"new:{n}{at}")]])
    if code == "agent_questions":
        qs = "\n".join(f"• {q}" for q in details.get("questions", []))
        return (text + f"\nEl agente pregunta:\n{qs}\n\nResponde a este mensaje con tu respuesta.",
                [[("🔁 Reintentar", f"retry:{n}{at}")]])
    if code == "design_review":
        summary = details.get("summary") or ""
        pending = details.get("pending") or []
        return (head + "El diseño espera tu visto bueno (las pantallas van en las fotos)."
                + (f"\n{summary}" if summary else "")
                + ("\n\nEl crítico todavía ve:\n" + "\n".join(f"• {p}" for p in pending[:5])
                   if pending else "")
                + "\n\nSi quieres cambios, responde a este mensaje diciendo cuáles.",
                [[("✅ Aprobar diseño", f"dok:{n}{at}")]])
    if code == "design_choice":
        options = details.get("options") or []
        return (head + f"Hay {len(options)} direcciones de diseño para elegir (van en las "
                "fotos). Elige una, o responde a este mensaje con lo que quieres en otra ronda.",
                [[(f"{i} · {o['name']}"[:40], f"dpick:{n}:{i}{at}")]
                 for i, o in enumerate(options, 1)])
    if code == "findings":
        return (text, [[("🚫 No aplica (todos)", f"waive:{n}{at}"),
                        ("🔁 Reintentar", f"retry:{n}{at}")],
                       [("🆕 De cero", f"new:{n}{at}")]])
    return (text, [[("🔁 Reintentar", f"retry:{n}{at}"), ("🆕 De cero", f"new:{n}{at}")]])


def spec_message(spec_dir: str, url: str, project: str = ""
                 ) -> tuple[str, list[list[tuple[str, str]]]]:
    name = spec_dir.split("/")[-1]
    head = f"umbra · {project} · spec {name}" if project else f"umbra · spec {name}"
    return (f"{head}\nTodas sus historias están integradas en su rama: espera tu "
            f"aprobación.\n{url}",
            [[("✅ Integrar la spec", f"spec:{name}" + (f"@{project}" if project else ""))]])


def notify_run(config: dict, run, type_: str, payload: dict, project: str = "") -> int | None:
    tg = settings(config)
    if not tg:
        return None
    text, buttons = decision_message(run, type_, payload, project)
    return send(tg, text, buttons)


def notify_spec(config: dict, spec_dir: str, url: str, project: str = "") -> int | None:
    tg = settings(config)
    if not tg:
        return None
    return send(tg, *spec_message(spec_dir, url, project))
