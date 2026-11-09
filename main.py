"""OrtoSistema: API en Python (FastAPI + PostgreSQL/Neon)."""
import datetime as dt
import getpass
import os
import json
import urllib.error
import urllib.request
import sys
import time
import unicodedata
from contextlib import asynccontextmanager
from pathlib import Path

import bcrypt
import jwt
import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, Request
import base64
import secrets
from fastapi import Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

# Carga .env local si existe (no sobrescribe variables ya definidas, p.ej. en Render).
_env = Path(__file__).parent / ".env"
if _env.is_file():
    for _line in _env.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ[_k.strip()] = _v.strip().strip('"').strip("'")

DATABASE_URL = os.environ["DATABASE_URL"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_HORAS = int(os.getenv("JWT_HORAS", "8"))
CORS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
AQUI = Path(__file__).parent

pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=5, open=False,
                      kwargs={"row_factory": dict_row})

# Tablas y columnas permitidas. Es la única lista que toca SQL dinámico:
# si una tabla o columna no está aquí, la API la rechaza.
TABLAS = {
    "pacientes": ["codigo", "nombre", "edad", "cedula", "seguro", "alergias", "diagnostico", "etapa",
                  "antecedentes_morbidos", "antecedentes_quirurgicos", "medicamentos",
                  "antecedentes_familiares", "habitos", "fecha_nacimiento", "sexo", "telefono",
                  "correo", "numero_afiliado",
                  "estado_atencion", "estado_autorizacion", "autorizacion", "historial"],
    "citas": ["paciente_id", "fecha", "hora", "duracion", "tipo", "motivo", "medico",
              "estado", "motivo_cancelacion"],
    "evaluaciones": ["paciente_id", "fecha", "texto", "tipo", "medico", "detalle"],
    "estudios_imagenes": ["paciente_id", "fecha", "tipo", "region", "estado", "informe",
                          "miniatura"],
    "cirugias": ["paciente_id", "fecha", "hora", "procedimiento", "lado", "duracion", "sala",
                 "cirujano", "anestesia", "implantes_previstos", "checklist",
                 "sin_autorizacion", "estado", "tipo_sangre"],
    "implantes": ["cirugia_id", "paciente_id", "descripcion", "lote"],
    "pt_sesiones": ["paciente_id", "fecha", "descripcion", "dolor"],
    "formularios_proms": ["paciente_id", "fecha", "cuestionario", "puntaje"],
    "referimientos": ["paciente_id", "fecha", "detalle", "estado"],
    "autorizaciones_preauth": ["paciente_id", "procedimiento", "seguro", "estado", "vence"],
    "cargos_facturacion": ["paciente_id", "fecha", "codigo", "concepto", "monto", "estado", "medico"],
    "tarifario": ["codigo", "nombre", "categoria", "fuente", "precio"],
    "procedimientos_paciente": ["paciente_id", "fecha", "procedimiento", "codigo", "categoria",
                                "precio", "medico", "estado"],
    "ortesis_paciente": ["paciente_id", "fecha", "ortesis", "categoria", "lado", "talla",
                         "indicacion", "medico", "estado"],
    "recetas": ["paciente_id", "fecha", "tipo", "titulo", "items", "notas", "medico"],
}
# Columnas jsonb: se envían como objeto/lista y psycopg las adapta con Jsonb.
JSONB = {"autorizacion", "historial", "detalle", "checklist", "items"}
CLINICAS = {"pacientes", "citas", "evaluaciones", "estudios_imagenes", "cirugias", "implantes",
            "pt_sesiones", "formularios_proms", "referimientos", "documentos",
            "procedimientos_paciente", "ortesis_paciente", "recetas"}
GESTION = {"pacientes", "citas", "referimientos", "autorizaciones_preauth",
           "cargos_facturacion", "tarifario", "documentos"}
PERMISOS = {  # los permisos se aplican aquí, en el servidor
    "admin": {"leer": "*", "escribir": "*"},
    "medico": {"leer": "*", "escribir": CLINICAS | {"autorizaciones_preauth"}},
    "enfermeria": {  # apoyo clínico: consulta el expediente y adjunta estudios/documentos
        "leer": {"pacientes", "citas", "evaluaciones", "estudios_imagenes", "documentos",
                 "procedimientos_paciente", "ortesis_paciente", "recetas", "referimientos"},
        "escribir": {"estudios_imagenes", "documentos", "ortesis_paciente"}},
    "secretaria": {  # recepción y gestión: consulta lo clínico, edita la gestión
        "leer": GESTION | {"pacientes", "estudios_imagenes", "recetas",
                           "procedimientos_paciente", "ortesis_paciente"},
        "escribir": GESTION},
    "fisio": {
        "leer": {"pacientes", "citas", "pt_sesiones", "formularios_proms", "ortesis_paciente",
                 "documentos", "estudios_imagenes"},
        "escribir": {"pt_sesiones", "formularios_proms", "ortesis_paciente"}},
    "facturacion": {  # cobros y autorizaciones, sin editar la historia clínica
        "leer": {"pacientes", "citas", "cargos_facturacion", "tarifario",
                 "autorizaciones_preauth", "procedimientos_paciente", "referimientos"},
        "escribir": {"cargos_facturacion", "tarifario", "autorizaciones_preauth"}},
}


MODULOS = {  # función del menú -> tablas que gobierna
    "agenda": ["citas"],
    "pacientes": ["pacientes", "evaluaciones"],
    "procedimientos": ["procedimientos_paciente"],
    "ortesis": ["ortesis_paciente"],
    "quirofano": ["cirugias", "implantes"],
    "estudios": ["estudios_imagenes"],
    "documentos": ["documentos"],
    "rehab": ["pt_sesiones", "formularios_proms"],
    "referimientos": ["referimientos"],
    "autorizaciones": ["autorizaciones_preauth"],
    "facturacion": ["cargos_facturacion", "tarifario"],
    "recetas": ["recetas"],
}
TABLA_MODULO = {t: m for m, ts in MODULOS.items() for t in ts}
FUNC_INICIAL = {
    "medico": set(MODULOS),
    "enfermeria": {"agenda", "pacientes", "estudios", "documentos", "ortesis", "recetas"},
    "secretaria": {"agenda", "pacientes", "procedimientos", "estudios", "documentos",
                   "ortesis", "referimientos", "autorizaciones", "facturacion", "recetas"},
    "fisio": {"agenda", "pacientes", "rehab", "ortesis", "estudios", "documentos"},
    "facturacion": {"agenda", "pacientes", "procedimientos", "autorizaciones",
                    "facturacion", "referimientos"},
}
FUNC: dict = {}  # rol -> funciones activas (el administrador siempre tiene todas)


