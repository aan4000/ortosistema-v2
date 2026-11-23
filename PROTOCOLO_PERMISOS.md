# Protocolo de visibilidad por rol (pestañas e iconos)

## Regla de oro
**Todo elemento de navegación (pestañas del expediente del paciente e iconos de la barra lateral) se renderiza únicamente si el rol del usuario autenticado tiene acceso al módulo correspondiente.** Si se remueve un permiso, el elemento desaparece automáticamente en el próximo render, sin recargar ni intervenir manualmente.

**Nunca se oculta con CSS** (`display:none`). Se **omite el elemento** en el momento de generar el HTML. Así no queda "rastro" clicable ni accesible por teclado.

## Fuente única de verdad
Existe una sola tabla en `static/index.html` que define la relación:

```js
const PERMISO_TAB = {
  resumen:         ["pacientes"],
  evaluacion:      ["pacientes"],
  recetas:         ["recetas"],
  citas:           ["agenda"],
  clinica:         ["estudios", "pacientes"],
  procedimientos:  ["procedimientos"],
  ortasis:         ["ortesis"],
  rehab:           ["rehab"],
  gestion:         ["referimientos", "autorizaciones", "facturacion"],
  documentos:      ["documentos"]
};
const tabVisible = k => {
  const req = PERMISO_TAB[k];
  if (!req) return true;
  return req.some(m => can(m));
};
```

- `can(m)` es la única función que decide si un módulo está permitido:
  - `admin` → siempre `true` para todo.
  - otros roles → `true` solo si el módulo está en `S.user.modulos` (o en el mapa por defecto del rol `DB.PM`).
- Para agregar o quitar una pestaña, **solo se edita `PERMISO_TAB`**. No hace falta tocar el HTML de la pestaña ni el icono.

## dónde se aplica

| Lugar | Función | Comportamiento |
|---|---|---|
| Barra lateral (iconos) | `menu(a)` | Filtra `M` y `AD` con `can(k)`. El grupo "Atención clínica" solo aparece si hay algún módulo visible. El grupo "Gestión"/"Administrativo" solo aparece si hay módulos de gestión permitidos. |
| Pestañas del paciente | `vExp(id, tab)` | Construye `T` con `.filter(([k]) => tabVisible(k))`. Orden: Resumen → Evaluación → **Estudios e imágenes** → Recetas → Citas → **Procedimientos** → Órtesis → Clínica → Rehabilitación → Gestión → Documentos. |
| Botones Anterior/Siguiente | `_tabOrder` | Usa el mismo `.filter(tabVisible)`, por lo que la secuencia salta las pestañas sin acceso. `_tabRuta()` garantiza que **siempre** se permanece en `p-<id>-<pestaña>`. |
| Ruta directa | `draw()` | Si alguien escribe `p-71-ortasis` y el rol no tiene `ortesis`, se normaliza a la primera pestaña visible (Resumen). |
| Registro de paciente | `gp()` | Al crear un paciente (o elegir "Crear como nuevo" ante un duplicado) se navega directo a `p-<id>-evaluacion`. El aviso posterior ofrece continuar a Citas. |
| Guardar evaluación | `fEval()` / atajo "Nueva evaluación" | Al guardar, navega automáticamente a `p-<id>-estudios` (Estudios e imágenes). |
| Guardar receta | `fRx()` | Al guardar (nueva, merge o edición) desde el expediente, navega automáticamente a `p-<id>-procedimientos`. Desde la sección principal de Recetas se queda en ella. |
| Pestañas Órtesis y Recetas | `vExp()` | Muestran el contenido de esa sección **dentro del expediente** (listado filtrado al paciente + acciones "Asignar órtesis" / "Nueva receta"). No existe botón que saque al usuario de la sección. |
| Pestaña Órtesis (clave `ortasis`) | `B2` / `TD` | **Correspondencia obligatoria:** la pestaña usa la clave histórica `ortasis` (con "a"), mientras la vista y la descripción usan `ortesis` (con "e"). Se definen los alias `B2.ortasis = B2.ortesis` y `TD.ortasis = TD.ortesis` para que la pestaña muestre Órtesis y no caiga en el fallback de Resumen. **Toda pestaña nueva debe tener su clave exacta en `B2` y en `TD`**; si no, `vExp` mostrará Resumen silenciosamente. |
| Acceso a sección | `draw()` | Bloquea rutas completas (`can(a)`) y redirige a `inicio` si no hay permiso. |

## Algoritmo de navegación (una sección lleva a la otra)

**Regla:** el expediente del paciente es una sección autocontenida. Todas sus pestañas y sus botones Anterior/Siguiente navegan **dentro** de ella. Solo un clic en la **barra lateral** puede sacar al usuario de la sección.

