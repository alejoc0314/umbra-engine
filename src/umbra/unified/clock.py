"""Horas para la persona: el almacén guarda UTC, la pantalla muestra la hora local."""

from datetime import UTC, datetime

MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def local(ts: str) -> datetime:
    """Marca ISO del almacén (UTC) → hora local de la máquina."""
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone()


def hhmm(ts: str) -> str:
    return local(ts).strftime("%H:%M")


def hhmmss(ts: str) -> str:
    return local(ts).strftime("%H:%M:%S")


def day_label(ts: str) -> str:
    """«4 nov» (con año si no es el actual)."""
    dt = local(ts)
    label = f"{dt.day} {MONTHS[dt.month - 1]}"
    return label if dt.year == datetime.now().astimezone().year else f"{label} {dt.year}"


def day_key(ts: str) -> str:
    return local(ts).strftime("%Y-%m-%d")


def duration(start: str | None, end: str | None) -> str:
    """Duración legible: 37s · 4m12s · 1h03m. Sin inicio: «-»."""
    if not start:
        return "-"
    end_dt = datetime.fromisoformat(end) if end else datetime.now(UTC)
    secs = max(0, int((end_dt - datetime.fromisoformat(start)).total_seconds()))
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m{secs % 60:02d}s"
    return f"{secs // 3600}h{(secs % 3600) // 60:02d}m"
