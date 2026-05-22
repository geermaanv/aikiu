"""
Andromarta — humanoide sintético que conversa con Aikiu como si fuera una adulta mayor real.

Vive en una cuenta de Telegram propia (no es un bot: usa MTProto vía Telethon).
Le habla a @aikiu_bot desde el celular sintético; vos observás la conversación
abriendo Telegram con esa misma cuenta en el celular o en Telegram Desktop.

Submódulos:
- persona: perfil base + system prompt
- estado: ánimo, energía, eventos del día (evoluciona con las horas)
- memoria: historial de la conversación, persistido en disco
- generador: arma el prompt y llama a Groq para producir el próximo mensaje
- scheduler: iniciativa proactiva (Andromarta arranca conversaciones sola)
"""
