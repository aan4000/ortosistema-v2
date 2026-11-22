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
| Botones Anterior/Siguiente | `_tabOrder` | Usa el mismo `.filter(tabVisible)`, por lo que la secuencia salta las pestañas sin acceso. Además usan `_tabRuta()`/`_tabApAttr()`, por lo que al avanzar a Órtesis o Recetas van **directo a la sección principal** con `data-ap="<id>"`, igual que al hacer clic en la pestaña. |
| Ruta directa | `draw()` | Si alguien escribe `p-71-ortasis` y el rol no tiene `ortesis`, se normaliza a la primera pestaña visible (Resumen). |
| Registro de paciente | `gp()` | Al crear un paciente (o elegir "Crear como nuevo" ante un duplicado) se navega directo a `p-<id>-evaluacion`. El aviso posterior ofrece continuar a Citas. |
| Pestaña Recetas | `vExp()` | Al hacer clic navega a la sección principal `recetas` con `data-ap="<id>"`, igual que Órtesis, preservando el paciente activo. Desde el expediente se puede crear la receta directamente con "Nueva receta". |
| Acceso a sección | `draw()` | Bloquea rutas completas (`can(a)`) y redirige a `inicio` si no hay permiso. |

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
