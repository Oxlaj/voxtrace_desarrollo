# VoxTrace

VoxTrace es una aplicación web de apoyo al análisis forense de archivos de audio.

## Estado por fases

### Fases 1 y 2: base y persistencia

Completadas a nivel de código. Existen FastAPI, configuración por `.env`, `/health`, SQLAlchemy, los ocho modelos del esquema `voxtrace` y configuración de Alembic. La base `voxtrace_db`, el esquema `voxtrace` y sus tablas existen previamente; no se ejecutan migraciones desde este proyecto.

### Fase 3: autenticación y RBAC

Implementada. Existen login, logout, `/auth/me`, hash Argon2, sesiones firmadas, CSRF, autorización por rol y administración de usuarios. Los roles existentes son consultables, pero no se crean, editan ni eliminan.

## Autenticación

La autenticación usa hashes Argon2 y sesiones firmadas en cookies `HttpOnly` con `SameSite=Lax`. `SESSION_COOKIE_SECURE=false` permite desarrollo HTTP local; debe configurarse como `true` cuando la LAN opere sobre HTTPS. La clave `SESSION_SECRET` es obligatoria, procede del entorno local y debe tener al menos 32 caracteres.

Las operaciones `POST`, `PUT`, `PATCH` y `DELETE` requieren un token CSRF asociado a la sesión y enviado mediante `X-CSRF-Token`. La página de login incorpora un token preautenticado; clientes API pueden iniciar el flujo con `GET /auth/csrf`. El token rota después de autenticar y nunca se almacena en `localStorage`, `sessionStorage` o logs.

`GET /auth/me` devuelve exclusivamente el identificador, nombre, correo y rol del usuario de la sesión. El frontend inicial usa esta misma cookie mediante solicitudes del mismo origen y nunca intenta leerla o modificarla desde JavaScript.

## Frontend inicial

Las páginas de login, Dashboard, personas, muestras, análisis 1:N, historial, reportes, usuarios y auditoría usan HTML, CSS, JavaScript y Jinja2. Todas las vistas privadas están protegidas por autenticación y RBAC. Administradores e Investigadores pueden cargar referencias; Analistas solo las consultan.
La pantalla `/app/analizar` permite a los tres roles ejecutar la identificación 1:N mediante el endpoint existente. Presenta hasta tres candidatos en el orden del backend, conserva el identificador del análisis únicamente en el DOM y enlaza su detalle. `/app/historial` ofrece filtros y paginación según rol; `/app/historial/{id}` integra detalle, reporte estructurado y descarga del PDF existente sin exponer metadatos internos.
La administración de usuarios está disponible exclusivamente para Administradores en `/app/usuarios`. Permite consultar roles existentes, crear y editar cuentas, activar o desactivar usuarios y establecer una contraseña nueva mediante Argon2. No elimina usuarios ni modifica roles, y evita desactivar o degradar al último Administrador activo.
La bitácora de solo lectura está disponible para Administradores en `/app/auditoria` y mediante `GET /logs`. Incluye filtros y paginación de 20 registros; los detalles pasan por una barrera defensiva que omite patrones de secretos, rutas, hashes, vectores, SQL o trazas antes de responder.

### Fase 4: personas

Implementada a nivel de API. El CRUD de personas está protegido por roles y usa los campos del modelo oficial. La validación contra PostgreSQL real requiere datos de prueba autorizados.

## Personas

El CRUD de `/personas` está protegido por roles. Administradores e Investigadores pueden registrar y editar personas; los Administradores son los únicos que pueden eliminarlas. Los tres roles pueden consultar y buscar por nombre, identificador o alias.

### Fase 5: gestión segura de muestras

