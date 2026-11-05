# Implementation Plan: Takeover

**Branch**: `017-takeover` | **Spec**: [spec.md](spec.md)

## Summary

`service.open_workspace(ctx, n)`: resuelve el editor (`[editor] command`, `$VISUAL`, `$EDITOR`,
`code`), lo lanza sobre `run.worktree` con `process.background_kwargs()` y registra
`takeover.opened`. `service.resume_human(ctx, n, message)`: `git.commit_all` («humano: …»),
intento `stage=build, profile=takeover, agent=human`, `commands.run_registered("test")` como
evidencia (`evidence.tests`), `head_sha` al nuevo commit, evento `takeover.done` y
`retry(from_=siguiente a build)`; con tests en rojo, `OpError` con la salida. CLI `umbra open`
y `umbra done -m`; `watch` tecla `o` (abre; si ya se abrió desde el último reintento, pide el
mensaje y retoma). `explain.AGENTS["human"] = "tú"`, narración de ambos eventos y acción
«Abrirla en tu editor» en los bloqueos.

## Constitution Check

III (la persona decide y su cambio queda como evidencia) · VI (nada avanza sin tests: el
retome corre `test` antes de encolar) · VII (sin cambios: la aprobación sigue siendo humana y
explícita). Sin enmienda.

## Pruebas

`tests/acceptance/test_takeover.py` con un editor falso (script que anota la ruta) y el
constructor falso en modo `broken`; una prueba Pilot de la tecla `o`.
