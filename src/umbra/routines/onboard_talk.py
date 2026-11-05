"""La conversación del onboarding, para la terminal y para Telegram.

`say(text, buttons=None)` es cómo habla con la persona; los botones llevan `oq:<i>` (opción),
`oq:otra` y `or:approve|changes`. `pending` dice qué espera: una respuesta a la pregunta `i`
(«question»/«other»), la revisión («review») o el texto de los cambios («changes»)."""

from pathlib import Path

from umbra import service
from umbra.management import design_systems as ds
from umbra.management import onboarding as ob
from umbra.unified.events import add_event


class OnboardTalk:
    def __init__(self, root: Path, origin: str = "cli"):
        self.root, self.origin = root, origin
        self.pending: tuple | None = None
        self.busy = False
        self.done = False

    # --- recorrido ---
    @classmethod
    def start(cls, root: Path, say, origin: str = "cli", fresh: bool = False) -> "OnboardTalk":
        talk = cls(root, origin)
        ctx = service.load(root)
        if ctx.members:  # ponytail: el onboarding estudia un repo; en un espacio, aún no
            ctx.conn.close()
            raise ob.OnboardingError(
                "el onboarding aún no funciona en un espacio de trabajo: hazlo en cada repo "
                "antes de unirlo al espacio")
        try:
            if fresh:
                ob.reset(ctx.udir)
            st = ob.state(ctx.udir)
            if st["phase"] == "explorar":
                add_event(ctx.conn, None, "onboarding.started", origin)
        finally:
            ctx.conn.close()
        talk.advance(say)
        return talk

    def advance(self, say) -> None:
        """Hace lo que toque según la fase guardada, hasta necesitar a la persona."""
        ctx = service.load(self.root)
        try:
            st = ob.state(ctx.udir)
            if st["phase"] == "explorar":
                say("Estudio el proyecto: reconocimiento y línea base de tests (sin modelo); "
                    "después cinco exploradores en paralelo. Tarda unos minutos.")
                ob.folder(ctx.udir).mkdir(parents=True, exist_ok=True)
                (ob.folder(ctx.udir) / "reconocimiento.md").write_text(ob.recon(ctx.root),
                                                                        encoding="utf-8")
                (ob.folder(ctx.udir) / "linea-base.md").write_text(
                    ob.baseline(ctx.conn, ctx.root, ctx.udir, ctx.config), encoding="utf-8")
                status = ob.explore(ctx.conn, ctx.root, ctx.udir, self.origin)
                failed = {f: e for f, e in status.items() if e != "ok"}
                say("Exploración lista: " + ", ".join(f for f, e in status.items() if e == "ok")
                    + (". Fallaron: " + "; ".join(f"{f} ({e})" for f, e in failed.items())
                       if failed else "."))
                st["phase"] = "preguntar"  # retomar no repite la exploración
                ob.save(ctx.udir, st)
            if st["phase"] == "preguntar":
                st["questions"] = ob.ask(ctx.conn, ctx.root, ctx.udir, st)
                if ds.needs_choice(ctx.config):  # el sistema de diseño, primero
                    options = ds.choices()
                    st["questions"].insert(0, {
                        "question": "¿Qué sistema de diseño usa este proyecto?",
                        "options": [label for _, label in options], "recommended": None,
                        "system": [key for key, _ in options]})
                st["answers"], st["phase"] = [], "preguntas"
                ob.save(ctx.udir, st)
            if st["phase"] == "preguntas":
                i = len(st["answers"])
                if i < len(st["questions"]):
                    return self.ask(st["questions"][i], i, len(st["questions"]), say)
                st["phase"] = "redactar"
                ob.save(ctx.udir, st)
            if st["phase"] == "redactar":
                say("Redacto CONTEXT.md, la constitución del proyecto y el inventario.")
                summary = ob.write(ctx.conn, ctx.root, ctx.udir, st, self.origin)
                st["phase"], st["summary"] = "revisar", summary
                ob.save(ctx.udir, st)
            if st["phase"] == "revisar":
                return self.review(st, say)
            say("El onboarding de este proyecto ya está hecho. «de cero» lo repite.")
            self.done = True
        finally:
            ctx.conn.close()

    def ask(self, q: dict, i: int, total: int, say) -> None:
        self.pending = ("question", i)
        rec = q.get("recommended")
        order = sorted(range(len(q["options"])), key=lambda k: k != rec)
        buttons = [[(q["options"][k] + (" (recomendada)" if k == rec else ""), f"oq:{k}")]
                   for k in order]
        buttons.append([("Otra respuesta…", "oq:otra")])
        say(f"Pregunta {i + 1} de {total}: {q['question']}", buttons)

    def review(self, st: dict, say) -> None:
        self.pending = ("review",)
        files = ob.written(self.root)
        say("Revisa lo que entendí antes de que quede en el repo:\n"
            + "\n".join(f"• {f}" for f in files)
            + (f"\n\n{st['summary']}" if st.get("summary") else "")
            + "\n\n¿Lo apruebas?",
            [[("✅ Aprobar", "or:approve"), ("✏️ Pedir cambios", "or:changes")]])

    # --- lo que dice la persona ---
    def option(self, which: str, say) -> None:
        if not self.pending or self.pending[0] != "question":
            return say("No hay una pregunta pendiente.")
        if which == "otra":
            self.pending = ("other", self.pending[1])
            return say("Escribe tu respuesta.")
        ctx = service.load(self.root)
        try:
            st = ob.state(ctx.udir)
            try:
                answer = st["questions"][self.pending[1]]["options"][int(which)]
            except (ValueError, IndexError):
                return say("Esa opción no existe.")
        finally:
            ctx.conn.close()
        self.answer(answer, say)

    def answer(self, text: str, say) -> None:
        ctx = service.load(self.root)
        try:
            st = ob.state(ctx.udir)
            q = st["questions"][len(st["answers"])] if len(st["answers"]) < len(
                st["questions"]) else {}
            if q.get("system") and text in q["options"]:
                ds.set_system(ctx.root, q["system"][q["options"].index(text)])
            st["answers"].append(text)
            ob.save(ctx.udir, st)
        finally:
            ctx.conn.close()
        say(f"Tú: {text}")
        self.pending = None
        self.advance(say)

    def decide(self, choice: str, say) -> None:
        if self.pending != ("review",):
            return say("No hay nada que revisar ahora.")
        if choice == "changes":
            self.pending = ("changes",)
            return say("¿Qué cambio? Escríbelo en un mensaje.")
        if choice != "approve":
            return say("No entiendo esa decisión.")
        ctx = service.load(self.root)
        try:
            sha = ob.approve(ctx.conn, ctx.root, self.origin)
            st = ob.state(ctx.udir)
            st["phase"] = "hecho"
            ob.save(ctx.udir, st)
        finally:
            ctx.conn.close()
        self.pending, self.done = None, True
        say("Aprobado: el onboarding quedó en el repo"
            + (f" (commit {sha[:10]})" if sha else "") + ". Desde ahora los agentes trabajan "
            "con ese contexto y esa constitución."
            + ("\n\n¿Replico también el diseño actual de la app para poder referenciar sus "
               "vistas? `umbra design replicar` o /replicar."
               if (self.root / "specs" / "000-linea-base" / "vistas.md").is_file() else ""))

    def text(self, text: str, say) -> None:
        kind = (self.pending or ("",))[0]
        if kind in ("question", "other"):
            return self.answer(text, say)
        if kind in ("review", "changes"):
            ctx = service.load(self.root)
            try:
                st = ob.state(ctx.udir)
                st["comments"] = [*st.get("comments", []), text]
                st["phase"] = "redactar"
                ob.save(ctx.udir, st)
            finally:
                ctx.conn.close()
            say(f"Tú: {text}")
            self.pending = None
            return self.advance(say)
        say("Ahora no espero nada; «/onboarding» retoma donde quedó.")
