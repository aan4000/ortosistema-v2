# -*- coding: utf-8 -*-
"""Respaldo logico de la base de datos de OrtoSistema (PostgreSQL/Neon).

Copia todas las tablas a un archivo JSON comprimido, por fecha, en una carpeta de
OneDrive. No requiere pg_dump y funciona con PostgreSQL 18.

Uso:
    python v2_api/scripts/backup.py                 # respaldo normal
    python v2_api/scripts/backup.py --retener 14    # conservar 14 dias
    python v2_api/scripts/backup.py --destino C:\\otra\\ruta
"""
import argparse
import base64
import datetime as dt
import gzip
import json
import os
import sys
import time
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

# Rutas relativas a este script: v2_api/scripts/ -> v2_api/
AQUI = Path(__file__).resolve().parent
API = AQUI.parent
ENV = API / ".env"

# Orden seguro para claves foraneas (primero padres, luego hijos).
ORDEN = [
    "usuarios", "funciones_rol", "pacientes", "tarifario",
    "estudios_imagenes", "imagenes_estudio", "cirugias", "implantes",
    "citas", "evaluaciones", "documentos", "procedimientos_paciente",
    "recetas", "cargos_facturacion", "ortesis_paciente", "pt_sesiones",
    "referimientos", "formularios_proms", "autorizaciones_preauth", "auditoria",
]

RETENER_DEFAULT = 30
DESTINO_DEFAULT = Path.home() / "Documents" / "ortosistema-backups"


def leer_env(path):
    env = {}
    for linea in io_open(path):
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            k, v = linea.split("=", 1)
            env[k] = v.strip().strip('"').strip("'")
    return env


def io_open(p):
    return open(p, encoding="utf-8")


def serializar(obj):
    if isinstance(obj, (dt.datetime, dt.date, dt.time)):
        return obj.isoformat()
    if isinstance(obj, dt.timedelta):
        return obj.total_seconds()
    if isinstance(obj, (bytes, bytearray, memoryview)):
        return {"__bytes__": base64.b64encode(bytes(obj)).decode("ascii")}
    if isinstance(obj, (set, frozenset)):
        return sorted(obj)
    # Decimal y otros tipos numericos no nativos
    if hasattr(obj, "__float__") and not isinstance(obj, bool):
        try:
            return float(obj)
        except (ValueError, TypeError):
            pass
    raise TypeError(f"Tipo no serializable: {type(obj)!r}")


def main():
    ap = argparse.ArgumentParser(description="Respaldo logico de OrtoSistema")
    ap.add_argument("--retener", type=int, default=RETENER_DEFAULT,
                    help="cuantos respaldos conservar (default 30)")
    ap.add_argument("--destino", type=Path, default=DESTINO_DEFAULT,
                    help="carpeta destino")
    args = ap.parse_args()

    if not ENV.exists():
        sys.exit(f"No existe {ENV}. Crea el archivo .env antes de respaldar.")
    env = leer_env(ENV)
    if "DATABASE_URL" not in env:
        sys.exit("Falta DATABASE_URL en .env")

    destino = args.destino
    destino.mkdir(parents=True, exist_ok=True)

    estampa = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
    carpeta = destino / estampa
    carpeta.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    datos = {"meta": {"fecha": dt.datetime.now().isoformat(),
                      "base": None, "filas": 0}}
    total = 0
    with psycopg.connect(env["DATABASE_URL"], row_factory=dict_row) as c:
        datos["meta"]["base"] = c.execute("select current_database() as db").fetchone()["db"]
        datos["tablas"] = {}
        for t in ORDEN:
            filas = c.execute(f"select * from {t} order by id" if _tiene_id(c, t)
                              else f"select * from {t}").fetchall()
            datos["tablas"][t] = [dict(f) for f in filas]
            total += len(filas)
            print(f"{t:26} {len(filas)}")
    datos["meta"]["filas"] = total

    archivo = carpeta / "datos.json.gz"
    with gzip.open(archivo, "wt", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, default=serializar, indent=1)

    # Copia del esquema (para restaurar estructura si hiciera falta).
    esquema = API / "schema.sql"
    if esquema.exists():
        (carpeta / "schema.sql").write_text(esquema.read_text(encoding="utf-8"),
                                            encoding="utf-8")

    # Rotacion: conservar solo los N mas recientes.
    carpetas = sorted((p for p in destino.iterdir() if p.is_dir()),
                      key=lambda p: p.name, reverse=True)
    for vieja in carpetas[args.retener:]:
        for f in vieja.iterdir():
            f.unlink()
        vieja.rmdir()
        print(f"eliminado (rotacion): {vieja.name}")

    print(f"\nRespaldo listo: {archivo}")
    print(f"Filas: {total} · tiempo: {time.time()-t0:.1f}s · "
          f"tamano: {archivo.stat().st_size/1024:.1f} KB")
    print(f"Conservados: {min(args.retener, len(carpetas))} respaldos")


def _tiene_id(conn, tabla):
    r = conn.execute(
        "select 1 from information_schema.columns "
        "where table_schema='public' and table_name=%s and column_name='id'",
        (tabla,)).fetchone()
    return bool(r)


if __name__ == "__main__":
    main()