Implementada. La carga valida extensión, MIME, tamaño, hash SHA-256 y nombre físico UUID, normaliza una copia y genera un embedding ECAPA-TDNN. `audio` y `embedding` se confirman en una única transacción. Si falla el embedding o la persistencia, se revierte la base, se limpia el procesado y se conserva el original técnicamente aceptado para preservar trazabilidad; un archivo rechazado durante la validación técnica sí se elimina. Las respuestas públicas no incluyen rutas, hashes ni vectores.

## Muestras de voz

La carga de referencias usa `POST /personas/{persona_id}/muestras` y está disponible para Administradores e Investigadores. La lectura usa `GET /personas/{persona_id}/muestras` y `GET /personas/{persona_id}/muestras/{audio_id}`, disponible para los tres roles. Las cargas web multipart requieren el token CSRF de sesión. Se aceptan MP3, OGG, MP4 y WAV. El original se conserva en `storage/` con nombre UUID y PostgreSQL mantiene la relación 1:1 entre metadatos y embedding.

## Procesamiento de audio

La salida normalizada utilizada por ECAPA-TDNN es WAV PCM de 16 kHz y un canal mono. VoxTrace no establece actualmente una duración mínima fija como criterio de aceptación: conserva la duración real como metadato y su influencia en el desempeño biométrico deberá evaluarse experimentalmente.

## Implementado

Autenticación y sesiones con CSRF; RBAC; personas; muestras con FFmpeg y ECAPA-TDNN; embeddings de 192 dimensiones; identificación 1:N y Top 3; persistencia transaccional; historial; reportes estructurados y PDF; administración de usuarios y consulta de auditoría; frontend Jinja2 para estos módulos.

## Pendiente

Calibración experimental del umbral, métricas académicas finales, política de retención/eliminación, respaldo operativo, recuperación autónoma de contraseñas y validación de despliegue LAN/HTTPS.

## Decisiones pospuestas

La verificación 1:1 permanece pospuesta. `verification_service.py` se conserva para una fase posterior, pero no existe endpoint ni interfaz 1:1 y no se modifica el esquema para diferenciar tipos de análisis. También permanecen pospuestos pgvector, nuevos modelos biométricos y cambios al muestreo o dimensión del embedding.

### Fase 8: similitud coseno

Implementada como servicio matemático independiente. Recibe dos vectores de 192 valores, valida dimensión, finitud y norma no cero, y devuelve el coseno original en escala matemática aproximada `[-1, 1]`. No calcula porcentajes, no aplica umbrales y no afirma identidad.

### Verificación 1:1 — pospuesta

Existe únicamente el servicio reutilizable `verification_service.py`. La funcionalidad completa está pospuesta: no tiene endpoint, interfaz ni persistencia diferenciada. No se presenta como módulo implementado.

### Fase 10: identificación 1:N y Top 3 exploratorio

Implementada como servicio independiente en `identification_service.py`. Genera un embedding de consulta una vez, compara contra las referencias disponibles de cada persona, excluye personas sin embeddings válidos y ordena por `similitud_mejor`, luego `similitud_promedio` y finalmente `id_persona`. Devuelve como máximo tres candidatos con sus puntuaciones individuales y conteos. El Top 3 es matemático y no afirma identidad.

### Persistencia del análisis

El endpoint `POST /analisis/identificacion` integra carga, preservación, hash, normalización, embedding, identificación 1:N y persistencia. `resultado_analisis.similitud` recibe una puntuación normalizada técnica mediante `((coseno + 1) / 2) * 100`, limitada a `[-1, 1]` y redondeada a tres decimales para `NUMERIC(6,3)`. No es probabilidad, certeza ni porcentaje de identidad. `supera_umbral` se decide con el coseno original, antes de normalizar o redondear, usando el umbral experimental provisional `0.6281865036` (`81.409/100` normalizado). El valor procede de `experimento-01`, con 5 consultas KNOWN y 17 UNKNOWN, y no constituye una validación biométrica definitiva.

