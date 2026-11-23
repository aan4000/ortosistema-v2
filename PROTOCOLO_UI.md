# Protocolo visual y UX de OrtoSistema v2

## Principio

La interfaz debe verse moderna, densa pero legible, y caber completa al **100 % de zoom** en una pantalla de escritorio. La navegación nunca debe dejar un vacío: entre secciones se muestra un **skeleton** ligero mientras se redibuja la página.

---

## 1. Tokens y medidas compactas

El bloque final de `static/index.html` (`Sistema visual 2026`) manda sobre el CSS anterior y define:

- `--side-w: 224px` (sidebar).
- `--top-h: 52px` (barra superior y sticky de la cabecera del paciente).
- Body: `13.5px / 1.45`.
- Inputs y botones: `min-height: 36px`.
- Tablas: celdas `8px`, fuente `12.5px`.
- Tarjetas: padding `14px 16px`, radio `12px`.
- `.pg`: `padding: 14px 20px 40px`, sin ancho máximo (aprovecha todo el main).

**Regla:** cualquier ajuste visual nuevo se agrega al bloque final, no se dispersa entre las reglas antiguas.

---

## 2. Skeleton de transición

- `skelOn()` crea `#skelLayer` en `document.body` antes de redibujar y registra `dataset.inicio`.
- `go()` lo activa solo cuando la ruta cambia.
- `draw()` siempre llama a `skelOff()` al terminar; el overlay permanece visible al menos `SKEL_MIN = 180 ms` y luego se desvanece en 220 ms. Así el skeleton sí se ve aunque `draw()` sea síncrono.
- El DOM se actualiza de forma síncrona: ningún código posterior a `go()` necesita esperar.
- Con `prefers-reduced-motion: reduce`, el skeleton no se muestra.
- El marcador inicial de carga ya es un skeleton, no el texto «Cargando…».

**Prohibido:** hacer `draw()` asíncrono dentro de `go()`. Varios flujos consultan el DOM inmediatamente después de navegar.

---

## 3. Correcciones aplicadas

- Se eliminaron `@keyframes` duplicados (`fadeInUp`, `slideInLeft`, `scaleIn`, `shimmer`, `pulse`, `bounceIn`).
- Se unificaron las definiciones duplicadas de `.nav-ic` y del fondo de `.lg`.
- Se redujo la animación de entrada de 1 s a 280 ms para evitar sensación de lentitud.
- Los tooltips de `.icb` usan `display:none` fuera de `:hover`/`:focus-visible`, por lo que no generan scroll horizontal; al mostrarse usan `tipIn` y texto con salto de línea.
- `.pcell` recorta los nombres largos de pacientes con elipsis para no empujar el ancho de la tabla.

---

## 4. Verificación obligatoria

Después de cualquier cambio visual:

1. Abrir con `?v=<nuevo>` y entrar como `admin`.
2. Comprobar que no hay scroll horizontal: `document.documentElement.scrollWidth === innerWidth`.
3. Medir sidebar ≈ `224px` y barra superior ≈ `52px`.
4. Navegar entre módulos y pestañas del paciente: debe aparecer el skeleton ~200 ms y desaparecer sin dejar capa.
5. Revisar consola: cero errores.
6. Probar con `prefers-reduced-motion`: sin skeleton y sin animaciones.

---

## Historial

| Commit | Cambio |
|---|---|
| este commit | Sistema visual 2026: compactación, tokens finales, skeleton y limpieza de CSS duplicado. |
