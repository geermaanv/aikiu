"""Tests para core/invites.py — códigos de invitación."""

import random
from datetime import datetime, timedelta

import pytest

from core import hogar as hogar_mod
from core import invites as invites_mod


@pytest.fixture(autouse=True)
def _aislar(tmp_path, monkeypatch):
    monkeypatch.setenv("AIKIU_REGISTRY", str(tmp_path))
    # Los tests usan adultos 42 y 99: como `consumir()` ahora valida que el
    # hogar exista, los creamos en el registry aislado.
    hogar_mod.crear_hogar(42, nombre="Adulto42")
    hogar_mod.crear_hogar(99, nombre="Adulto99")
    yield


def test_generar_codigo_devuelve_string_de_longitud_correcta():
    codigo = invites_mod.generar_codigo(42)
    assert isinstance(codigo, str)
    assert len(codigo) == invites_mod.LONGITUD_CODIGO
    assert all(c in invites_mod.ALFABETO_CODIGO for c in codigo)


def test_generar_codigo_se_persiste():
    codigo = invites_mod.generar_codigo(42)
    data = invites_mod._leer()
    assert codigo in data
    assert data[codigo]["adulto_chat_id"] == 42
    assert data[codigo]["usos_restantes"] == 1


def test_consumir_codigo_valido_devuelve_adulto_y_lo_borra():
    codigo = invites_mod.generar_codigo(42)
    assert invites_mod.consumir(codigo) == 42
    # Single-use: ya no existe
    assert invites_mod.consumir(codigo) is None


def test_consumir_codigo_inexistente_devuelve_none():
    assert invites_mod.consumir("XXXXXX") is None


def test_consumir_codigo_vacio_o_none():
    assert invites_mod.consumir("") is None
    assert invites_mod.consumir(None) is None  # type: ignore[arg-type]


def test_consumir_normaliza_a_mayusculas():
    codigo = invites_mod.generar_codigo(42)
    assert invites_mod.consumir(codigo.lower()) == 42


def test_consumir_normaliza_espacios():
    codigo = invites_mod.generar_codigo(42)
    assert invites_mod.consumir(f"  {codigo}  ") == 42


def test_consumir_codigo_expirado_no_funciona():
    codigo = invites_mod.generar_codigo(42, ttl_horas=1)
    # Forzamos vencimiento manipulando el JSON.
    data = invites_mod._leer()
    data[codigo]["expira_en"] = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
    invites_mod._escribir_atomico(data)
    assert invites_mod.consumir(codigo) is None


def test_codigo_con_usos_multiples_se_decrementa():
    codigo = invites_mod.generar_codigo(42, usos=3)
    assert invites_mod.consumir(codigo) == 42
    assert invites_mod.consumir(codigo) == 42
    assert invites_mod.consumir(codigo) == 42
    assert invites_mod.consumir(codigo) is None  # 4to ya no


def test_inspeccionar_devuelve_metadatos_sin_consumir():
    codigo = invites_mod.generar_codigo(42)
    info = invites_mod.inspeccionar(codigo)
    assert info is not None
    assert info["adulto_chat_id"] == 42
    # Sigue vivo:
    assert invites_mod.consumir(codigo) == 42


def test_listar_de_adulto_solo_devuelve_los_suyos():
    c1 = invites_mod.generar_codigo(42)
    c2 = invites_mod.generar_codigo(42)
    invites_mod.generar_codigo(99)
    propios = invites_mod.listar_de_adulto(42)
    codigos = [c for c, _ in propios]
    assert c1 in codigos
    assert c2 in codigos
    assert len(propios) == 2


def test_consumir_codigo_de_hogar_borrado_devuelve_none_y_se_elimina():
    """Si el hogar deja de existir entre la generación y el consumo, el
    código no se honra. Caso real: admin borra un hogar con códigos vivos."""
    codigo = invites_mod.generar_codigo(42)
    # Hogar borrado externamente (simulamos lo que hace `cmd_borrar`).
    hogar_mod.borrar_hogar(42)
    assert invites_mod.consumir(codigo) is None
    # El código se eliminó al detectar el hogar inexistente, para no quedar
    # como huérfano en `_invites.json`.
    assert codigo not in invites_mod._leer()


def test_purgar_de_hogar_elimina_solo_los_de_ese_hogar():
    """Limpieza explícita al borrar un hogar: borra los códigos pendientes
    de ese adulto sin tocar los demás."""
    c_a = invites_mod.generar_codigo(42)
    c_b = invites_mod.generar_codigo(42)
    c_otro = invites_mod.generar_codigo(99)
    n = invites_mod.purgar_de_hogar(42)
    assert n == 2
    data = invites_mod._leer()
    assert c_a not in data
    assert c_b not in data
    assert c_otro in data


def test_purgar_de_hogar_sin_codigos_devuelve_cero():
    assert invites_mod.purgar_de_hogar(42) == 0


def test_consumir_es_thread_safe_no_consume_dos_veces_el_mismo_codigo():
    """Race condition: dos /vincular simultáneos sobre el mismo código de
    un solo uso no deben ambos descontar. El lock interno serializa el
    read-modify-write para garantizar single-use real."""
    import threading

    codigo = invites_mod.generar_codigo(42, usos=1)
    resultados: list = []
    barrier = threading.Barrier(8)

    def intentar():
        barrier.wait()
        resultados.append(invites_mod.consumir(codigo))

    hilos = [threading.Thread(target=intentar) for _ in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    exitos = [r for r in resultados if r is not None]
    assert len(exitos) == 1, (
        f"Esperaba exactamente 1 consumo exitoso, hubo {len(exitos)}: {resultados}"
    )
    assert exitos[0] == 42


def test_purgar_expirados_elimina_solo_los_vencidos():
    invites_mod.generar_codigo(42, ttl_horas=24)
    codigo_viejo = invites_mod.generar_codigo(42, ttl_horas=1)
    data = invites_mod._leer()
    data[codigo_viejo]["expira_en"] = (datetime.now() - timedelta(hours=2)).isoformat(timespec="seconds")
    invites_mod._escribir_atomico(data)
    purgados = invites_mod.purgar_expirados()
    assert purgados == 1
    assert codigo_viejo not in invites_mod._leer()


def test_dos_codigos_distintos_para_mismo_adulto():
    c1 = invites_mod.generar_codigo(42)
    c2 = invites_mod.generar_codigo(42)
    assert c1 != c2