La fila de `analisis`, sus candidatos en `resultado_analisis` y el estado `completado` se confirman mediante un único commit. El original de consulta técnicamente aceptado se conserva siempre. El WAV normalizado de consulta es temporal y se elimina tanto al completar el análisis como ante cualquier error posterior a su creación. Los fallos controlados e inesperados revierten la transacción principal y generan una auditoría segura; la auditoría posterior utiliza una transacción separada para no alterar la atomicidad del resultado principal.

Permanece pendiente definir una política formal de evidencia y retención para los originales técnicamente aceptados cuyo análisis no llegue a persistirse. Estos originales no se eliminan automáticamente y, con el esquema actual, pueden quedar sin una fila de análisis asociada. Esta limitación no se resuelve mediante cambios de esquema en la fase actual.

### Fase 6: procesamiento técnico de audio

Implementada e integrada con los flujos biométricos posteriores. FFprobe exige una pista de audio real, obtiene y conserva su duración, y rechaza archivos corruptos, sin audio o con duración inválida. La duración positiva no provoca por sí sola un rechazo. FFmpeg convierte una copia a WAV PCM `pcm_s16le`, mono, 16 kHz y conserva el original intacto. Los procesados fallidos se eliminan según la política transaccional vigente.

## Auditoría

La auditoría básica usa la tabla existente `voxtrace.log` mediante un servicio centralizado. Registra login exitoso y fallido, logout, creación y edición de personas, carga de muestras y errores relevantes de esas operaciones. Conserva usuario, acción, fecha, IP y detalles técnicos mínimos, sin contraseñas, hashes, cookies ni contenido de audio.

## Persistencia

Los modelos SQLAlchemy representan las tablas `rol`, `usuario`, `persona`, `audio`, `embedding`, `analisis`, `resultado_analisis` y `log`, incluyendo sus relaciones y restricciones principales. La tabla `persona` incluye `nombre` como exige la decisión final del modelo.

## Historial de análisis

El backend expone un listado paginado en `GET /historial` y el detalle de candidatos ordenados en `GET /historial/{analysis_id}`. Administradores e Investigadores pueden consultar todos los análisis y filtrar por usuario; cada Analista solo puede consultar los análisis realizados por su propio usuario. Las respuestas omiten rutas, hashes, embeddings y detalles internos. El detalle presenta `posible_coincidencia` o `coincidencia_insuficiente` a partir del valor `supera_umbral` persistido.

Política histórica del umbral: `BIOMETRIC_THRESHOLD_EFFECTIVE_AT=2026-10-04T23:13:27` representa el momento local de integración del umbral experimental. Los análisis con `fecha_analisis` anterior se presentan como `umbral_no_evaluado`, con independencia del booleano histórico, y no se recalculan desde la puntuación normalizada. Los análisis creados en la fecha de corte o posteriormente muestran `posible_coincidencia` o `coincidencia_insuficiente` según el valor persistido. Esta regla se aplica al detalle, reporte estructurado y PDF sin modificar PostgreSQL.

## Reportes estructurados

`GET /reportes/analisis/{analysis_id}` devuelve un reporte JSON seguro y `GET /reportes/analisis/{analysis_id}/pdf` genera su versión PDF institucional en memoria. Ambos incluyen los datos generales y hasta tres candidatos ordenados, aplican la misma política de acceso del historial y responden 404 ante consultas de un Analista sobre análisis ajenos. El modelo biométrico se devuelve como `null` en JSON y como `No registrado` en PDF porque el esquema actual no conserva históricamente qué modelo produjo cada análisis. Los reportes incluyen la nota metodológica y omiten rutas, hashes y datos biométricos internos.

## Evaluación biométrica experimental 1:N

La herramienta offline `scripts/evaluate_biometrics.py` evalúa el ranking actual sin
alterar producción ni definir umbrales. El dataset debe mantener carpetas separadas
`references/` y `queries/`. Las referencias deben estar registradas en VoxTrace y cada
consulta debe ser una grabación independiente.

