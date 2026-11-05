# Implementation Plan: `umbra new` con playbooks y `watch --all`

**Branch**: `021-umbra-new` | **Spec**: [spec.md](spec.md)

## Summary

`management/playbooks.py`: `available()` (umbra `defaults/playbooks/<stack>` y
`~/.umbra/playbooks/<stack>`, estos con prioridad), `load(stack)` (`playbook.toml`:
`scaffold`, `default_routine`, `[commands]`, `[files]`), `sync(url)` (clone/pull).
`service.new_project`: git init, andamiaje con `run_bounded`, copia de archivos,
`project.init_project(stack, commands, default_routine)`, primer commit, `gh.repo_create`
(`gh repo create --private --source . --push`), `context_build`, `spec_new` con `--idea`,
registro en `management/projects.py` (`~/.umbra/projects.json`, `overview()` con conteos por
repo). CLI `umbra new`, `umbra playbook list|sync`, `umbra projects`, `umbra watch --all`
(`ProjectsApp` elige el repo; `WatchApp(all_projects=True)` sale con «projects» al pulsar `P`
y la CLI vuelve a la lista). `_render_toml` acepta comandos como diccionario y cadenas con
comillas. Playbooks por defecto: `python` (uv), `node` (npm), `laravel` (composer, con `dev`).

## Constitution Check

I (todo por CLI; `watch --all` es la vista) · II (`umbra projects` es la sombra de la lista) ·
IX (sin credenciales: `gh` del usuario) · X (sin dependencias; los playbooks son archivos).

## Pruebas

`tests/acceptance/test_new_project.py`: playbook del equipo con andamiaje local (script de
Python), `gh repo create` falso (bare local), cartógrafo falso; `--no-remote --no-context`;
carpeta existente y stack desconocido; `playbook sync` desde un repo git local; `umbra
projects` y la pantalla de proyectos con Pilot.
