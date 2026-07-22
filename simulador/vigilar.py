#!/usr/bin/env python3
"""Vigía del ciclo — corre de fondo y mantiene vivo el veredicto del gate.

    ./venv/bin/python simulador/vigilar.py                 # arranca
    ./venv/bin/python simulador/vigilar.py --avisar        # + aviso por Telegram
    caffeinate -i ./venv/bin/python simulador/vigilar.py   # sin que duerma la Mac

DOS MODOS, y la diferencia importa:

  · DISPARADO POR CAMBIO (el que sirve). Vigila aikiu_core.md, aikiu.py,
    escenarios.json y aserciones.json. Cuando tocás una regla, corre el ciclo
    completo del nivel actual y todos los anteriores. Es el equivalente
    conversacional de un test runner en watch mode: te enterás en minutos si el
    arreglo funcionó y si rompió algo viejo.

  · CAZA DE INTERMITENTES (el de relleno). Si nada cambió, sigue acumulando
    repeticiones del nivel actual. Sirve para las fallas raras: S-BUS2 aparecía
    2/2, pero G2 y G6 aparecían 1 de cada 4 — con una sola corrida se te
    escapan. Tiene rendimiento decreciente: la corrida 50 sobre código idéntico
    casi no agrega información.

OJO CON EL COSTO. Cada conversación son ~8 turnos × (conversador + vigía) más
el simulador y el juez: un ciclo de nivel 3 completo son ~20 conversaciones y
varios cientos de llamadas. Correr esto 24/7 quema créditos de verdad. Por eso
PAUSA_OCIOSO es alta por defecto: lo caro es el modo de relleno, no el útil.
"""
import argparse, hashlib, json, os, subprocess, sys, time

BASE = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(BASE)
PY = os.path.join(RAIZ, "venv", "bin", "python")
ESTADO = os.path.join(BASE, "estado_vigilancia.json")
BITACORA = os.path.join(BASE, "logs", "vigilancia.log")

VIGILADOS = ["aikiu_core.md", "aikiu.py",
             "simulador/escenarios.json", "simulador/aserciones.json",
             "simulador/niveles.json", "simulador/personas"]

PAUSA_CAMBIO = 20        # s de gracia: no disparar a mitad de una edición
PAUSA_OCIOSO = 30 * 60   # s entre corridas de relleno (lo caro es esto)


def _huella():
    """Hash del contenido de todo lo que puede cambiar el comportamiento."""
    h = hashlib.sha256()
    for rel in VIGILADOS:
        p = os.path.join(RAIZ, rel)
        archivos = []
        if os.path.isdir(p):
            archivos = [os.path.join(p, f) for f in sorted(os.listdir(p))
                        if not f.startswith(".")]
        elif os.path.exists(p):
            archivos = [p]
        for a in archivos:
            try:
                with open(a, "rb") as f:
                    h.update(rel.encode()); h.update(f.read())
            except OSError:
                pass
    return h.hexdigest()[:16]


def _log(msg):
    linea = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(linea, flush=True)
    os.makedirs(os.path.dirname(BITACORA), exist_ok=True)
    with open(BITACORA, "a") as f:
        f.write(linea + "\n")


def _leer_estado():
    if os.path.exists(ESTADO):
        try:
            return json.load(open(ESTADO))
        except (OSError, ValueError):
            pass
    return {"huella": None, "veredicto": None, "corridas": 0}


def _nivel_actual():
    return json.load(open(os.path.join(BASE, "niveles.json")))["estado"]["nivel_actual"]


def _correr_ciclo(nivel, reps=None):
    """Devuelve (pasa, salida). El gate del ciclo sale con código 0 o 1."""
    cmd = [PY, os.path.join(BASE, "ciclo.py"), "-l", str(nivel)]
    if reps:
        cmd += ["-n", str(reps)]
    r = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True, timeout=7200)
    return r.returncode == 0, r.stdout


def _resumen(salida):
    """Se queda con el bloque del veredicto, que es lo único que se avisa."""
    if "VEREDICTO" not in salida:
        return salida[-500:]
    return salida[salida.index("VEREDICTO"):][:900]


def _avisar(texto):
    """Aviso al bot admin de Telegram, si está configurado."""
    tok = os.environ.get("ADMIN_BOT_TOKEN")
    chat = os.environ.get("ADMIN_CHAT_ID")
    if not (tok and chat):
        return
    try:
        import urllib.parse, urllib.request
        datos = urllib.parse.urlencode(
            {"chat_id": chat, "text": texto[:3900]}).encode()
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{tok}/sendMessage", datos, timeout=15)
    except Exception as e:
        _log(f"no se pudo avisar por Telegram: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--avisar", action="store_true",
                    help="avisar por Telegram cuando cambia el veredicto")
    ap.add_argument("--solo-cambios", action="store_true",
                    help="no correr de relleno; esperar cambios (más barato)")
    a = ap.parse_args()

    st = _leer_estado()
    _log(f"vigilando {len(VIGILADOS)} rutas | nivel {_nivel_actual()} | "
         f"relleno {'off' if a.solo_cambios else f'cada {PAUSA_OCIOSO//60} min'}")
    ultimo_relleno = 0.0

    while True:
        try:
            h = _huella()
            cambio = h != st["huella"]
            toca_relleno = (not a.solo_cambios
                            and time.time() - ultimo_relleno > PAUSA_OCIOSO)

            if not (cambio or toca_relleno):
                time.sleep(30); continue

            if cambio:
                _log(f"cambio detectado ({st['huella']} → {h}), esperando {PAUSA_CAMBIO}s")
                time.sleep(PAUSA_CAMBIO)
                h = _huella()  # por si seguía editando
                motivo = "cambio en las reglas"
            else:
                motivo = "relleno (caza de intermitentes)"
                ultimo_relleno = time.time()

            nivel = _nivel_actual()
            _log(f"▶ ciclo nivel {nivel} — {motivo}")
            t0 = time.time()
            pasa, salida = _correr_ciclo(nivel)
            mins = (time.time() - t0) / 60
            veredicto = "VERDE" if pasa else "ROJO"
            _log(f"◀ nivel {nivel}: {veredicto} ({mins:.0f} min)")

            volteo = st["veredicto"] and st["veredicto"] != veredicto
            st.update(huella=h, veredicto=veredicto, corridas=st["corridas"] + 1,
                      ultimo=time.strftime("%Y-%m-%d %H:%M:%S"), nivel=nivel)
            json.dump(st, open(ESTADO, "w"), indent=2)

            with open(os.path.join(BASE, "logs",
                                   f"vigilancia_{time.strftime('%Y%m%d_%H%M%S')}.txt"), "w") as f:
                f.write(salida)

            # Solo se avisa cuando el veredicto CAMBIA. Un aviso por corrida se
            # vuelve ruido y se deja de leer, que es peor que no avisar.
            if a.avisar and (volteo or cambio):
                icono = "🟢" if pasa else "🔴"
                _avisar(f"{icono} Aikiu nivel {nivel}: {veredicto}"
                        + (" (¡cambió!)" if volteo else "")
                        + f"\n{motivo}\n\n{_resumen(salida)}")
            if volteo:
                _log(f"⚠️  el veredicto cambió a {veredicto}")

        except KeyboardInterrupt:
            _log("cortado a mano"); return
        except Exception as e:
            _log(f"error en el ciclo: {type(e).__name__}: {e}")
            time.sleep(120)


if __name__ == "__main__":
    main()