El manifiesto JSON contiene `references` con `audio_id`, `person_id` y
`dataset_audio_id`. Cada elemento de `queries` incluye obligatoriamente `test_id`,
`condition`, `dataset_audio_id` y una `path` relativa al manifiesto. `condition` solo
puede ser `KNOWN` o `UNKNOWN`. Una consulta `KNOWN` requiere un `person_id` de
PostgreSQL con referencias elegibles y no utiliza `experimental_speaker_id`. Una
consulta `UNKNOWN` requiere `experimental_speaker_id`, no puede declarar `person_id`
y no crea ni busca ese hablante experimental en PostgreSQL. Varios audios UNKNOWN
pueden compartir el mismo `experimental_speaker_id`.

`test_id` y los `dataset_audio_id` de consultas deben ser únicos; los
`dataset_audio_id` de referencias también deben ser únicos y no pueden coincidir con
los de consultas. Para evitar referencias ocultas, el manifiesto debe declarar todos
los audios con embedding elegibles de la base usada para el experimento.

Estructura recomendada:

```text
dataset/experimento-01/
├── manifest.json
├── references/  # copia organizada opcional; las referencias efectivas ya están registradas
└── queries/
    ├── persona-001/consulta-001.wav
    └── persona-002/consulta-001.wav
```

Ejemplo completo de `manifest.json`:

```json
{
  "dataset_id": "experimento-01",
  "references": [
    {"audio_id": 101, "person_id": 1, "dataset_audio_id": "REF-P001-01"},
    {"audio_id": 102, "person_id": 1, "dataset_audio_id": "REF-P001-02"},
    {"audio_id": 201, "person_id": 2, "dataset_audio_id": "REF-P002-01"}
  ],
  "queries": [
    {"test_id": "TEST-K001-01", "condition": "KNOWN", "person_id": 1, "dataset_audio_id": "QUERY-K001-01", "path": "queries/persona-001/consulta-001.wav"},
    {"test_id": "TEST-U001-01", "condition": "UNKNOWN", "experimental_speaker_id": "UNKNOWN-001", "dataset_audio_id": "QUERY-U001-01", "path": "queries/unknown-001/consulta-001.wav"}
  ]
}
```

En KNOWN, `person_id` expresa la identidad real conocida. En UNKNOWN,
`experimental_speaker_id` permite agrupar grabaciones de un mismo hablante no
registrado sin convertirlo en una persona de VoxTrace. `audio_id` enlaza cada
referencia con su embedding actual en PostgreSQL. Además de exigir identificadores
distintos, la herramienta compara SHA-256 y rechaza una consulta físicamente idéntica
a cualquier referencia registrada o a otra consulta del mismo experimento. Las rutas
solo se usan como entrada y nunca se exportan.

```powershell
python -m scripts.evaluate_biometrics dataset\manifest.json --output resultados\experimento-01
```

Se generan `queries.csv`, `scores.csv` y `summary.json`. `queries.csv` conserva los
campos de ranking existentes y añade `condition` y `experimental_speaker_id`; en
UNKNOWN, identidad real, posición correcta y hits quedan vacíos. `scores.csv` añade
los mismos campos de condición y clasifica cada comparación como `genuine`,
`known_impostor` o `unknown_impostor`. `summary.json` separa las métricas KNOWN de los
conteos y estadísticas descriptivas UNKNOWN. Solo KNOWN calcula exactitud Top-1 y
Top-3. `threshold_evaluated` permanece en `false`.

Los CSV conservan el coseno original con la precisión práctica del `float` y una
puntuación normalizada redondeada para presentación, pero no embeddings, rutas
absolutas ni decisiones de aceptación/rechazo. Los WAV procesados temporales se
eliminan tras cada consulta. La protección SHA-256 no detecta recodificaciones,
reexportaciones, recortes, cambios de bitrate ni otras transformaciones acústicas; la
independencia de esos casos debe garantizarse al preparar el dataset.

