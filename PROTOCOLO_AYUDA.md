# Protocolo de actualización de la sección Ayuda

## Objetivo
Garantizar que cada vez que se agregue, modifique o elimine una funcionalidad del sistema, la sección **Ayuda** (`vAyuda()` en `static/index.html`) se actualice para reflejar el cambio en la sección correspondiente, manteniendo la documentación al día.

## Regla principal
> **Ningún cambio funcional se considera terminado hasta que la sección Ayuda correspondiente esté actualizada.**

## Estructura de la ayuda
La ayuda se renderiza en `vAyuda()` (archivo `v2_api/static/index.html`) mediante tarjetas (`card(...)`). Cada tarjeta corresponde a una sección del sistema y sigue este formato:

```js
${card("N. Nombre de la sección", `<p class="mu">Descripción breve de la sección.</p>
  <ul class="mu" style="line-height:1.8">
    <li><b>Subfunción:</b> descripción.</li>
  </ul>`)}
```

## Pasos obligatorios al actualizar una función

1. **Identificar la sección afectada** (Pacientes, Agenda, Quirófano, Estudios, Recetas, Documentos, Órtesis, Rehabilitación, Referimientos, Autorizaciones, Facturación, Administración, Evaluación médica, etc.).
2. **Localizar la tarjeta correspondiente** en `vAyuda()` (numerada del 1 al N).
3. **Actualizar el texto** de esa tarjeta:
   - Si se **agregó** una función → añadir un `<li>` describiéndola.
   - Si se **modificó** una función → corregir la descripción existente.
   - Si se **eliminó** una función → quitar el `<li>` correspondiente.
4. **Verificar** que la ayuda renderiza sin errores (`#main` sin `undefined`).
5. **Probar** en el navegador: abrir la sección Ayuda y confirmar que el texto es correcto.
6. **Commit y push** junto con el cambio funcional (no en un commit separado).

## Convención de comentarios
Al modificar una función, agregar un comentario `// HELP: <sección>` encima para recordar actualizar la ayuda:

```js
// HELP: Recetas — botón Verificar agregado
function fRx(i){ ... }
```

## Lista de secciones y sus tarjetas (numeración actual)
1. Conceptos básicos
2. Inicio
3. Agenda
4. Pacientes
5. Expediente del paciente (pestañas)
6. Nuevo paciente
7. Quirófano
8. Estudios e imágenes
9. Procedimientos
10. Recetas
11. Documentos
12. Órtesis
13. Rehabilitación
14. Referimientos
15. Autorizaciones
16. Facturación
17. Administración
18. Portada y acceso
19. Atajos y tips

Si se agrega una sección nueva, añadir una tarjeta nueva y renumerar si es necesario.

## Verificación
- La sección Ayuda debe renderizar sin `undefined` ni errores en consola.
- El enlace "Ayuda" en el menú lateral debe estar visible para todos los roles.
- La descripción debe coincidir con el comportamiento real del sistema.

## Responsable
Quien realice el cambio funcional es responsable de actualizar la ayuda en el mismo commit.
