import asyncio
from pathlib import Path

import edge_tts


async def sintetizar(texto: str, salida: Path, voz: str = "es-AR-ElenaNeural"):
    mp3 = salida.with_suffix(".mp3")
    communicate = edge_tts.Communicate(texto, voice=voz)
    await communicate.save(str(mp3))
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-i", str(mp3), "-c:a", "libopus", str(salida),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
