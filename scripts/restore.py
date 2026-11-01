# -*- coding: utf-8 -*-
"""Restaura un respaldo logico de OrtoSistema en la base actual.

Por seguridad, por defecto hace un ensayo (dry-run) que solo muestra lo que haria.
Para restaurar de verdad: --ejecutar.

Uso:
    python v2_api/scripts/restore.py                 # lista respaldos disponibles
    python v2_api/scripts/restore.py --ultimo        # ensayo del mas reciente
    python v2_api/scripts/restore.py --ultimo --ejecutar
    python v2_api/scripts/restore.py --archivo C:\\ruta\\datos.json.gz --ejecutar
"""
import argparse
import base64
import datetime as dt
import gzip
import json
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

AQUI = Path(__file__).resolve().parent
API = AQUI.parent
ENV = API / ".env"
DESTINO_DEFAULT = Path.home() / "Documents" / "ortosistema-backups"

ORDEN = [
    "usuarios", "funciones_rol", "pacientes", "tarifario",
    "estudios_imagenes", "imagenes_estudio", "cirugias", "implantes",
    "citas", "evaluaciones", "documentos", "procedimientos_paciente",
    "recetas", "cargos_facturacion", "ortesis_paciente", "pt_sesiones",
    "referimientos", "formularios_proms", "autorizaciones_preauth", "auditoria",
]


def leer_env(path):
    env = {}
    for linea in open(path, encoding="utf-8"):
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            k, v = linea.split("=", 1)
            env[k] = v.strip().strip('"').strip("'")
    return env


def deserializar(obj):
    if isinstance(obj, dict) and "__bytes__" in obj and len(obj) == 1:
        return base64.b64decode(obj["__bytes__"])
    if isinstance(obj, dict):
        return {k: deserializar(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [deserializar(x) for x in obj]
    return obj


def listar(destino):
    if not destino.exists():
        print("No hay respaldos en", destino)
        return []
    carpetas = sorted((p for p in destino.iterdir() if p.is_dir()),
                      key=lambda p: p.name, reverse=True)
    print(f"{'#':>3}  {'carpeta':22}  {'filas':>6}  fecha")
    print("-" * 55)
    for i, c in enumerate(carpetas, 1):
        arch = c / "datos.json.gz"
        if not arch.exists():
            continue
        try:
            with gzip.open(arch, "rt", encoding="utf-8") as f:
                meta = json.load(f)["meta"]
            print(f"{i:3}  {c.name:22}  {meta.get('filas', '?'):>6}  {meta.get('fecha', '')[:19]}")
        except Exception as e:
            print(f"{i:3}  {c.name:22}  ERROR: {e}")
    return carpetas


def main():
    ap = argparse.ArgumentParser(description="Restaura un respaldo de OrtoSistema")
    ap.add_argument("--destino", type=Path, default=DESTINO_DEFAULT)
    ap.add_argument("--ultimo", action="store_true", help="usar el respaldo mas reciente")
    ap.add_argument("--archivo", type=Path, help="ruta a un datos.json.gz especifico")
    ap.add_argument("--ejecutar", action="store_true",
                    help="aplicar los cambios (sin esto solo hace ensayo)")
    args = ap.parse_args()

    if args.archivo:
        archivo = args.archivo
    elif args.ultimo:
        carpetas = sorted((p for p in args.destino.iterdir() if p.is_dir()),
                          key=lambda p: p.name, reverse=True)
        if not carpetas:
            sys.exit("No hay respaldos disponibles")
        archivo = carpetas[0] / "datos.json.gz"
    else:
        listar(args.destino)
        print("\nUsa --ultimo o --archivo para restaurar. Por defecto es ensayo (dry-run).")
        return

    if not archivo.exists():
        sys.exit(f"No existe {archivo}")

    with gzip.open(archivo, "rt", encoding="utf-8") as f:
        datos = json.load(f)
    datos["tablas"] = {k: deserializar(v) for k, v in datos["tablas"].items()}
    meta = datos["meta"]
    print(f"Respaldo: {archivo}")
    print(f"Fecha: {meta.get('fecha')}  ·  Base origen: {meta.get('base')}  ·  Filas: {meta.get('filas')}")

    env = leer_env(ENV)
    if "DATABASE_URL" not in env:
        sys.exit("Falta DATABASE_URL en .env")

    with psycopg.connect(env["DATABASE_URL"], row_factory=dict_row) as conn:
        # Conteos actuales
        print("\nEstado actual:")
        for t in ORDEN:
            n = conn.execute(f"select count(*) n from {t}").fetchone()["n"]
            m = len(datos["tablas"].get(t, []))
            print(f"  {t:26} actual={n:5}  respaldo={m:5}  {'CAMBIA' if n != m else ''}")

        if not args.ejecutar:
            print("\nENSAYO (dry-run). Nada se modifico.")
            print("Para aplicar: agrega --ejecutar")
            return

        print("\nRestaurando...")
        # Borrar en orden inverso (hijos primero).
        for t in reversed(ORDEN):
            conn.execute(f"truncate table {t} restart identity cascade")
        # Insertar en orden (padres primero).
        for t in ORDEN:
            filas = datos["tablas"].get(t, [])
            if not filas:
                continue
            cols = list(filas[0].keys())
            placeholders = ",".join(["%s"] * len(cols))
            sql = f"insert into {t}({','.join(cols)}) values ({placeholders})"
            with conn.cursor() as cur:
                for f in filas:
                    cur.execute(sql, [f[c] for c in cols])
            print(f"  {t:26} {len(filas)} filas")

        # Ajustar secuencias.
        for t in ORDEN:
            r = conn.execute(
                "select 1 from information_schema.columns "
                "where table_schema='public' and table_name=%s and column_name='id'",
                (t,)).fetchone()
            if not r:
                continue
            seq = conn.execute("select pg_get_serial_sequence(%s,'id') as seq", (t,)).fetchone()["seq"]
            if not seq:
                continue
            conn.execute(
                f"select setval(%s, coalesce((select max(id) from {t}), 1), "
                f"(select max(id) from {t}) is not null)", (seq,))
        conn.commit()
        print("\nRestauracion completa.")


if __name__ == "__main__":
    main()
