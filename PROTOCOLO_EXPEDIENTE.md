# Protocolo de código y número de expediente

## Regla de oro

**Todo paciente debe tener siempre `codigo` (`P-0001`) y `expediente` (`EXP-0001`) únicos, no nulos y no vacíos.**

Los genera **la base de datos** mediante secuencias. La interfaz y la API nunca inventan, sobrescriben ni borran esos valores.

---

## Por qué fallaba

`toK("P")` enviaba `expediente: null` cuando el campo estaba vacío. En PostgreSQL, un `INSERT` con la columna explícitamente en `NULL` **no aplica el `DEFAULT`**. Por eso un paciente recién creado podía quedar sin expediente hasta el próximo reinicio, cuando el backfill de `schema.sql` lo rellenaba.

Además, `schema.sql` ejecutaba `setval('paciente_expediente_seq', ...)` antes de crear la tabla `pacientes`, lo que podía fallar en una base vacía, y el backfill usaba `EXP-<id>`, que podía colisionar con un expediente ya existente.

---

## Capas de protección (implementadas)

### 1. Base de datos (`schema.sql`)

- Secuencias `paciente_codigo_seq` y `paciente_expediente_seq`.
- `DEFAULT ('P-' || lpad(nextval(...), 4, '0'))` y `DEFAULT ('EXP-' || lpad(nextval(...), 4, '0'))`.
- Las secuencias se alinean con el mayor sufijo numérico existente **y** con el mayor `id`, sin retroceder: nunca se reutiliza un número ya emitido.
- Backfill idempotente de filas históricas con `codigo`/`expediente` nulos o en blanco, usando `nextval` (no `id`).
- `ALTER COLUMN ... SET NOT NULL` y `CHECK (btrim(...) <> '')` al final: la base rechaza cualquier paciente sin código, nulo o en blanco.

### 2. API (`main.py`, `POST /api/guardar`)

- Si `codigo` o `expediente` llegan vacíos, se omiten de la lista de columnas:
  - en `INSERT`, se aplica el `DEFAULT` de la secuencia;
  - en `UPDATE`, no se sobrescribe el valor guardado.
- Antes de editar un paciente, se rellenan sus códigos si faltaran (caso de datos históricos).
- La respuesta incluye `codigo` y `expediente`, para que el front-end tenga el valor real inmediatamente.

### 3. Front-end (`static/index.html`)

- `toK("P")` solo incluye `codigo`/`expediente` cuando tienen valor; nunca envía `null`.
- `crearK("P")` y `editarK("P")` copian los códigos devueltos por la API al objeto local (`cd`, `xp`).
- El directorio, el encabezado del expediente, la buscador, las constancias y las licencias muestran `xp` sin esperar a recargar.
- Ni «Nuevo paciente» ni «Editar datos del paciente» permiten escribir el número de expediente.

---

## Verificación obligatoria

Después de cualquier cambio en este flujo, comprobar:

1. **Crear** un paciente nuevo → el directorio muestra `P-xxxx · Exp. EXP-xxxx` sin recargar.
2. **Editar** un paciente existente → el código y el expediente no cambian.
3. **Buscar** por expediente (por ejemplo `EXP-0075`) → aparece el paciente.
4. **SQL** (debe devolver 0 filas):

   ```sql
   select id, nombre from pacientes
   where codigo is null or btrim(codigo) = ''
      or expediente is null or btrim(expediente) = '';
   ```

5. **Duplicados** (debe devolver 0 filas):

   ```sql
   select codigo, count(*) from pacientes group by codigo having count(*) > 1;
   select expediente, count(*) from pacientes group by expediente having count(*) > 1;
   ```

---

## Prohibiciones

- No asignar `EXP-` manualmente desde el front-end ni desde scripts.
- No calcular el número como `max(id) + 1` en la aplicación.
- No enviar `expediente: null` en un `INSERT`.
- No borrar ni dejar en blanco un expediente al editar un paciente.
- No quitar los `NOT NULL` ni los `DEFAULT` de `schema.sql`.

---

## Edad y fecha de nacimiento (regla relacionada)

- En **Nuevo paciente** y en **Editar datos del paciente**, al escribir una edad válida (1–130) se calcula la **fecha de nacimiento aproximada** (mismo día y mes, años atrás) y se marca como `(aprox.)`.
- Si se ajustan los selectores de día/mes/año, la edad se recalcula a partir de la fecha exacta.
- La fecha exacta siempre prevalece: si ya viene de la cédula o del expediente, no se sobrescribe al guardar.

---

## Historial

| Commit | Cambio |
|---|---|
| `6c1e2f2` | Etiqueta «Radiografia» y corrección del modal de edición. |
| este commit | Regla de código/expediente en tres capas y edad → fecha aproximada. |