def puede(rol, accion, tabla):
    if tabla not in TABLAS:
        return False
    if rol == "admin":
        return True
    p = PERMISOS.get(rol, {}).get(accion, set())
    return (p == "*" or tabla in p) and TABLA_MODULO.get(tabla) in FUNC.get(rol, set())


def cargar_funciones():
    with pool.connection() as c:
        filas = c.execute("select rol, modulo from funciones_rol").fetchall()
        if not any(f["rol"] == "_init" for f in filas):  # primera vez: valores por defecto
            for r, ms in FUNC_INICIAL.items():
                for mod in ms:
                    c.execute("insert into funciones_rol(rol,modulo) values (%s,%s) on conflict do nothing", (r, mod))
            c.execute("insert into funciones_rol(rol,modulo) values ('_init','_') on conflict do nothing")
            filas = c.execute("select rol, modulo from funciones_rol").fetchall()
        if not any(f["rol"] == "_up_documentos" for f in filas):
            # "documentos" pasó a ser un módulo propio (antes colgaba de "pacientes").
            for r in ("medico", "secretaria"):
                c.execute("insert into funciones_rol(rol,modulo) values (%s,'documentos') "
                          "on conflict do nothing", (r,))
            c.execute("insert into funciones_rol(rol,modulo) values ('_up_documentos','_') "
                      "on conflict do nothing")
            filas = c.execute("select rol, modulo from funciones_rol").fetchall()
        if not any(f["rol"] == "_up_ortesis" for f in filas):
            # "ortesis" se agregó después: se activa para médico y fisioterapeuta.
            for r in ("medico", "fisio"):
                c.execute("insert into funciones_rol(rol,modulo) values (%s,'ortesis') "
                          "on conflict do nothing", (r,))
            c.execute("insert into funciones_rol(rol,modulo) values ('_up_ortesis','_') "
                      "on conflict do nothing")
            filas = c.execute("select rol, modulo from funciones_rol").fetchall()
        if not any(f["rol"] == "_up_recetas" for f in filas):
            # "recetas" se agrego despues: se activa para medico y secretaria.
            for r in ("medico", "secretaria"):
                c.execute("insert into funciones_rol(rol,modulo) values (%s,'recetas') "
                          "on conflict do nothing", (r,))
            c.execute("insert into funciones_rol(rol,modulo) values ('_up_recetas','_') "
                      "on conflict do nothing")
            filas = c.execute("select rol, modulo from funciones_rol").fetchall()
        if not any(f["rol"] == "_up_perfiles_2026" for f in filas):
            # Protocolo de mejora de perfiles: agrega los accesos recomendados que falten
            # sin quitar las funciones que el administrador ya haya personalizado.
            for r, ms in FUNC_INICIAL.items():
                for mod in ms:
                    c.execute("insert into funciones_rol(rol,modulo) values (%s,%s) "
                              "on conflict do nothing", (r, mod))
            for mod in ("estudios", "recetas"):
                c.execute("insert into funciones_rol(rol,modulo) values ('secretaria',%s) "
                          "on conflict do nothing", (mod,))
            c.execute("insert into funciones_rol(rol,modulo) values ('_up_perfiles_2026','_') "
                      "on conflict do nothing")
            filas = c.execute("select rol, modulo from funciones_rol").fetchall()
    FUNC.clear()
    for f in filas:
        FUNC.setdefault(f["rol"], set()).add(f["modulo"])


def exigir(u, accion, tabla):
    if tabla not in TABLAS:
        raise HTTPException(404, "Tabla desconocida")
    if not puede(u["rol"], accion, tabla):
        raise HTTPException(403, "Tu rol no tiene permiso para esta acción")


def aplicar_schema():
    sql = (AQUI / "schema.sql").read_text(encoding="utf-8")
    with pool.connection() as c:
        c.execute(sql)


@asynccontextmanager
async def ciclo(app):
    pool.open(wait=True, timeout=30)
    if os.getenv("AUTO_SCHEMA", "1") == "1":
        aplicar_schema()
    cargar_funciones()
    yield
    pool.close()


