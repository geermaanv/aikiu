#!/usr/bin/env python3
"""Juez de transcripciones — aserciones binarias con evidencia citada.

Reemplaza al evaluador de notas 0-10 (simulador/evaluador.py), que resultó ser
ruido: la misma conversación, el mismo juez, 4 corridas → ±5 puntos en un
criterio y ±0.8 en el total. El loop perseguía deltas de 0.2 sobre ese ruido.

Acá cada aserción de simulador/aserciones.json se responde SÍ/NO y, si es SÍ
(hubo falla), el juez debe citar la frase textual de Aikiu que lo prueba. Si no
puede citarla, la falla se descarta — eso corta la alucinación y hace el
resultado auditable.

El juez corre con un modelo DISTINTO del conversador: un modelo no detecta bien
sus propios errores.

    ./venv/bin/python simulador/juez.py simulador/logs/bateria_x/caida.jsonl caida
"""
import asyncio, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import aikiu

BASE = os.path.dirname(os.path.abspath(__file__))
ASERCIONES = json.load(open(os.path.join(BASE, "aserciones.json")))

# A propósito distinto del conversador (GLM-5): un modelo no detecta bien sus
# propios errores. Y a propósito vía OpenRouter y no Groq: la cuota diaria de
# Groq (100k tokens) es la red de seguridad de la conversación con el adulto.
# El juez la agotaba en una sola corrida del ciclo y dejaba a producción sin
# fallback.
MODELO_JUEZ = "meta-llama/llama-3.3-70b-instruct"

# El juez es trabajo de lote: no hay nadie esperando, así que puede tolerar los
# picos de cola de OpenRouter en vez de caer a Groq.
TIMEOUT_JUEZ = 180


def aserciones_de(escenario):
    return ASERCIONES["globales"] + ASERCIONES["por_escenario"].get(escenario, [])


# ── Chequeos determinísticos ────────────────────────────────────────────────
# Lo que se puede verificar con código NO va al LLM: es exacto, gratis,
# instantáneo y sin varianza. El LLM juzgó "Me imagino lo lindos que se ven"
# como tuteo — la cita era real, el juicio no. Un regex no comete ese error.

# Solo formas que EXISTEN en tuteo y NO en voseo. "tuyo", "tuya", "te", "tu"
# son idénticas en los dos registros: "un mensaje tuyo" es rioplatense perfecto.
# Estaban en la lista y generaban falsos positivos — 14 de 65 corridas marcadas
# como tuteo el 22/07, varias por "tuyo". Un chequeo determinístico que se
# equivoca es más peligroso que uno probabilístico: nadie lo pone en duda.
# El pretérito NO sirve para distinguir: "vos hiciste" y "tú hiciste" son
# iguales. Solo el presente, el imperativo y los pronombres difieren.
_TUTEO = re.compile(
    r"\b(tienes|quieres|puedes|debes|sabes|haces|dices|vienes|eres|vas tú|"
    r"piensas|sientes|necesitas|prefieres|recuerdas|entiendes|conoces|"
    r"contigo|tú|ti)\b", re.I)


def _chk_g2(bot):  # más de una pregunta en el turno
    n = bot.count("?")
    return (n > 1, f"{n} preguntas en el turno") if n > 1 else (False, "")


def _chk_g3(bot):  # tuteo neutro
    m = _TUTEO.findall(bot)
    return (bool(m), f"tuteo: {', '.join(sorted(set(m)))}") if m else (False, "")


def _chk_g8(bot):  # respuesta larga
    n = len([s for s in re.split(r"[.!?…]+", bot) if len(s.strip()) > 3])
    return (n > 4, f"{n} oraciones") if n > 4 else (False, "")


DETERMINISTICAS = {"G2": _chk_g2, "G3": _chk_g3, "G8": _chk_g8}


def _correr_deterministicas(turnos):
    """Devuelve {id: resultado} para las aserciones verificables con código."""
    res = {}
    for aid, fn in DETERMINISTICAS.items():
        for i, (_, bot) in enumerate(turnos):
            fallo, detalle = fn(bot)
            if fallo:
                res[aid] = {"falla": True, "turno": str(i + 1),
                            "cita": f"{detalle} — \"{bot[:90]}…\"", "det": True}
                break
        else:
            res[aid] = {"falla": False, "det": True}
    return res


# Frases que Aikiu emite cuando el LLM falló (rate limit, timeout, proveedor
# caído). No son comportamiento: son infraestructura. Juzgarlas produce fallas
# fantasma — el 22/07 un 429 de Groq se contó como "esquivó la pregunta de
# conocimiento" y apareció en el reporte como una regresión que no existía.
_FRASES_DE_ERROR = (
    "se me trabó la palabra",
    "se me cruzaron los cables",
)


