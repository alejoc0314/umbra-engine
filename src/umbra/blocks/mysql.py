"""MySQL local: consultas de solo lectura y cambios (que solo aplica la persona, ver `service`).

La conexión sale de `[mysql]` (host, port, user, password_env, database) en `.umbra/local.toml`
o `~/.umbra/local.toml`; por defecto, el root sin contraseña de 127.0.0.1:3306 (Laragon/XAMPP).
"""

import os
import re

MAX_ROWS = 200
READ_ONLY = ("select", "show", "describe", "desc", "explain", "with")
_COMMENTS = re.compile(r"(/\*.*?\*/|--[^\n]*|#[^\n]*)", re.S)


class MySQLError(Exception):
    pass


def check_read_only(sql: str) -> str:
    """La consulta, si es de lectura; si no, MySQLError. La transacción READ ONLY de `query`
    frena además cualquier escritura que se cuele (p. ej. un WITH … UPDATE)."""
    clean = _COMMENTS.sub(" ", sql).strip().rstrip(";").strip()
    first = clean.split(None, 1)[0].lower() if clean else ""
    if first not in READ_ONLY:
        raise MySQLError("solo se consulta sin permiso (SELECT, SHOW, DESCRIBE, EXPLAIN); "
                         "para cambiar datos propón el cambio: `umbra db change`")
    if re.search(r"\binto\s+(outfile|dumpfile)\b", clean, re.I):
        raise MySQLError("una consulta no escribe archivos (INTO OUTFILE/DUMPFILE)")
    return clean


def _connect(config: dict, database: str | None, multi: bool = False):
    try:
        import pymysql
        from pymysql.constants import CLIENT
    except ImportError as e:  # pragma: no cover - es dependencia de umbra
        raise MySQLError("falta pymysql: reinstala umbra") from e
    c = config.get("mysql") or {}
    try:
        return pymysql.connect(
            host=c.get("host", "127.0.0.1"), port=int(c.get("port", 3306)),
            user=c.get("user", "root"),
            password=os.environ.get(c["password_env"], "") if c.get("password_env") else "",
            database=database or c.get("database") or None, charset="utf8mb4",
            connect_timeout=10, autocommit=False,
            client_flag=CLIENT.MULTI_STATEMENTS if multi else 0)
    except pymysql.MySQLError as e:
        raise MySQLError(f"no pude conectar con MySQL ({e}); revisa que esté encendido y la "
                         "sección [mysql] de ~/.umbra/local.toml") from e


def query(config: dict, sql: str, database: str | None = None) -> dict:
    """Una consulta en una transacción de solo lectura: {columns, rows, truncated}."""
    import pymysql
    sql = check_read_only(sql)
    conn = _connect(config, database)
    try:
        with conn.cursor() as cur:
            cur.execute("START TRANSACTION READ ONLY")
            cur.execute(sql)  # sin MULTI_STATEMENTS: «SELECT 1; DROP …» lo rechaza el servidor
            columns = [d[0] for d in cur.description or []]
            rows = cur.fetchmany(MAX_ROWS + 1)
            conn.rollback()
    except pymysql.MySQLError as e:
        raise MySQLError(str(e)) from e
    finally:
        conn.close()
    return {"columns": columns, "truncated": len(rows) > MAX_ROWS,
            "rows": [["NULL" if v is None else str(v) for v in r] for r in rows[:MAX_ROWS]]}


def execute(config: dict, sql: str, database: str | None = None) -> int:
    """Aplica un cambio (puede ser varias sentencias) en una transacción; filas afectadas."""
    import pymysql
    conn = _connect(config, database, multi=True)
    try:
        with conn.cursor() as cur:
            affected = max(cur.execute(sql), 0)
            while cur.nextset():
                affected += max(cur.rowcount, 0)
        conn.commit()
    except pymysql.MySQLError as e:
        conn.rollback()
        raise MySQLError(str(e)) from e
    finally:
        conn.close()
    return affected