app = FastAPI(title="OrtoSistema API", lifespan=ciclo)
if CORS:
    app.add_middleware(CORSMiddleware, allow_origins=CORS, allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(psycopg.Error)
async def error_bd(_: Request, e: psycopg.Error):
    return JSONResponse({"detail": "Dato inválido o registro relacionado inexistente"}, 400)


# ---------- Autenticación ----------
bearer = HTTPBearer(auto_error=False)
INTENTOS: dict = {}  # (usuario, ip) -> (fallos, último_intento)


def usuario_actual(req: Request, cred: HTTPAuthorizationCredentials = Depends(bearer)):
    if not cred:
        raise HTTPException(401, "Inicia sesión para continuar")
    try:
        u = jwt.decode(cred.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Tu sesión venció. Inicia sesión de nuevo")
    with pool.connection() as c:
        r = c.execute("select rol, activo, debe_cambiar_clave, token_version from usuarios "
                      "where usuario=%s", (u["sub"],)).fetchone()
    if not r or not r["activo"]:
        raise HTTPException(401, "Tu usuario está desactivado")
    if int(u.get("ver", 0)) != int(r["token_version"]):
        raise HTTPException(401, "Tu sesión cambió. Inicia sesión de nuevo")
    if r["debe_cambiar_clave"] and req.url.path not in ("/api/cambiar-clave", "/api/yo"):
        raise HTTPException(403, "Debes cambiar tu contraseña antes de continuar")
    u["rol"] = r["rol"]
    return u


def auditar(c, u, accion, tabla, registro=None):
    c.execute("insert into auditoria(usuario,accion,tabla,registro_id) values (%s,%s,%s,%s)",
              (u["sub"], accion, tabla, registro))


class Login(BaseModel):
    usuario: str
    password: str


@app.post("/api/login")
def login(d: Login, req: Request):
    k = (d.usuario.lower(), req.client.host if req.client else "")
    fallos, t = INTENTOS.get(k, (0, 0))
    if time.time() - t > 900:
        fallos = 0
    if fallos >= 5:
        raise HTTPException(429, "Demasiados intentos. Espera 15 minutos")
    with pool.connection() as c:
        u = c.execute("select * from usuarios where lower(usuario)=%s and activo",
                      (d.usuario.lower(),)).fetchone()
    if not u or not bcrypt.checkpw(d.password.encode(), u["password_hash"].encode()):
        INTENTOS[k] = (fallos + 1, time.time())
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    INTENTOS.pop(k, None)
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=JWT_HORAS)
    token = jwt.encode({"sub": u["usuario"], "rol": u["rol"], "nombre": u["nombre"],
                        "ver": int(u["token_version"]), "exp": exp},
                       JWT_SECRET, algorithm="HS256")
    with pool.connection() as c:
        c.execute("update usuarios set ultimo_ingreso=now() where id=%s", (u["id"],))
    return {"token": token, "rol": u["rol"], "nombre": u["nombre"],
            "debe_cambiar_clave": bool(u.get("debe_cambiar_clave"))}


@app.get("/api/yo")
def yo(u=Depends(usuario_actual)):
    with pool.connection() as c:
        p = c.execute("select correo, cargo, telefono, ultimo_ingreso, preguntas_config_en "
                      "from usuarios where usuario=%s", (u["sub"],)).fetchone()
    return {"usuario": u["sub"], "rol": u["rol"], "nombre": u["nombre"],
            "correo": p["correo"] if p else None,
            "cargo": p["cargo"] if p else None,
            "telefono": p["telefono"] if p else None,
            "ultimo_ingreso": p["ultimo_ingreso"] if p else None,
            "preguntas_config": bool(p and p["preguntas_config_en"]),
            "modulos": sorted(MODULOS) if u["rol"] == "admin" else sorted(FUNC.get(u["rol"], set())),
            "es_admin": u["rol"] == "admin"}


@app.get("/api/salud")
def salud():
    with pool.connection() as c:
        c.execute("select 1")
    return {"ok": True}


# ---------- Verificación de registros y documentos ----------
VERIFICABLES = {"evaluaciones", "estudios_imagenes", "cirugias", "pt_sesiones", "formularios_proms",
                "referimientos", "autorizaciones_preauth", "procedimientos_paciente",
                "cargos_facturacion", "documentos", "ortesis_paciente", "recetas"}


class Verificar(BaseModel):
    tabla: str
    id: int
    verificado: bool = True


@app.post("/api/verificar")
def verificar(d: Verificar, u=Depends(usuario_actual)):
    """Marca o desmarca un registro como verificado por el usuario. Editarlo borra la verificación."""
    exigir(u, "escribir", d.tabla)
    if d.tabla not in VERIFICABLES:
        raise HTTPException(400, "Esta tabla no se verifica")
    quien = u["sub"] if d.verificado else None
    cuando = dt.datetime.now(dt.timezone.utc) if d.verificado else None
    with pool.connection() as c:
        r = c.execute(f"update {d.tabla} set verificado_por=%s, verificado_en=%s where id=%s returning id",
                      (quien, cuando, d.id)).fetchone()
        if not r:
            raise HTTPException(404, "Registro no encontrado")
        auditar(c, u, "verificar" if d.verificado else "quitar-verificacion", d.tabla, d.id)
    return {"ok": True}


class Archivo(BaseModel):
    mime: str = "application/octet-stream"
    datos_base64: str


@app.put("/api/documentos/{did}/archivo")
def documento_subir(did: int, d: Archivo, u=Depends(usuario_actual)):
    """Adjunta el archivo (hasta 8 MB) a un documento ya creado con /api/guardar."""
    exigir(u, "escribir", "documentos")
    try:
        datos = base64.b64decode(d.datos_base64, validate=True)
    except ValueError:
        raise HTTPException(400, "Archivo inválido")
    if len(datos) > 8_000_000:
        raise HTTPException(413, "El archivo supera 8 MB")
    with pool.connection() as c:
        r = c.execute("update documentos set archivo=%s, mime=%s, tamano=%s, "
                      "verificado_por=null, verificado_en=null where id=%s returning id",
                      (datos, d.mime, len(datos), did)).fetchone()
        if not r:
            raise HTTPException(404, "Documento no encontrado")
        auditar(c, u, "subir-archivo", "documentos", did)
    return {"ok": True}


@app.get("/api/documentos/{did}/archivo")
def documento_bajar(did: int, u=Depends(usuario_actual)):
    exigir(u, "leer", "documentos")
    with pool.connection() as c:
        r = c.execute("select nombre,mime,archivo from documentos where id=%s", (did,)).fetchone()
        if not r or r["archivo"] is None:
            raise HTTPException(404, "Documento sin archivo")
        auditar(c, u, "descargar", "documentos", did)
    return Response(bytes(r["archivo"]), media_type=r["mime"] or "application/octet-stream",
                    headers={"Content-Disposition": 'attachment; filename="documento"'})


# ---------- Imágenes médicas ----------
class Imagen(BaseModel):
    estudio_id: int
    mime: str = "image/jpeg"
    datos_base64: str


@app.post("/api/imagenes")
def imagen_subir(d: Imagen, u=Depends(usuario_actual)):
    """Sube una imagen (JPG, PNG o WebP, hasta 8 MB) y la liga a un estudio."""
    exigir(u, "escribir", "estudios_imagenes")
    if d.mime not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(400, "Solo se aceptan imágenes JPG, PNG o WebP")
    try:
        datos = base64.b64decode(d.datos_base64, validate=True)
    except ValueError:
        raise HTTPException(400, "Imagen inválida")
    if len(datos) > 8_000_000:
        raise HTTPException(413, "La imagen supera 8 MB")
    with pool.connection() as c:
        r = c.execute("insert into imagenes_estudio(estudio_id,mime,datos) values (%s,%s,%s) returning id",
                      (d.estudio_id, d.mime, datos)).fetchone()
        auditar(c, u, "subir", "imagenes_estudio", r["id"])
    return {"ok": True, "id": r["id"]}


@app.get("/api/imagenes/{iid}")
def imagen_ver(iid: int, u=Depends(usuario_actual)):
    """Devuelve los bytes de la imagen. El front-end la pide con el token y crea un blob para el visor."""
    exigir(u, "leer", "estudios_imagenes")
    with pool.connection() as c:
        r = c.execute("select mime,datos from imagenes_estudio where id=%s", (iid,)).fetchone()
        if not r:
            raise HTTPException(404, "Imagen no encontrada")
        auditar(c, u, "ver", "imagenes_estudio", iid)
    return Response(bytes(r["datos"]), media_type=r["mime"])


@app.delete("/api/imagenes/{iid}")
def imagen_borrar(iid: int, u=Depends(usuario_actual)):
    """Elimina una imagen del estudio. El estudio y su informe se conservan."""
    exigir(u, "escribir", "estudios_imagenes")
    with pool.connection() as c:
        r = c.execute("delete from imagenes_estudio where id=%s returning estudio_id", (iid,)).fetchone()
        if not r:
            raise HTTPException(404, "Imagen no encontrada")
        c.execute("update estudios_imagenes set miniatura=null where id=%s "
                  "and not exists (select 1 from imagenes_estudio where estudio_id=%s)",
                  (r["estudio_id"], r["estudio_id"]))
        auditar(c, u, "eliminar-imagen", "imagenes_estudio", iid)
    return {"ok": True, "estudio_id": r["estudio_id"]}


# ---------- Primer uso: registro del administrador ----------
class RegistroInicial(BaseModel):
    usuario: str
    nombre: str
    password: str


@app.get("/api/estado")
def estado():
    """El front-end muestra la pantalla de registro cuando aún no existe ningún usuario."""
    with pool.connection() as c:
        n = c.execute("select count(*) n from usuarios").fetchone()["n"]
    return {"requiere_registro": n == 0}


@app.post("/api/registro-inicial")
def registro_inicial(d: RegistroInicial):
    """Crea el primer administrador. Solo funciona mientras no exista ningún usuario."""
    _validar("admin", d.password)
    h = bcrypt.hashpw(d.password.encode(), bcrypt.gensalt()).decode()
    with pool.connection() as c:
        r = c.execute("insert into usuarios(usuario,nombre,rol,password_hash) "
                      "select %s::text,%s::text,'admin',%s::text "
                      "where not exists (select 1 from usuarios) returning id",
                      (d.usuario.lower(), d.nombre, h)).fetchone()
        if not r:
            raise HTTPException(409, "El sistema ya tiene usuarios. Pide al administrador que te cree una cuenta")
        auditar(c, {"sub": d.usuario.lower()}, "registro-inicial", "usuarios", r["id"])
    return {"ok": True}


# ---------- Administración (solo rol admin) ----------
def solo_admin(u=Depends(usuario_actual)):
    if u["rol"] != "admin":
        raise HTTPException(403, "Solo el administrador puede hacer esto")
    return u


class NuevoUsuario(BaseModel):
    usuario: str
    nombre: str
    rol: str
    password: str
    correo: str | None = None
    telefono: str | None = None
    cargo: str | None = None


class CambioUsuario(BaseModel):
    nombre: str | None = None
    rol: str | None = None
    activo: bool | None = None
    password: str | None = None
    debe_cambiar_clave: bool | None = None
    correo: str | None = None
    telefono: str | None = None
    cargo: str | None = None


def _validar(rol=None, password=None):
    if rol is not None and rol not in PERMISOS:
        raise HTTPException(400, "Rol inválido")
    if password is not None and len(password) < 10:
        raise HTTPException(400, "La contraseña debe tener al menos 10 caracteres")


@app.get("/api/usuarios")
def usuarios(u=Depends(solo_admin)):
    with pool.connection() as c:
        return {"usuarios": c.execute(
            "select u.id,u.usuario,u.nombre,u.rol,u.activo,u.debe_cambiar_clave,"
            "u.correo,u.telefono,u.cargo,u.ultimo_ingreso,"
            "(select count(*) from preguntas_seguridad p where p.usuario_id=u.id) preguntas "
            "from usuarios u order by u.usuario").fetchall()}


@app.post("/api/usuarios")
def usuario_nuevo(d: NuevoUsuario, u=Depends(solo_admin)):
    _validar(d.rol, d.password)
    h = bcrypt.hashpw(d.password.encode(), bcrypt.gensalt()).decode()
    with pool.connection() as c:
        if c.execute("select 1 from usuarios where lower(usuario)=%s", (d.usuario.lower(),)).fetchone():
            raise HTTPException(409, "Ese usuario ya existe")
        r = c.execute("insert into usuarios(usuario,nombre,rol,password_hash,correo,telefono,cargo,"
                      "debe_cambiar_clave) values (%s,%s,%s,%s,%s,%s,%s,true) returning id",
                      (d.usuario.lower(), d.nombre, d.rol, h, d.correo, d.telefono, d.cargo)).fetchone()
        auditar(c, u, "crear", "usuarios", r["id"])
    return {"ok": True, "id": r["id"]}


@app.patch("/api/usuarios/{uid}")
def usuario_editar(uid: int, d: CambioUsuario, u=Depends(solo_admin)):
    _validar(d.rol, d.password)
    campos = {}
    if d.nombre is not None:
        campos["nombre"] = d.nombre
    if d.rol is not None:
        campos["rol"] = d.rol
    if d.activo is not None:
        campos["activo"] = d.activo
    if d.debe_cambiar_clave is not None:
        campos["debe_cambiar_clave"] = d.debe_cambiar_clave
    if d.correo is not None:
        campos["correo"] = d.correo.strip() or None
    if d.telefono is not None:
        campos["telefono"] = d.telefono.strip() or None
    if d.cargo is not None:
        campos["cargo"] = d.cargo.strip() or None
    if d.password is not None:
        campos["password_hash"] = bcrypt.hashpw(d.password.encode(), bcrypt.gensalt()).decode()
        campos["debe_cambiar_clave"] = True
    if not campos:
        raise HTTPException(400, "Nada que cambiar")
    with pool.connection() as c:
        a = c.execute("select rol, activo from usuarios where id=%s", (uid,)).fetchone()
        if not a:
            raise HTTPException(404, "Usuario no encontrado")
        sigue_admin = (d.rol or a["rol"]) == "admin" and (a["activo"] if d.activo is None else d.activo)
        otros = c.execute("select count(*) n from usuarios where rol='admin' and activo and id<>%s",
                          (uid,)).fetchone()["n"]
        if not sigue_admin and not otros:
            raise HTTPException(400, "Debe quedar al menos un administrador activo")
        sql = [k + "=%s" for k in campos]
        # Cambiar la clave o desactivar invalida las sesiones abiertas.
        if d.password is not None or d.activo is False:
            sql.append("token_version=token_version+1")
        c.execute(f"update usuarios set {','.join(sql)} where id=%s",
                  list(campos.values()) + [uid])
        auditar(c, u, "editar", "usuarios", uid)
    return {"ok": True}


@app.delete("/api/usuarios/{uid}")
def usuario_borrar(uid: int, u=Depends(solo_admin)):
    """Elimina una cuenta. Nunca permite borrar la propia ni al último administrador activo."""
    with pool.connection() as c:
        a = c.execute("select usuario,rol,activo from usuarios where id=%s", (uid,)).fetchone()
        if not a:
            raise HTTPException(404, "Usuario no encontrado")
        if a["usuario"] == u["sub"]:
            raise HTTPException(400, "No puedes eliminar tu propia cuenta")
        if a["rol"] == "admin" and a["activo"]:
            otros = c.execute("select count(*) n from usuarios where rol='admin' and activo and id<>%s",
                              (uid,)).fetchone()["n"]
            if not otros:
                raise HTTPException(400, "Debe quedar al menos un administrador activo")
        c.execute("delete from usuarios where id=%s", (uid,))
        auditar(c, u, "eliminar", "usuarios", uid)
    return {"ok": True}


@app.post("/api/usuarios/{uid}/restablecer-clave")
def restablecer_clave(uid: int, u=Depends(solo_admin)):
    """Recuperación: genera una contraseña temporal (se muestra una sola vez) y obliga a cambiarla al entrar."""
    temporal = secrets.token_urlsafe(9)
    h = bcrypt.hashpw(temporal.encode(), bcrypt.gensalt()).decode()
    with pool.connection() as c:
        r = c.execute("update usuarios set password_hash=%s, debe_cambiar_clave=true, "
                      "token_version=token_version+1 where id=%s returning id",
                      (h, uid)).fetchone()
        if not r:
            raise HTTPException(404, "Usuario no encontrado")
        auditar(c, u, "restablecer-clave", "usuarios", uid)
    return {"ok": True, "clave_temporal": temporal}


@app.post("/api/usuarios/{uid}/desbloquear")
def usuario_desbloquear(uid: int, u=Depends(solo_admin)):
    """Libera los intentos fallidos de inicio de sesión de una cuenta."""
    with pool.connection() as c:
        a = c.execute("select usuario from usuarios where id=%s", (uid,)).fetchone()
        if not a:
            raise HTTPException(404, "Usuario no encontrado")
        c.execute("update usuarios set bloqueado_hasta=null where id=%s", (uid,))
        auditar(c, u, "desbloquear", "usuarios", uid)
    liberados = 0
    for k in list(INTENTOS):
        if k[0] == a["usuario"].lower():
            INTENTOS.pop(k, None)
            liberados += 1
    return {"ok": True, "liberados": liberados}


@app.post("/api/usuarios/{uid}/reset-seguridad")
def usuario_reset_seguridad(uid: int, u=Depends(solo_admin)):
    """Borra las preguntas de seguridad de un usuario para que las configure de nuevo."""
    with pool.connection() as c:
        r = c.execute("select id from usuarios where id=%s", (uid,)).fetchone()
        if not r:
            raise HTTPException(404, "Usuario no encontrado")
        c.execute("delete from preguntas_seguridad where usuario_id=%s", (uid,))
        c.execute("update usuarios set preguntas_config_en=null where id=%s", (uid,))
        auditar(c, u, "reset-preguntas", "usuarios", uid)
    return {"ok": True}


@app.get("/api/auditoria")
def ver_auditoria(limite: int = Query(60, ge=1, le=300), u=Depends(solo_admin)):
    with pool.connection() as c:
        filas = c.execute("select id,usuario,accion,tabla,registro_id,fecha from auditoria "
                          "order by id desc limit %s", (limite,)).fetchall()
    return {"eventos": filas}


@app.get("/api/admin/resumen")
def admin_resumen(u=Depends(solo_admin)):
    """Panel rápido del administrador: cuentas, seguridad y actividad reciente."""
    with pool.connection() as c:
        total = c.execute("select count(*) n from usuarios").fetchone()["n"]
        activos = c.execute("select count(*) n from usuarios where activo").fetchone()["n"]
        roles = {r["rol"]: r["n"] for r in c.execute(
            "select rol,count(*) n from usuarios group by rol order by rol").fetchall()}
        sin_preguntas = c.execute(
            "select count(*) n from usuarios u where u.activo and not exists "
            "(select 1 from preguntas_seguridad p where p.usuario_id=u.id)").fetchone()["n"]
        pendientes = c.execute("select count(*) n from usuarios where debe_cambiar_clave").fetchone()["n"]
        recup = c.execute("select count(*) n from recuperaciones where creado_en > now() - interval '7 days'"
                          ).fetchone()["n"]
        ultimos = c.execute("select id,usuario,accion,tabla,registro_id,fecha from auditoria "
                            "order by id desc limit 8").fetchall()
        datos = {t: c.execute(f"select count(*) n from {t}").fetchone()["n"]
                 for t in ("pacientes", "citas", "cirugias", "estudios_imagenes")}
    return {"usuarios": total, "activos": activos, "roles": roles,
            "sin_preguntas": sin_preguntas, "deben_cambiar": pendientes,
            "recuperaciones_7d": recup, "ultimos": ultimos, "datos": datos}


class CambioClave(BaseModel):
    actual: str
    nueva: str


@app.post("/api/cambiar-clave")
def cambiar_clave(d: CambioClave, u=Depends(usuario_actual)):
    """Cada usuario cambia su propia contraseña (obligatorio tras un restablecimiento)."""
    _validar(None, d.nueva)
    if d.actual == d.nueva:
        raise HTTPException(400, "Elige una contraseña distinta a la actual")
    with pool.connection() as c:
        r = c.execute("select nombre,rol,password_hash,token_version from usuarios where usuario=%s",
                      (u["sub"],)).fetchone()
        if not bcrypt.checkpw(d.actual.encode(), r["password_hash"].encode()):
            raise HTTPException(400, "La contraseña actual no es correcta")
        ver = int(r["token_version"]) + 1
        c.execute("update usuarios set password_hash=%s, debe_cambiar_clave=false, token_version=%s "
                  "where usuario=%s", (bcrypt.hashpw(d.nueva.encode(), bcrypt.gensalt()).decode(),
                                       ver, u["sub"]))
        auditar(c, u, "cambiar-clave", "usuarios")
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=JWT_HORAS)
    token = jwt.encode({"sub": u["sub"], "rol": r["rol"], "nombre": r["nombre"], "ver": ver, "exp": exp},
                       JWT_SECRET, algorithm="HS256")
    return {"ok": True, "token": token}