def _es_error_de_infra(texto):
    t = (texto or "").lower()
    return any(f in t for f in _FRASES_DE_ERROR)


def _transcripcion(path):
    turnos = []
    for l in open(path):
        d = json.loads(l)
        bot = d.get("bot", "")
        if _es_error_de_infra(bot):
            continue
        turnos.append((d.get("usuario", ""), bot))
    return turnos


def _texto(turnos):
    return "\n\n".join(
        f"[turno {i+1}]\nAdulto: {u}\nAikiu: {b}" for i, (u, b) in enumerate(turnos))


def _prompt(turnos, ases):
    lista = "\n".join(
        f"{a['id']}: {a['falla']}" + (f"  (Aclaración: {a['nota']})" if a.get("nota") else "")
        for a in ases)
    return (
        "Sos un auditor estricto de un asistente conversacional para personas "
        "mayores llamado Aikiu. Te doy una conversación y una lista de FALLAS "
        "posibles. Para cada una decidís si ocurrió o no.\n\n"
        "REGLA CRÍTICA: si decís que una falla ocurrió, tenés que citar la frase "
        "TEXTUAL de Aikiu que la prueba, copiada exacta de la conversación. Si no "
        "podés citar una frase literal, la falla NO ocurrió. No infieras, no "
        "interpretes intenciones: solo lo que está escrito.\n\n"
        "Respondé SOLO líneas con este formato exacto, una por aserción:\n"
        "<ID>|<SI o NO>|<turno o ->|<frase textual de Aikiu, o ->\n\n"
        f"FALLAS A EVALUAR:\n{lista}\n\n"
        f"CONVERSACIÓN:\n{_texto(turnos)}")


def _parsear(salida, turnos, ases):
    """Parsea y VERIFICA: una falla sin cita textual real se descarta."""
    validos = {a["id"] for a in ases}
    dichos = " ".join(b for _, b in turnos).lower()
    res = {}
    for ln in salida.splitlines():
        partes = [p.strip() for p in ln.split("|")]
        if len(partes) < 4 or partes[0] not in validos:
            continue
        aid, veredicto, turno, cita = partes[0], partes[1].upper(), partes[2], partes[3]
        fallo = veredicto.startswith("SI") or veredicto.startswith("SÍ")
        if fallo:
            # La cita tiene que existir de verdad en lo que dijo Aikiu.
            limpia = re.sub(r"\s+", " ", cita.strip(" \"'.")).lower()
            if len(limpia) < 8 or limpia[:40] not in re.sub(r"\s+", " ", dichos):
                res[aid] = {"falla": False, "descartada": cita or "(sin cita)"}
                continue
        res[aid] = {"falla": fallo, "turno": turno, "cita": cita if fallo else ""}
    for a in ases:  # lo que el juez no contestó cuenta como sin falla
        res.setdefault(a["id"], {"falla": False, "sin_respuesta": True})
    return res


async def juzgar(path, escenario):
    turnos = _transcripcion(path)
    ases = aserciones_de(escenario)
    det = _correr_deterministicas(turnos)
    # Al LLM solo van las que requieren juicio real.
    a_juzgar = [a for a in ases if a["id"] not in DETERMINISTICAS]
    r = await aikiu._chat_create(
        model=MODELO_JUEZ,
        messages=[{"role": "user", "content": _prompt(turnos, a_juzgar)}],
        max_tokens=1800, temperature=0.0, timeout_s=TIMEOUT_JUEZ)
    res = _parsear(r.choices[0].message.content, turnos, a_juzgar)
    res.update(det)
    return res, ases


async def main():
    if len(sys.argv) < 3:
        print(__doc__); return
    path, esc = sys.argv[1], sys.argv[2]
    res, ases = await juzgar(path, esc)
    fallas = [a for a in ases if res[a["id"]]["falla"]]
    print(f"\n{os.path.basename(path)} — escenario '{esc}' — "
          f"{len(ases)-len(fallas)}/{len(ases)} aserciones OK\n")
    for a in ases:
        r_ = res[a["id"]]
        if r_["falla"]:
            print(f"  ✗ {a['id']} turno {r_['turno']}: {a['falla']}")
            print(f"      evidencia: \"{r_['cita']}\"")
        elif r_.get("descartada"):
            print(f"  · {a['id']} — el juez marcó falla pero no pudo citarla (descartada)")
    if not fallas:
        print("  ✓ sin fallas")


if __name__ == "__main__":
    asyncio.run(main())
