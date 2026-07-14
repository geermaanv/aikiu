"""
Herramientas para consultas en tiempo real: clima, dólar, noticias.
Usadas con tool calling nativo de Groq (formato OpenAI).
"""

import json
import logging
import re
import httpx

log = logging.getLogger("aikiu")

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "consultar_clima",
            "description": (
                "Consulta el clima actual en Buenos Aires o la ciudad indicada. "
                "Usá esta herramienta cuando el usuario pregunte por el tiempo, "
                "temperatura, lluvia, frío, calor o clima."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ciudad": {
                        "type": "string",
                        "description": "Ciudad para consultar. Default: Buenos Aires.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_dolar",
            "description": (
                "Consulta la cotización del dólar blue y oficial en Argentina hoy. "
                "Usá esta herramienta cuando el usuario pregunte por el dólar, "
                "el precio del dólar, o el tipo de cambio."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_noticias",
            "description": (
                "Obtiene los titulares de noticias más recientes de Argentina. "
                "Usá esta herramienta cuando el usuario pregunte por las noticias, "
                "qué pasó hoy, o novedades."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tema": {
                        "type": "string",
                        "description": "Tema específico (opcional). Ej: política, deporte, economía.",
                    }
                },
                "required": [],
            },
        },
    },
]


async def consultar_clima(ciudad: str = "Buenos Aires") -> str:
    ciudad_enc = ciudad.strip().replace(" ", "+")
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(f"https://wttr.in/{ciudad_enc}?format=j1")
            r.raise_for_status()
            data = r.json()
        c = data["current_condition"][0]
        temp   = c["temp_C"]
        feels  = c["FeelsLikeC"]
        desc   = c["weatherDesc"][0]["value"]
        hum    = c["humidity"]
        return (
            f"Clima en {ciudad}: {desc}. "
            f"Temperatura {temp}°C (sensación {feels}°C), humedad {hum}%."
        )
    except Exception as e:
        return f"No pude obtener el clima en este momento: {e}"


async def consultar_dolar() -> str:
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            rb = await client.get("https://dolarapi.com/v1/dolares/blue")
            ro = await client.get("https://dolarapi.com/v1/dolares/oficial")
            rb.raise_for_status()
            ro.raise_for_status()
        blue = rb.json()
        ofic = ro.json()
        return (
            f"Dólar hoy — Blue: compra ${blue['compra']}, venta ${blue['venta']}. "
            f"Oficial: compra ${ofic['compra']}, venta ${ofic['venta']}."
        )
    except Exception as e:
        return f"No pude obtener la cotización del dólar en este momento: {e}"


async def consultar_noticias(tema: str = "") -> str:
    try:
        url = "https://www.lanacion.com.ar/arc/outboundfeeds/rss/"
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
        # CDATA no captura el título del feed — no hace falta saltar el primero
        headlines = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>", r.text)
        if not headlines:
            # Fallback texto plano: el primer <title> es el nombre del feed
            all_titles = re.findall(r"<title>(.*?)</title>", r.text)
            headlines = [t for t in all_titles[1:] if t.strip()]
        headlines = [t.strip() for t in headlines if t.strip()][:6]
        if tema:
            tema_lower = tema.lower()
            filtradas = [h for h in headlines if tema_lower in h.lower()]
            if filtradas:
                headlines = filtradas[:3]
        if not headlines:
            return "No encontré noticias disponibles en este momento."
        return "Noticias de hoy: " + ". ".join(headlines[:4]) + "."
    except Exception as e:
        return f"No pude obtener las noticias en este momento: {e}"


async def titulares_google_news(query: str = "", max_titulares: int = 25) -> list[str]:
    """Titulares del día desde Google News (Argentina, español). RSS gratis,
    sin API key. Sin query → top titulares generales. Con query → búsqueda por
    tema o ciudad (para temas locales). Devuelve titulares crudos (sin curar).
    Se usa en el job nocturno que arma la lista de temas del día."""
    if query:
        from urllib.parse import quote
        url = f"https://news.google.com/rss/search?q={quote(query)}&hl=es-419&gl=AR&ceid=AR:es-419"
    else:
        url = "https://news.google.com/rss?hl=es-419&gl=AR&ceid=AR:es-419"
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
        # En Google News RSS los títulos vienen en texto plano; el primero es
        # el nombre del feed ("Google Noticias"), se descarta.
        titulos = re.findall(r"<title>(.*?)</title>", r.text)[1:]
        limpios = []
        for t in titulos:
            t = t.replace("&#39;", "'").replace("&amp;", "&").replace("&quot;", '"').strip()
            # Google News agrega " - Medio" al final; nos quedamos con el titular.
            t = re.sub(r"\s+-\s+[^-]+$", "", t).strip()
            if t:
                limpios.append(t)
        return limpios[:max_titulares]
    except Exception as e:
        log.warning(f"titulares_google_news falló: {e}")
        return []


async def ejecutar_tool(name: str, args: dict) -> str:
    if name == "consultar_clima":
        return await consultar_clima(args.get("ciudad", "Buenos Aires"))
    if name == "consultar_dolar":
        return await consultar_dolar()
    if name == "consultar_noticias":
        return await consultar_noticias(args.get("tema", ""))
    return f"Herramienta '{name}' no reconocida."
