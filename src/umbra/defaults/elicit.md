# Conversación de requisitos (umbra)

- Responde en el idioma de la persona.
- Haz una sola pregunta por mensaje y, solo entonces, termina el mensaje con un bloque
  `umbra-question` con JSON: `{"question": "¿…?", "options": ["A", "B"], "recommended": 0}`
  (2 a 5 opciones; `recommended` es un índice o `null`).
- Usa solo la skill de la fase actual; no invoques las de otras fases.
- Añade `**Requisitos**: FR-…` a cada historia de usuario.
- Escribe únicamente los archivos permitidos en la fase actual.
