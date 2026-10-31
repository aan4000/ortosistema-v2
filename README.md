# OrtoSistema: backend en Python

FastAPI + PostgreSQL (Neon). Login con JWT, permisos por rol aplicados en el servidor, auditoría de accesos y cambios.

Esta es la versión 2 (`ortosistema-v2`). El front-end se sirve desde el mismo servidor en `/` y la base de datos es la base `ortosistema` del proyecto Neon `ortosistema-v2` (PostgreSQL 18, región `aws-us-east-2`). Se migraron los datos del sistema anterior.

## Puesta en marcha

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # completa DATABASE_URL y JWT_SECRET
export $(grep -v '^#' .env | xargs)                 # Windows: define las variables a mano
python main.py crear-usuario dr.nombre medico "Dr. Nombre"   # pide la contraseña
python main.py                                      # http://localhost:3000/docs
```

Roles: `admin`, `medico`, `secretaria`, `fisio`.

## Endpoints

| Método | Ruta | Uso |
|---|---|---|
| POST | `/api/login` | `{usuario, password}` → `{token, rol, nombre}` |
| GET | `/api/yo` | Usuario de la sesión |
| GET | `/api/salud` | Comprobación de vida (despierta Render) |
| GET | `/api/datos` | Sin `tabla`: conteos. Con `tabla`, `q`, `pagina`, `limite`: registros |
| GET | `/api/paciente/{id}` | Expediente completo según el rol |
| POST | `/api/guardar` | `{tabla, datos, id?}`: crea o edita |
| GET | `/api/buscar?q=` | Búsqueda de pacientes |
| GET | `/api/dashboard` | Indicadores del rol en una llamada |

Primer uso: `GET /api/estado` dice si falta crear el administrador y `POST /api/registro-inicial` (`{usuario, nombre, password}`) lo crea. Solo funciona mientras no exista ningún usuario; después, el administrador crea las demás cuentas. La línea de comandos `python main.py crear-usuario` sigue disponible.

Solo administrador:

| Método | Ruta | Uso |
|---|---|---|
| GET / POST | `/api/usuarios` | Listar y crear usuarios (contraseña de 10+ caracteres) |
| PATCH | `/api/usuarios/{id}` | Cambiar nombre, rol, estado o contraseña. Siempre queda un administrador activo |
| GET / PUT | `/api/funciones` | Ver y cambiar las funciones de cada rol: `{rol, modulos:[...]}` |

`/api/yo` devuelve la lista de `modulos` del usuario para armar el menú. Los cambios de funciones, rol o estado se aplican en la siguiente llamada. Si corres varios procesos, reinícialos tras cambiar funciones (se guardan en memoria).

Todas, salvo login y salud, piden `Authorization: Bearer <token>`.

## Conectar el front-end

1. Copia tu `index.html` a una carpeta `static/` junto a `main.py`: el servidor la sirve en `/`.
2. Si el front-end vive en otro dominio, agrégalo a `CORS_ORIGINS`.
3. Desde el front-end: `POST /api/login`, guarda el token y envíalo en cada llamada.

## Despliegue en Render

- La base vive en Neon: proyecto `ortosistema-v2`, base `ortosistema`, región `aws-us-east-2`. La cadena completa va en `DATABASE_URL` (local y Render); no se sube al repositorio.
- Desplegado en Render: https://ortosistema-v2.onrender.com (`/api/salud` como health check; plan free, se duerme tras ~15 min sin uso).
- El repositorio incluye `render.yaml`: crea un servicio web `ortosistema-v2` en la región `ohio` (misma que Neon `us-east-2`), con `AUTO_SCHEMA=1` y `JWT_HORAS=8`.
- Build: `pip install -r requirements.txt`
- Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- En Render define `DATABASE_URL` (la cadena de Neon) y deja que `JWT_SECRET` se genere. No subas `.env` al repositorio.
- El front-end queda disponible en la raíz del servicio (`/`) y la documentación de la API en `/docs`.

## Antes de usar datos reales

- `schema.sql` solo crea tablas que no existan. Si tu base ya tiene tablas con otras columnas, ajusta el diccionario `TABLAS` de `main.py` (es la única lista de tablas y columnas permitidas) o migra con `alter table`.
- Usa HTTPS y un `JWT_SECRET` largo. No pongas credenciales en la URL.
- Activa las copias de seguridad en Neon.

## Catálogo de procedimientos (tarifario)

La tabla `tarifario` (`codigo`, `nombre`, `fuente`, `precio`) se lee y escribe con `/api/datos?tabla=tarifario` y `/api/guardar`. Carga ahí los precios aprobados por tu fuente (SDOT, aseguradora o tarifa propia). Cada cargo de `cargos_facturacion` guarda además el `medico` responsable.

## Imágenes médicas y procedimientos

- `POST /api/imagenes` recibe `{estudio_id, mime, datos_base64}` (JPG, PNG o WebP, hasta 8 MB) y `GET /api/imagenes/{id}` devuelve la imagen. Una etiqueta `<img>` no envía el token, así que el front-end la pide con `fetch` y el encabezado `Authorization`, y muestra el resultado como `blob:` en el visor.
- Los procedimientos asignados a cada paciente van en `procedimientos_paciente`, y el catálogo en `tarifario` (ahora con `categoria`).
- Si ya tenías el sistema en marcha, entra como administrador a **Administración → Funciones por rol** y activa **Procedimientos** para los roles que lo necesiten.

## Paciente activo, verificación y documentos

- El paciente activo es una función del front-end: la API ya trabaja por paciente (`/api/paciente/{id}` y el filtro `paciente_id`), así que no necesita cambios.
- `POST /api/verificar` (`{tabla, id, verificado}`) marca un registro como verificado por el usuario. Editarlo con `/api/guardar` borra la verificación.
- Documentos: crea el registro con `/api/guardar` (tabla `documentos`), luego `PUT /api/documentos/{id}/archivo` sube el archivo en base64 (hasta 8 MB) y `GET` lo descarga. Para activar la sección, ve a **Administración → Funciones por rol**.

## Contraseñas y órtesis

- `POST /api/usuarios/{id}/restablecer-clave` (solo administrador) genera una contraseña temporal y la devuelve una sola vez. Mientras el usuario no la cambie con `POST /api/cambiar-clave` (`{actual, nueva}`), la API solo le permite `/api/yo` y ese endpoint. `/api/login` devuelve `debe_cambiar_clave`.
- Cambiar la contraseña de un usuario con `PATCH /api/usuarios/{id}` también le exige cambiarla en su próximo ingreso.
- Las órtesis asignadas van en `ortesis_paciente`. El catálogo de órtesis es una lista fija del front-end. Activa **Órtesis** en Administración → Funciones por rol si ya tenías el sistema en marcha.

## Sincronización del front-end (`static/index.html`)

| Método | Ruta | Uso |
|---|---|---|
| GET | `/api/todo` | Todo lo que el usuario puede ver en una sola llamada: pacientes, citas, evaluaciones, estudios, documentos, órtesis, procedimientos, cargos, tarifario y usuarios. Incluye `verificado_por`/`verificado_en`, `documentos.tiene` y `_imagenes` |
| GET | `/api/medicos` | Lista de médicos para los selectores de cita y evaluación |
| DELETE | `/api/datos/{tabla}/{id}` | Borra un registro (respeta el mismo control de rol que `/api/guardar`) |
| GET / PUT | `/api/documentos/{id}/archivo` | Descarga (`GET`) o reemplaza (`PUT`, base64) el archivo de un documento |
| POST | `/api/verificar` | `{tabla, id, verificado}`: marca o quita la verificación |

- El front-end guarda el token en `localStorage` y llama a la API en cada cambio; no hay copia local de los datos.
- Columnas nuevas (se agregan solas con `add column if not exists` al arrancar): `documentos.archivo`, `mime`, `tamano`; `verificado_por`/`verificado_en` en evaluaciones, estudios, cirugías, sesiones de terapia, formularios PROMs, referimientos, autorizaciones, cargos, documentos, procedimientos y órtesis; `medico` en citas, evaluaciones, cargos y procedimientos; `tarifario.categoria`. El campo `documentos.tiene` no se guarda: lo calcula `/api/todo`.
- Módulos nuevos (`ortesis`, `documentos`) se activan una sola vez por rol con los marcadores de `MODULOS`/`FUNC_INICIAL`; después se editan desde **Administración → Funciones por rol**.
- La transición entre secciones (1 s) y el desplazamiento suave se desactivan con `prefers-reduced-motion`.
