"""Agente `script` de ejemplo para umbra-engine.

Lee por stdin el JSON de umbra ({"envelope", "profile", "instructions", "output_schema",
"allowed_commands"}) y escribe por stdout {"output": {...}} con el contrato de etapa.
Marca como hallazgo `medium` cada línea añadida que contenga TODO o FIXME.
"""

import json
import re
import sys

payload = json.loads(sys.stdin.read())
diff = payload["envelope"].get("diff") or ""

findings, current_file, line_no = [], None, 0
for line in diff.splitlines():
    if line.startswith("+++ "):
        current_file = line[6:] if line.startswith("+++ b/") else None
    elif line.startswith("@@"):
        line_no = int(re.search(r"\+(\d+)", line).group(1)) - 1
    elif line.startswith("+"):
        line_no += 1
        if re.search(r"\b(TODO|FIXME)\b", line):
            findings.append({"severity": "medium", "file": current_file, "line": line_no,
                             "rule": "todo-added",
                             "message": f"pendiente añadido: {line[1:].strip()}"})
    elif not line.startswith("-"):
        line_no += 1

summary = f"{len(findings)} pendientes añadidos" if findings else "sin pendientes añadidos"
print(json.dumps({"output": {"status": "done", "summary": summary, "findings": findings,
                             "questions": []}, "cost": 0}))