# ---------- Preguntas de seguridad y recuperación de contraseña ----------
PREGUNTAS_SEGURIDAD = [
    "¿Cuál es el nombre de tu primera mascota?",
    "¿En qué ciudad naciste?",
    "¿Cuál es el nombre de tu madre?",
    "¿Cuál fue el nombre de tu primer colegio?",
    "¿Cuál es tu comida favorita?",
    "¿Cuál es el nombre de tu mejor amigo de la infancia?",
    "¿Cuál fue el modelo de tu primer vehículo?",
    "¿En qué hospital o clínica trabajaste por primera vez?",
    "¿Cuál es el nombre de tu abuelo o abuela favorito?",
    "¿Cuál es tu equipo deportivo favorito?",
]


def normalizar_respuesta(t: str) -> str:
    """Compara respuestas sin importar mayúsculas, tildes ni espacios repetidos."""
    t = unicodedata.normalize("NFKD", str(t or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(t.lower().strip().split())


class PreguntaSeguridad(BaseModel):
    pregunta: str
    respuesta: str


class GuardarSeguridad(BaseModel):
    actual: str
    preguntas: list[PreguntaSeguridad]


class RecuperarInicio(BaseModel):
    usuario: str


class RespuestaRecuperacion(BaseModel):
    id: int
    respuesta: str


class RecuperarVerificar(BaseModel):
    token: str
    respuestas: list[RespuestaRecuperacion]


class RecuperarClave(BaseModel):
    token: str
    nueva: str


RECUPERACION: dict = {}  # (usuario, ip) -> (fallos, último_intento)


def _limitar_recuperacion(k) -> int:
    fallos, t = RECUPERACION.get(k, (0, 0))
    if time.time() - t > 900:
        fallos = 0
    if fallos >= 6:
        raise HTTPException(429, "Demasiados intentos. Espera 15 minutos")
    return fallos


@app.get("/api/seguridad")
def seguridad_ver(u=Depends(usuario_actual)):
    with pool.connection() as c:
        uid = c.execute("select id from usuarios where usuario=%s", (u["sub"],)).fetchone()["id"]
        filas = c.execute("select id,orden,pregunta from preguntas_seguridad "
                          "where usuario_id=%s order by orden", (uid,)).fetchall()
    return {"configurado": len(filas) >= 3, "preguntas": filas,
            "catalogo": PREGUNTAS_SEGURIDAD}


@app.put("/api/seguridad")
def seguridad_guardar(d: GuardarSeguridad, u=Depends(usuario_actual)):
    """Configura 3 preguntas de seguridad. Las respuestas se guardan con bcrypt."""
    if len(d.preguntas) < 3:
        raise HTTPException(400, "Elige al menos 3 preguntas de seguridad")
    preguntas = [p.pregunta.strip() for p in d.preguntas]
    if len(set(preguntas)) != len(preguntas):
        raise HTTPException(400, "No repitas la misma pregunta")
    if any(len(normalizar_respuesta(p.respuesta)) < 3 for p in d.preguntas):
        raise HTTPException(400, "Las respuestas deben tener al menos 3 caracteres")
    with pool.connection() as c:
        r = c.execute("select id,password_hash from usuarios where usuario=%s", (u["sub"],)).fetchone()
        if not bcrypt.checkpw(d.actual.encode(), r["password_hash"].encode()):
            raise HTTPException(400, "La contraseña actual no es correcta")
        c.execute("delete from preguntas_seguridad where usuario_id=%s", (r["id"],))
        for i, p in enumerate(d.preguntas, 1):
            h = bcrypt.hashpw(normalizar_respuesta(p.respuesta).encode(), bcrypt.gensalt()).decode()
            c.execute("insert into preguntas_seguridad(usuario_id,orden,pregunta,respuesta_hash) "
                      "values (%s,%s,%s,%s)", (r["id"], i, p.pregunta.strip(), h))
        c.execute("update usuarios set preguntas_config_en=now() where id=%s", (r["id"],))
        auditar(c, u, "configurar-preguntas", "usuarios", r["id"])
    return {"ok": True}


@app.post("/api/recuperar/iniciar")
def recuperar_iniciar(d: RecuperarInicio, req: Request):
    ip = req.client.host if req.client else ""
    usuario = d.usuario.lower().strip()
    k = (usuario, ip)
    fallos = _limitar_recuperacion(k)
    with pool.connection() as c:
        usr = c.execute("select id,usuario,activo,token_version from usuarios "
                        "where lower(usuario)=%s", (usuario,)).fetchone()
        filas = c.execute("select id,orden,pregunta from preguntas_seguridad "
                          "where usuario_id=%s order by orden", (usr["id"],)).fetchall() if usr else []
    if not usr or not usr["activo"] or len(filas) < 3:
        RECUPERACION[k] = (fallos + 1, time.time())
        with pool.connection() as c:
            c.execute("insert into recuperaciones(usuario,ip,exito) values (%s,%s,false)", (usuario, ip))
        raise HTTPException(400, "No pudimos iniciar la recuperación. Verifica el usuario o pide ayuda al administrador")
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10)
    token = jwt.encode({"sub": usr["usuario"], "purpose": "recuperar",
                        "ids": [f["id"] for f in filas], "ver": int(usr["token_version"]), "exp": exp},
                       JWT_SECRET, algorithm="HS256")
    return {"token": token, "usuario": usr["usuario"],
            "preguntas": [{"id": f["id"], "pregunta": f["pregunta"]} for f in filas]}


@app.post("/api/recuperar/verificar")
def recuperar_verificar(d: RecuperarVerificar, req: Request):
    ip = req.client.host if req.client else ""
    try:
        p = jwt.decode(d.token, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(400, "La recuperación venció. Empieza de nuevo")
    if p.get("purpose") != "recuperar":
        raise HTTPException(400, "Enlace de recuperación inválido")
    k = (p["sub"].lower(), ip)
    fallos = _limitar_recuperacion(k)
    with pool.connection() as c:
        usr = c.execute("select id,activo,token_version from usuarios where usuario=%s",
                        (p["sub"],)).fetchone()
        if not usr or not usr["activo"] or int(usr["token_version"]) != int(p.get("ver", -1)):
            raise HTTPException(400, "La recuperación ya no es válida. Empieza de nuevo")
        filas = c.execute("select id,respuesta_hash from preguntas_seguridad "
                          "where usuario_id=%s and id = any(%s)",
                          (usr["id"], p.get("ids") or [])).fetchall()
    respuestas = {int(r.id): r.respuesta for r in d.respuestas}
    ok = len(filas) >= 3 and all(
        int(f["id"]) in respuestas and bcrypt.checkpw(
            normalizar_respuesta(respuestas[int(f["id"])]).encode(), f["respuesta_hash"].encode())
        for f in filas)
    if not ok:
        RECUPERACION[k] = (fallos + 1, time.time())
        with pool.connection() as c:
            c.execute("insert into recuperaciones(usuario,ip,exito) values (%s,%s,false)", (p["sub"], ip))
        raise HTTPException(400, "Alguna respuesta no coincide. Revisa e intenta de nuevo")
    RECUPERACION.pop(k, None)
    with pool.connection() as c:
        c.execute("insert into recuperaciones(usuario,ip,exito) values (%s,%s,true)", (p["sub"], ip))
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=15)
    token = jwt.encode({"sub": p["sub"], "purpose": "restablecer",
                        "ver": int(usr["token_version"]), "exp": exp}, JWT_SECRET, algorithm="HS256")
    return {"ok": True, "token": token}


@app.post("/api/recuperar/restablecer")
def recuperar_restablecer(d: RecuperarClave):
    _validar(None, d.nueva)
    try:
        p = jwt.decode(d.token, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(400, "La recuperación venció. Empieza de nuevo")
    if p.get("purpose") != "restablecer":
        raise HTTPException(400, "Enlace de recuperación inválido")
    with pool.connection() as c:
        usr = c.execute("select id,activo,token_version from usuarios where usuario=%s",
                        (p["sub"],)).fetchone()
        if not usr or not usr["activo"] or int(usr["token_version"]) != int(p.get("ver", -1)):
            raise HTTPException(400, "La recuperación ya no es válida. Empieza de nuevo")
        c.execute("update usuarios set password_hash=%s, debe_cambiar_clave=false, "
                  "token_version=token_version+1 where id=%s",
                  (bcrypt.hashpw(d.nueva.encode(), bcrypt.gensalt()).decode(), usr["id"]))
        auditar(c, {"sub": p["sub"]}, "recuperar-clave", "usuarios", usr["id"])
    return {"ok": True, "usuario": p["sub"]}


class Funciones(BaseModel):
    rol: str
    modulos: list[str]


ROLES_DESC = {
    "admin": "Control total: usuarios, perfiles, seguridad, auditoría y todas las secciones clínicas.",
    "medico": "Historia clínica completa: evaluaciones, cirugías, estudios, recetas y autorizaciones.",
    "enfermeria": "Apoyo clínico: consulta el expediente y adjunta estudios, documentos y órtesis.",
    "secretaria": "Recepción y gestión: agenda, pacientes, documentos, referimientos, cobros y recetas.",
    "fisio": "Rehabilitación: sesiones, PROMs, órtesis y consulta de documentos y estudios.",
    "facturacion": "Cobros y autorizaciones: cargos, tarifario y preautorizaciones, sin editar la clínica.",
}


@app.get("/api/funciones")
def funciones(u=Depends(solo_admin)):
    return {"modulos": list(MODULOS),
            "roles": {r: sorted(FUNC.get(r, set())) for r in PERMISOS if r != "admin"},
            "descripciones": ROLES_DESC,
            "recomendados": {r: sorted(ms) for r, ms in FUNC_INICIAL.items()}}


@app.put("/api/funciones")
def funciones_guardar(d: Funciones, u=Depends(solo_admin)):
    """Agrega o quita funciones a un rol. Se aplica de inmediato a la API y al menú."""
    if d.rol not in PERMISOS or d.rol == "admin":
        raise HTTPException(400, "Rol inválido")
    if any(x not in MODULOS for x in d.modulos):
        raise HTTPException(400, "Función desconocida")
    with pool.connection() as c:
        c.execute("delete from funciones_rol where rol=%s", (d.rol,))
        for x in set(d.modulos):
            c.execute("insert into funciones_rol(rol,modulo) values (%s,%s)", (d.rol, x))
        auditar(c, u, "funciones", "funciones_rol")
    FUNC[d.rol] = set(d.modulos)
    return {"ok": True}


@app.post("/api/funciones/restaurar")
def funciones_restaurar(u=Depends(solo_admin)):
    """Restaura los accesos recomendados de cada rol (no toca al administrador)."""
    with pool.connection() as c:
        for r, ms in FUNC_INICIAL.items():
            c.execute("delete from funciones_rol where rol=%s", (r,))
            for mod in sorted(ms):
                c.execute("insert into funciones_rol(rol,modulo) values (%s,%s)", (r, mod))
        auditar(c, u, "restaurar-funciones", "funciones_rol")
    FUNC.clear()
    for r, ms in FUNC_INICIAL.items():
        FUNC[r] = set(ms)
    return {"ok": True, "roles": {r: sorted(ms) for r, ms in FUNC_INICIAL.items()}}


# ---------- Datos ----------
@app.get("/api/todo")
def todo(u=Depends(usuario_actual)):
    """Todo lo que el rol puede leer, en una sola llamada (lo usa el front-end al entrar)."""
    out: dict = {}
    with pool.connection() as c:
        for t, cols in TABLAS.items():
            if not puede(u["rol"], "leer", t):
                continue
            extra = ", (archivo is not null) as tiene" if t == "documentos" else ""
            if t in VERIFICABLES:
                extra += ", verificado_por, verificado_en"
            out[t] = c.execute(f"select id,{','.join(cols)}{extra} from {t} order by id").fetchall()
        if puede(u["rol"], "leer", "estudios_imagenes"):
            out["_imagenes"] = c.execute(
                "select id, estudio_id from imagenes_estudio order by id").fetchall()
    return out


@app.get("/api/medicos")
def medicos(u=Depends(usuario_actual)):
    """Nombres de los médicos activos, para los desplegables del front-end."""
    with pool.connection() as c:
        r = c.execute("select nombre from usuarios where rol='medico' and activo "
                      "order by nombre").fetchall()
    return {"medicos": [x["nombre"] for x in r]}


@app.get("/api/datos")
def datos(tabla: str | None = None, q: str = "", pagina: int = Query(1, ge=1),
          limite: int = Query(25, ge=1, le=100), u=Depends(usuario_actual)):
    """Sin `tabla`: conteos por tabla. Con `tabla`: página de registros (q filtra pacientes)."""
    with pool.connection() as c:
        if not tabla:
            return {"conteos": {t: c.execute(f"select count(*) n from {t}").fetchone()["n"]
                                for t in TABLAS if puede(u["rol"], "leer", t)}}
        exigir(u, "leer", tabla)
        where, args = "", []
        if q and tabla == "pacientes":
            where, args = " where nombre ilike %s or cedula ilike %s", [f"%{q}%"] * 2
        total = c.execute(f"select count(*) n from {tabla}{where}", args).fetchone()["n"]
        cols = ",".join(["id"] + TABLAS[tabla])
        filas = c.execute(f"select {cols} from {tabla}{where} order by id desc limit %s offset %s",
                          args + [limite, (pagina - 1) * limite]).fetchall()
    return {"tabla": tabla, "total": total, "pagina": pagina, "filas": filas}


@app.delete("/api/datos/{tabla}/{rid}")
def borrar(tabla: str, rid: int, u=Depends(usuario_actual)):
    """Elimina un registro. Borrar un paciente arrastra todo su expediente."""
    exigir(u, "escribir", tabla)
    with pool.connection() as c:
        r = c.execute(f"delete from {tabla} where id=%s returning id", (rid,)).fetchone()
        if not r:
            raise HTTPException(404, "Registro no encontrado")
        auditar(c, u, "eliminar", tabla, rid)
    return {"ok": True}


@app.get("/api/cedula/{cedula}")
def cedula_lookup(cedula: str, u=Depends(usuario_actual)):
    """Consulta opcional de cedula. Devuelve validacion y, si el proveedor lo soporta, el nombre."""
    num = "".join(ch for ch in (cedula or "") if ch.isdigit())
    if len(num) < 9:
        raise HTTPException(400, "Cedula invalida")
    provider = os.getenv("CEDULA_API_PROVIDER", "").strip().lower()
    if provider == "verifik":
        token = os.getenv("VERIFIK_TOKEN", "").strip()
        if not token:
            return {"valid": None, "nombre": None, "fuente": "verifik", "mensaje": "Falta VERIFIK_TOKEN"}
        url = "https://api.verifik.co/v2/do/cedula?documentType=CIE&documentNumber=" + num
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            d = data.get("data") or {}
            nombre = d.get("fullName") or " ".join(filter(None, [d.get("firstName"), d.get("lastName")]))
            return {"valid": True, "nombre": nombre, "fuente": "verifik"}
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"valid": False, "nombre": None, "fuente": "verifik", "mensaje": "No encontrada"}
            return {"valid": None, "nombre": None, "fuente": "verifik", "mensaje": "Error " + str(e.code)}
        except Exception as e:
            return {"valid": None, "nombre": None, "fuente": "verifik", "mensaje": str(e)}
    if provider == "ogtic":
        key = os.getenv("OGTIC_API_KEY", "").strip()
        if not key:
            return {"valid": None, "nombre": None, "fuente": "ogtic", "mensaje": "Falta OGTIC_API_KEY"}
        url = "https://api.digital.gob.do/v3/citizens/" + num + "/validate"
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + key, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return {"valid": bool(data.get("valid")), "nombre": None, "fuente": "ogtic"}
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"valid": False, "nombre": None, "fuente": "ogtic", "mensaje": "No encontrada"}
            return {"valid": None, "nombre": None, "fuente": "ogtic", "mensaje": "Error " + str(e.code)}
        except Exception as e:
            return {"valid": None, "nombre": None, "fuente": "ogtic", "mensaje": str(e)}
    return {"valid": None, "nombre": None, "fuente": "none", "mensaje": "Sin proveedor configurado. Define CEDULA_API_PROVIDER y el token correspondiente."}