## Ejecución local

1. Crear y activar el entorno virtual:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Instalar dependencias:

   ```powershell
   pip install -r requirements.txt
   ```

3. Copiar `.env.example` como `.env` y ajustar sus valores locales.

4. Verificar que PostgreSQL, la base configurada y el esquema `voxtrace` estén
   disponibles. El bootstrap no crea ni modifica el esquema.

5. Garantizar los tres roles base. El comando es idempotente: puede repetirse y
   solo crea roles faltantes o completa una descripción vacía.

   ```powershell
   python -m scripts.bootstrap_roles
   ```

6. Crear el primer Administrador de forma interactiva:

   ```powershell
   python -m scripts.create_admin
   ```

7. Iniciar FastAPI:

   ```powershell
   uvicorn backend.main:app --reload
   ```

El endpoint de comprobación estará disponible en `http://127.0.0.1:8000/health`.

### Reutilizar audio de un análisis como muestra

El formulario de registro permite adjuntar una primera muestra opcional (MP3,
OGG, MP4 o WAV). Sin archivo conserva `POST /personas` con JSON; con archivo usa
`POST /personas/con-muestra` multipart, con `persona` como JSON y `file` como
audio. El procesamiento utiliza los servicios existentes. Persona, audio,
embedding y auditoría se confirman juntos; los errores de procesamiento no crean
una persona parcial. Ante un commit incierto se conservan archivos para revisión.
El registro mediante reutilización de análisis mantiene su operación existente.

Pruebas HTTP aisladas del registro con/sin primera muestra:

```powershell
.\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider tests/test_person_registration_http.py
```

Administrador e Investigador pueden usar «Registrar nueva persona» o «Agregar a
persona existente» desde el resultado inmediato y el detalle del historial, con o
sin candidatos o coincidencias. La asociación requiere confirmación explícita;
no constituye una identificación definitiva ni modifica resultados o umbrales.

`POST /analisis/{id_analisis}/muestra` recibe `confirmar: true` y exactamente uno
de `id_persona` o `nueva_persona` (campos del formulario existente). La sesión,
RBAC, cambio obligatorio de contraseña y CSRF siguen siendo obligatorios. Se
mantiene el acceso global al historial de Administrador e Investigador. Solo se
admiten análisis completados; el esquema actual no guarda el tipo de análisis y
el flujo de identificación 1:N existente es el origen de estos resultados.

El servidor resuelve el original por ID, restringe el almacenamiento a `storage/`
del proyecto, copia con UUID a referencias y verifica SHA-256 sobre los bytes
copiados. Procesamiento y embeddings utilizan los servicios existentes. El hash
único impide registrar el mismo audio en dos personas; se devuelve conflicto en
lugar de reasignarlo. Persona nueva, muestra, embedding y auditoría de asociación
se guardan en una transacción, sin migraciones. Si falla antes de intentar el
commit, se limpian únicamente las copias nuevas después de confirmar rollback y
ausencia de referencias por hash y rutas. Si falla el commit, el rollback o la
consulta de referencias, las copias se conservan y se registra una advertencia
con el ID del análisis para revisión manual. No hay borrado automático ni se
supone que un error de comunicación significa que PostgreSQL rechazó el commit.
El original de consulta se conserva y debe seguir disponible. Los fallos de
EmbeddingError devuelven HTTP 500, como la carga actual de muestras.

Pruebas aisladas sin dependencias externas ni conexión a PostgreSQL:

```powershell
python -B -m unittest discover -s tests -p test_analysis_reuse_isolated.py -v
```

Estas pruebas ejecutan las definiciones de los servicios con dependencias
sustituidas; no validan el montaje HTTP, Pydantic, el navegador, FFmpeg ni
SpeechBrain reales. La prueba E2E general usa la conexión de la aplicación y no
debe ejecutarse contra una base de producción.
