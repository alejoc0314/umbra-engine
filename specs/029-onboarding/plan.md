# Implementation Plan: Onboarding de proyectos ya iniciados

**Branch**: `029-onboarding` | **Spec**: [spec.md](spec.md)

## Summary

- `management/onboarding.py`: estado en `.umbra/artifacts/onboarding/estado.json` (fase, preguntas,
  respuestas, comentarios). Fases: `explorar` → `preguntas` → `redactar` → `revisar` → `hecho`.
  - `recon(root)`: detección sin modelo (archivos de stack, scripts de `package.json`/
    `composer.json`/`pyproject.toml`/`Makefile`/`artisan`, CI, docs, instrucciones para IA,
    `.env.example`, migraciones, líneas por lenguaje, historia de git) →
    `reconocimiento.md` (con los comandos que declara el proyecto).
  - `baseline(ctx)`: corre `test` y `lint` registrados (sin worker) → `linea-base.md`.
  - `explore(ctx)`: cinco agentes `explorer` (Sonnet, solo lectura) en hilos, cada uno con su
    foco en el sobre; cada nota se guarda como `<foco>.md`. Un fallo no detiene a los demás.
  - `ask(ctx)`: agente `onboarder` (Opus, lectura) con salida `OnboardQuestions`
    (`questions: list[Question]`, máx. 8).
  - `write(ctx, comment)`: `onboarder` con edición limitada a `CONTEXT.md`,
    `.specify/memory/constitution.md` y `specs/000-linea-base/**`; lo demás se restaura (como
    el cartógrafo).
  - `approve(ctx)`: commit «umbra: onboarding» de esos archivos (sin push).

- `routines/onboard_talk.py`: `OnboardTalk` (como `SpecTalk`): `start`, `option`, `text`, `decide`,
  con botones `oq:<i>|otra` y `or:approve|changes`.
- CLI `umbra onboard [--de-cero]` en la terminal (preguntas numeradas, revisión con
  confirmación); bridge: `/onboarding`, botones y texto, y la oferta tras `/adoptar`.
- Perfiles `explorer` y `onboarder` con sus instrucciones; contrato `OnboardQuestions`.

## Constitution Check

II (el onboarding es una conversación opcional; sus artefactos se pueden escribir a mano) ·
III (el agente redacta, la persona aprueba y el motor confirma) · V (agentes acotados en tiempo,
costo, workspace y acciones) · VI (la línea base es evidencia: comando, exit code y salida) ·
VII (nada se confirma sin aprobación explícita; no se hace push). Sin enmienda.

## Pruebas

`tests/acceptance/test_onboarding.py` con el `claude` falso (modos `explore`,
`onboard_questions`, `onboard_write`): recorrido por CLI y por Telegram, retomar, redactor que se
pasa de la raya, explorador que falla.