```
para cada pestaña visible k en _tabOrder:
    ruta(k) = "p-" + id + "-" + k        # SIEMPRE dentro del expediente
    anterior(k) = _tabOrder[idx(k) - 1]  # omitida si es la primera
    siguiente(k) = _tabOrder[idx(k) + 1] # omitida si es la última

al hacer clic en una pestaña o en Anterior/Siguiente:
    S.route = ruta(destino)
    draw() -> S.ap = id, se renderiza ph-head + pestañas + B2[destino]
    NO se cambia la ruta a una sección principal (ortesis, recetas, etc.)

al hacer clic en la barra lateral:
    S.route = clave de sección principal   # única salida permitida
```

**Implementación:** `_tabRuta(k)` devuelve siempre `"p-"+id+"-"+k`. `_tabApAttr(k)` ya no inyecta `data-ap` porque `draw()` fija `S.ap` al abrir `p-<id>`. Los botones "Ir a sección de …" se eliminaron de `B2.ortesis` y `B2.recetas`. El breadcrumb del expediente ("Inicio › Pacientes › nombre") se renderiza como **texto plano** (sin `data-r`) para que ningún control dentro del perfil permita salir. Las únicas salidas son la barra lateral y las acciones explícitas del encabezado (por ejemplo "Cerrar paciente").

**Recorrido completo (admin):** Resumen → Evaluación → Estudios e imágenes → Recetas → Citas → Procedimientos → Órtesis → Clínica → Rehabilitación → Gestión → Documentos. En la primera pestaña solo aparece "Siguiente"; en la última solo "Anterior". Los roles sin un módulo omiten esa pestaña y el flujo la salta automáticamente.

## Verificación de contenido por pestaña (regla anti-fallback)

`vExp` renderiza con `(B2[tab]||B2.resumen)()` y `(TD[tab]||TD.resumen)`. Si una clave de pestaña no existe en `B2` o en `TD`, **no da error**: muestra silenciosamente Resumen. Por eso toda pestaña debe pasar esta comprobación:

```
para cada k en _tabOrder:
    assert B2[k] existe
    assert TD[k] existe
    assert ruta tras clic == "p-" + id + "-" + k
```

Caso corregido: `ortasis` → alias a `ortesis` en `B2` y en `TD`. Sin esos alias la pestaña Órtesis se veía activa pero mostraba "Estado del paciente / Datos del paciente / Antecedentes".

Caso corregido: el botón **Editar datos del paciente** del Resumen usa `data-a="epac:<id>"`. La acción `ep:<id>` está reservada para editar procedimientos del catálogo; al compartir nombre se abría el modal equivocado y los cambios no se veían en el Resumen. `epac` llama a `fEditPac(+v)` y, tras guardar, `draw()` vuelve a renderizar la pestaña activa. El manejador debe declararse `epac:()=>fEditPac(+v)`: si se escribe `epac:v=>fEditPac(+v)`, ese parámetro `v` local oculta el `v` del `data-a` y llega `NaN`, por lo que el modal no se abre.

Alergias forma parte de **Antecedentes**: en Resumen es la primera fila de esa tarjeta (ya no aparece en Datos del paciente), en Nuevo paciente se captura dentro de la tarjeta Antecedentes (`nl`) y en el expediente se edita desde **Editar antecedentes** (`ga`). La alerta roja del paciente activo y los documentos imprimibles la siguen mostrando por seguridad. Al seleccionar un antecedente familiar oncológico (`nh`/`gf`) se abre `famCancerModal()` para elegir familiares; el valor se guarda como `Antecedente · Familiar1, Familiar2` y se muestra bajo el selector.

| Pestaña Estudios e imágenes | `B2.estudios` / `TD.estudios` | Clave `estudios` (mismo módulo que la sección principal). Muestra los estudios del paciente activo, miniaturas, estado de revisión y el botón **Indicar estudio**. El modal `indicarEstudioModal()` crea el registro y vuelve a dibujar la **misma** ruta `p-<id>-estudios`, sin salir del expediente. Los tipos ofrecidos son los permitidos en el perfil del médico. |

## Transiciones automáticas del flujo clínico

Además del botón Siguiente, ciertas acciones avanzan solas al siguiente paso (siempre dentro del expediente, nunca salen del perfil):

```
guardar evaluación  -> p-<id>-estudios
guardar receta      -> p-<id>-procedimientos
```

Estas transiciones usan la misma `ruta(k) = "p-" + id + "-" + k` del algoritmo de navegación, por lo que respetan la regla de única salida por barra lateral y el filtrado por rol.

## Tipos de estudio por médico

