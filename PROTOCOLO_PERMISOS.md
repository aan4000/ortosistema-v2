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
| Pestañas del paciente | `vExp(id, tab)` | Construye `T` con `.filter(([k]) => tabVisible(k))`. Orden: Resumen → Evaluación → **Recetas** → Citas → Órtesis → Clínica → Procedimientos → Rehabilitación → Gestión → Documentos. |
| Botones Anterior/Siguiente | `_tabOrder` | Usa el mismo `.filter(tabVisible)`, por lo que la secuencia salta las pestañas sin acceso. `_tabRuta()` garantiza que **siempre** se permanece en `p-<id>-<pestaña>`. |
| Ruta directa | `draw()` | Si alguien escribe `p-71-ortasis` y el rol no tiene `ortesis`, se normaliza a la primera pestaña visible (Resumen). |
| Registro de paciente | `gp()` | Al crear un paciente (o elegir "Crear como nuevo" ante un duplicado) se navega directo a `p-<id>-evaluacion`. El aviso posterior ofrece continuar a Citas. |
| Pestañas Órtesis y Recetas | `vExp()` | Muestran el contenido de esa sección **dentro del expediente** (listado filtrado al paciente + acciones "Asignar órtesis" / "Nueva receta"). No existe botón que saque al usuario de la sección. |
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

**Recorrido completo (admin):** Resumen → Evaluación → Recetas → Citas → Órtesis → Clínica → Procedimientos → Rehabilitación → Gestión → Documentos. En la primera pestaña solo aparece "Siguiente"; en la última solo "Anterior". Los roles sin un módulo omiten esa pestaña y el flujo la salta automáticamente.

## Actualización automática por sesión
1. Al iniciar sesión, `cargar()` guarda en `S.user.modulos` los módulos del perfil que entró (o `null` para admin, que implica acceso total).
2. `draw()` se ejecuta en **cada navegación** y vuelve a generar `$("#side").innerHTML = menu(a)` y `$("#main").innerHTML = ... vExp(...)`.
3. Por lo tanto, al cambiar de usuario (cerrar sesión y entrar con otro), **la barra lateral y las pestañas se recalculan con el perfil nuevo** sin dejar iconos del rol anterior.

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
