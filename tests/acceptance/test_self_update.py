"""Actualizar sin romper nada, también desde el teléfono (spec 025)."""

import os

from tests.acceptance.test_telegram import poll
from umbra import __version__
from umbra.routines import bridge
from umbra.unified import version


def test_update_from_the_phone_stops_the_bridge_and_relaunches_it(env, tg, monkeypatch):
    calls = []
    monkeypatch.setattr(version, "latest", lambda repo=version.REPO: "99.0.0")
    monkeypatch.setattr(version, "notes", lambda v, repo=version.REPO: "- algo nuevo")
    monkeypatch.setattr(version, "install", lambda *a: calls.append(a) or "lanzado.")
    bridge._beat(env.root)  # este proceso es el puente
    tg.say("/actualizar")
    poll(env, tg)
    latest, previous, held, target = calls[0]
    assert latest == "99.0.0" and held == {"pid": os.getpid(), "root": env.root.as_posix()}
    assert target and "token" not in target and target["chat_id"]  # sin el token
    assert not bridge.alive()  # el puente se detiene; el script lo relanza al terminar
    text = tg.sent[-1]["text"]
    assert f"de v{__version__} a v99.0.0" in text and "algo nuevo" in text


def test_update_from_the_phone_when_already_on_the_latest(env, tg, monkeypatch):
    monkeypatch.setattr(version, "latest", lambda repo=version.REPO: __version__)
    monkeypatch.setattr(version, "install", lambda *a: (_ for _ in ()).throw(AssertionError))
    tg.say("/actualizar")
    poll(env, tg)
    assert f"Ya estás en v{__version__}" in tg.sent[-1]["text"]