En **Administración → Usuarios → Editar perfil**, un usuario con rol `medico` puede marcar
**Tipos de estudio que puede indicar**, agrupados por categoría (`TIPOS`). La selección se
guarda en `usuarios.estudios` (jsonb) y se devuelve en `/api/yo` como `S.user.estudios`.

- En **Estudios → Indicar estudio**, el selector `ip_t` (y el de **Subir imágenes**, `up_t`)
  solo ofrece los tipos marcados en el perfil del médico.
- Si el médico **no marca ninguno**, se ofrecen todos los tipos del catálogo (`TIPOS_FLAT`).
- El paciente sigue bloqueado al paciente activo: los selectores `ip_p` y `up_p` permanecen
  deshabilitados y no permiten buscar otros pacientes.
- Los tipos se validan por nombre exacto contra el catálogo; no se crean tipos nuevos desde
  el formulario de estudios.

**Correctivo aplicado:** el bloque "Indicar estudio (sin imágenes)" se construía pero no se
incluía en el `return` de `vSubir()`, por lo que la pestaña no mostraba el formulario y
`ip_t` no existía en el DOM. Además, el ayudante `sl()` generaba selectores `disabled` y,
en `ip_t`, un `<select>` anidado. Ahora `sl()` acepta `dis` y los tipos son seleccionables.

## Actualización automática por sesión
1. Al iniciar sesión, `cargar()` guarda en `S.user.modulos` los módulos del perfil que entró (o `null` para admin, que implica acceso total).
2. `draw()` se ejecuta en **cada navegación** y vuelve a generar `$("#side").innerHTML = menu(a)` y `$("#main").innerHTML = ... vExp(...)`.
3. Por lo tanto, al cambiar de usuario (cerrar sesión y entrar con otro), **la barra lateral y las pestañas se recalculan con el perfil nuevo** sin dejar iconos del rol anterior.

## Documentos imprimibles en Recetas
| Documento | Acciones | Datos |
|---|---|---|
| Constancia médica | `cm` → `fConstancia()` | A4 con prestadora, paciente (nombre/cédula/afiliado/expediente), médico (nombre/especialidad/cédula profesional/exequátur), diagnóstico de la última evaluación, texto libre, fecha, firma y sello. Botones Ver e Imprimir. |
| Licencia médica | `lm` → `fLicencia()` | Campos CNSS/SISALRIL: afiliado y cédula, número de afiliado, aseguradora, prestadora, diagnóstico principal, causa (enfermedad común / accidente no laboral / embarazo), modalidad (ambulatoria / hospitalización / ambas), fecha de inicio, días calendario, fecha de término calculada, médico con cédula, exequátur, firma y sello, más nota aclaratoria sobre el formulario oficial de SISALRIL. |

Los botones aparecen tanto en la sección **Recetas** como en la pestaña **Recetas** del expediente; en este último caso el paciente se pasa explícitamente en la acción (`cm:<id>` / `lm:<id>`). Los datos del médico se toman de `S.user` (cargado desde `/api/yo`) y se pueden editar en el modal sin alterar el perfil.

## Casos de prueba esperados

| Rol | Módulos | Iconos laterales | Pestañas en expediente |
|---|---|---|---|
| `admin` | (todos) | Todos + Administración | Las 9 |
| `medico` (ej. `paolagarabito@gmail.com`) | agenda, pacientes, procedimientos, ortesis, quirofano, estudios | Inicio, Agenda, Pacientes, Procedimientos, Órtesis, Quirófano, Estudios | Resumen, Evaluación, Citas, Órtesis, Clínica, Procedimientos. **No** Recetas, Rehabilitación, Gestión, Documentos |
| `secretaria` | (según `DB.PM.secretaria`) | Inicio, Agenda, Pacientes, Procedimientos, Recetas, Órtesis, Documentos, Gestión… | Resumen, Evaluación, Recetas, Citas, Órtesis, Clínica, Procedimientos, Gestión, Documentos. **No** Rehabilitación |
| `fisio` | agenda, pacientes, rehab, ortesis, estudios, documentos | Inicio, Agenda, Pacientes, Órtesis, Estudios, Documentos, Rehabilitación | Resumen, Evaluación, Recetas, Citas, Órtesis, Clínica, Rehabilitación, Documentos. **No** Procedimientos, Gestión |

## Mantenimiento
- Si se crea una sección nueva, agregarla a `M` o `AD` y a `PERMISO_TAB` con su módulo.
- Si se elimina un acceso a un rol desde Administración → Usuarios, el cambio se refleja al reingresar ese usuario (o al recargar, ya que `cargar()` lee `modulos` del servidor).
- No existe un "override" que muestre un icono prohibido: `nv()`, `T` y `_tabOrder` consultan siempre la misma regla.