@app.get("/api/paciente/{pid}")
def paciente(pid: int, u=Depends(usuario_actual)):
    """Expediente: el paciente y sus registros de las tablas que el rol puede leer."""
    exigir(u, "leer", "pacientes")
    with pool.connection() as c:
        p = c.execute(f"select id,{','.join(TABLAS['pacientes'])} from pacientes where id=%s",
                      (pid,)).fetchone()
        if not p:
            raise HTTPException(404, "Paciente no encontrado")
        rel = {t: c.execute(f"select id,{','.join(cols)} from {t} where paciente_id=%s order by id desc",
                            (pid,)).fetchall()
               for t, cols in TABLAS.items()
               if t != "pacientes" and "paciente_id" in cols and puede(u["rol"], "leer", t)}
        auditar(c, u, "ver", "pacientes", pid)
    return {"paciente": p, **rel}


class Guardar(BaseModel):
    tabla: str
    datos: dict
    id: int | None = None  # con id edita; sin id crea


@app.post("/api/guardar")
def guardar(g: Guardar, u=Depends(usuario_actual)):
    exigir(u, "escribir", g.tabla)
    cols = [k for k in g.datos if k in TABLAS[g.tabla]]
    if not cols:
        raise HTTPException(400, "No hay campos válidos para guardar")
    vals = [Jsonb(g.datos[k]) if k in JSONB else g.datos[k] for k in cols]
    with pool.connection() as c:
        if g.id:
            r = c.execute(f"update {g.tabla} set {','.join(k + '=%s' for k in cols)} "
                          f"{', verificado_por=null, verificado_en=null' if g.tabla in VERIFICABLES else ''} "
                          "where id=%s returning id", vals + [g.id]).fetchone()
            if not r:
                raise HTTPException(404, "Registro no encontrado")
            accion = "editar"
        else:
            r = c.execute(f"insert into {g.tabla}({','.join(cols)}) "
                          f"values ({','.join(['%s'] * len(cols))}) returning id", vals).fetchone()
            accion = "crear"
        auditar(c, u, accion, g.tabla, r["id"])
    return {"ok": True, "id": r["id"]}


