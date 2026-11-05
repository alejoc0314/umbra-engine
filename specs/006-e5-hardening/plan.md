# Implementation Plan: E5 — Endurecimiento y vista en vivo

**Branch**: `006-e5-hardening` | **Date**: 2026-10-29 | **Spec**: [spec.md](spec.md)

## Summary

Etapa determinista `scan` (secretos con patrones + comandos SAST registrados), aislamiento
Docker para comandos registrados, guardia de configuración de agentes del repo, `umbra metrics`
calculado desde eventos e intentos, `umbra watch` con Textual y `docs/usage.md`.

## Research (decisiones)

| Tema | Decisión |
| --- | --- |
| Secretos | Patrones sobre líneas añadidas del diff: claves privadas PEM, AWS `AKIA…`, GitHub `gh[pousr]_…`, Slack `xox[baprs]-…`, Anthropic `sk-ant-…`, OpenAI `sk-…`(≥32), Google `AIza…`. Hallazgo `critical`, bloqueo sin retrabajo |
| SAST | `[scan] commands = ["sast"]` → nombres de comandos registrados; exit ≠ 0 → hallazgo `high` con la cola de la salida → retrabajo |
| Docker | `docker run --rm --network none -v <wt>:/work -w /work --cpus 2 --memory 2g --pids-limit 512 <image> sh -c "<cmd>"`, configurable en `[blocks]` |
| Guardia | `.claude/settings.json`, `.claude/settings.local.json`, `.mcp.json` en la raíz |
| Métricas | Tiempo hasta PR = `run.queued` → `pr.opened`; hasta merge = → `run.succeeded`; ciclos = intentos de BUILD − 1; aceptación inicial = SUCCEEDED sin `stage.rework` ni BUILD repetido |
| Vista | Textual: `DataTable` de tareas, `DataTable` de intentos y `RichLog` de eventos; refresco cada 1 s; `q` sale |

## Constitution Check

VI y VII: un secreto bloquea siempre y el agente no puede excluirlo. IX: Docker para código del
repo. X: Textual era la dependencia ya prevista en la constitución. Sin violaciones.