@app.get("/api/buscar")
def buscar(q: str = Query(min_length=2), u=Depends(usuario_actual)):
    exigir(u, "leer", "pacientes")
    with pool.connection() as c:
        r = c.execute("select id,nombre,cedula,diagnostico from pacientes "
                      "where nombre ilike %s or cedula ilike %s order by nombre limit 10",
                      [f"%{q}%"] * 2).fetchall()
    return {"pacientes": r}


KPIS = {
    "citas_hoy": ("citas", "fecha = current_date"),
    "cirugias_programadas": ("cirugias", "estado = 'Programada'"),
    "estudios_por_revisar": ("estudios_imagenes", "estado = 'Por revisar'"),
    "proms_bajos": ("formularios_proms", "puntaje < 50"),
    "preauth_pendientes": ("autorizaciones_preauth", "estado in ('Por solicitar','Enviada')"),
    "cobros_pendientes": ("cargos_facturacion", "estado = 'Pendiente'"),
    "referimientos_sin_responder": ("referimientos", "estado = 'Pendiente'"),
}


@app.get("/api/dashboard")
def dashboard(u=Depends(usuario_actual)):
    """Todos los indicadores del rol en una sola llamada."""
    with pool.connection() as c:
        return {k: c.execute(f"select count(*) n from {t} where {w}").fetchone()["n"]
                for k, (t, w) in KPIS.items() if puede(u["rol"], "leer", t)}


# Si existe la carpeta `static/`, sirve el front-end desde el mismo servidor.
if (AQUI / "static").is_dir():
    app.mount("/", StaticFiles(directory=AQUI / "static", html=True), name="web")


def crear_usuario(usuario, rol, nombre):
    if rol not in PERMISOS:
        sys.exit("Rol inválido. Usa: " + ", ".join(PERMISOS))
    clave = getpass.getpass("Contraseña (mínimo 10 caracteres): ")
    if len(clave) < 10:
        sys.exit("La contraseña es demasiado corta")
    h = bcrypt.hashpw(clave.encode(), bcrypt.gensalt()).decode()
    pool.open(wait=True, timeout=30)
    aplicar_schema()
    with pool.connection() as c:
        c.execute("insert into usuarios(usuario,nombre,rol,password_hash) values (%s,%s,%s,%s) "
                  "on conflict (usuario) do update set nombre=excluded.nombre, rol=excluded.rol, "
                  "password_hash=excluded.password_hash, activo=true", (usuario, nombre, rol, h))
    print("Usuario listo:", usuario, f"({rol})")


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "crear-usuario":
        crear_usuario(sys.argv[2], sys.argv[3], " ".join(sys.argv[4:]) or sys.argv[2])
    else:
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "3000")))
