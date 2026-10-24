# AGENTS.md — VoxTrace

## 1. Propósito de este archivo

Este archivo es la guía maestra de desarrollo para Codex y cualquier otro agente de programación que trabaje en VoxTrace.

Debe leerse antes de crear, modificar o eliminar código. Las decisiones aquí descritas representan el alcance, arquitectura, modelo de datos, reglas de seguridad, experiencia de usuario y prioridades del proyecto.

No cambiar tecnologías principales, arquitectura, relaciones de base de datos, permisos, flujos biométricos o diseño funcional sin justificarlo primero. Si un cambio puede afectar el alcance académico, seguridad, trazabilidad o validez del análisis, detenerse y explicarlo antes de implementarlo.

---

## 2. Nombre y objetivo del proyecto

Nombre oficial del sistema:

**VoxTrace**

VoxTrace es un sistema web biométrico de voz orientado al análisis forense de archivos de audio. Su propósito es servir como herramienta de apoyo para comparar una muestra de voz cargada por un usuario autorizado contra voces previamente registradas y mostrar posibles coincidencias.

El sistema NO debe presentar una coincidencia automática como identificación forense definitiva.

Usar términos como:
- Posible coincidencia
- Candidato
- Porcentaje de similitud
- Resultado del análisis
- Supera el umbral
- No supera el umbral

Evitar términos como:
- Identificación confirmada
- Persona identificada de forma definitiva
- Culpable

---

## 3. Alcance funcional principal

VoxTrace deberá permitir:

1. Autenticación de usuarios.
2. Control de acceso por roles.
3. Registro de personas.
4. Gestión de muestras de voz por persona.
5. Carga de audios forenses.
6. Validación de archivos.
7. Conversión/normalización de audio a WAV para procesamiento.
8. Generación de embeddings de voz.
9. Identificación 1:N contra personas registradas.
10. Verificación 1:1 contra una persona específica.
11. Comparación mediante similitud coseno.
12. Decisión automática basada en umbral configurable.
13. Mostrar Top 3 posibles coincidencias.
14. Ordenar Top 3 de mayor a menor similitud.
15. Mostrar si cada candidato supera o no el umbral.
16. Historial de análisis.
17. Generación de reportes.
18. Auditoría de acciones.
19. Gestión de usuarios y roles para el Administrador.
20. Posibilidad de registrar una nueva persona y asociar nuevas muestras cuando no exista coincidencia suficiente, según permisos.

---

## 4. Contexto de datos biométricos

La base inicial contempla:

- Al menos 15 personas.
- Mínimo 3 audios por persona.
- Se espera trabajar con 20 o más muestras totales.
- Formatos admitidos:
  - MP3
  - OGG
  - MP4
  - WAV

---

## 5. Arquitectura

Utilizar arquitectura cliente-servidor de tres capas.

### 5.1 Presentación

Interfaz web de escritorio.

Responsabilidades:
- Login.
- Dashboard.
- Formularios.
- Gestión de personas.
- Gestión de muestras.
- Carga de audios.
- Resultados.
- Historial.
- Administración.
- Auditoría.

### 5.2 Lógica de negocio

Backend Python + FastAPI.

Responsabilidades:
- Autenticación.
- Autorización.
- Validación.
- Procesamiento de audio.
- Generación de embeddings.
- Comparación biométrica.
- Persistencia.
- Reportes.
- Auditoría.
- Manejo de errores.

### 5.3 Datos

PostgreSQL.

Responsabilidades:
- Roles.
- Usuarios.
- Personas.
- Metadatos de audio.
- Embeddings.
- Análisis.
- Resultados.
- Logs.

Regla obligatoria:

`Frontend -> FastAPI -> PostgreSQL`

Nunca conectar el frontend directamente a PostgreSQL.

---

## 6. Tecnologías principales

### Backend
- Python 3
- FastAPI
- Uvicorn
- SQLAlchemy
- Alembic
- Pydantic

### Base de datos
- PostgreSQL
- pgAdmin 4
- pgvector podrá evaluarse posteriormente

### Procesamiento de audio
- FFmpeg
- Librosa

### Biometría de voz
- SpeechBrain
- Línea inicial recomendada: ECAPA-TDNN
- Embeddings de voz

### Matemática
- NumPy
- SciPy
- Similitud coseno

### Frontend
Primera versión:
- HTML
- CSS
- JavaScript
- Jinja2 si se usa renderizado del lado del servidor

No introducir React, Vue u otro framework sin justificación.

### Desarrollo
- Visual Studio Code
- Git
- Entorno virtual `.venv`

---

## 7. Despliegue inicial

Fase inicial:
- Desarrollo en una sola computadora.
- Acceso mediante `localhost`.

Fase de implementación:
- Servidor central dentro de una red local.
- El servidor alojará:
  - FastAPI
  - PostgreSQL
  - Archivos de audio
  - Modelos biométricos

Los clientes accederán por navegador dentro de la LAN.

No asumir despliegue en Internet o nube en la primera versión.

---

## 8. Almacenamiento de audios

No almacenar los audios completos dentro de PostgreSQL en la primera versión.

PostgreSQL almacenará:
- Metadatos
- Relaciones
- Rutas
- Hashes
- Embeddings
- Resultados

Sistema de archivos:
- Audios originales
- Audios normalizados
- Archivos derivados

Estructura sugerida:

```text
storage/
└── audio/
    ├── originales/
    ├── procesados/
    └── temporales/
```

Reglas:
- Conservar el original sin modificar.
- Generar hash SHA-256 del original.
- Normalizar una copia de trabajo.
- No usar nombres físicos basados directamente en alias.
- Usar identificadores internos seguros.

---

## 9. Flujo biométrico

Flujo general:

`Carga -> Validación -> Conversión/normalización -> Preprocesamiento -> Embedding -> Comparación -> Ranking -> Umbral -> Resultado -> Historial`

### 9.1 Validación
Comprobar:
- Archivo real.
- Extensión permitida.
- Tipo MIME.
- Tamaño.
- Duración.
- Pista de audio válida.
- Integridad básica.

### 9.2 Conversión
Convertir los formatos de entrada a WAV cuando sea necesario mediante FFmpeg.

No fijar parámetros definitivos de frecuencia de muestreo hasta confirmar requisitos del modelo biométrico.

### 9.3 Embeddings
Utilizar SpeechBrain para generar una representación de la voz.

### 9.4 Comparación
Utilizar similitud coseno.

### 9.5 Top 3
Para identificación 1:N:
- comparar contra las personas registradas;
- ordenar de mayor a menor;
- devolver exactamente las 3 mejores coincidencias disponibles;
- incluir porcentaje de similitud;
- incluir posición 1, 2 y 3;
- indicar si supera el umbral.

### 9.6 Umbral
No usar un valor arbitrario como definitivo.

El umbral debe:
- ser configurable;
- quedar registrado por análisis cuando se implemente;
- validarse experimentalmente;
- evaluarse con falsos positivos y falsos negativos.

---

## 10. Roles

### Administrador
Puede:
- Gestionar usuarios.
- Asignar roles.
- Registrar personas.
- Editar personas.
- Gestionar muestras.
- Analizar audios.
- Consultar resultados.
- Consultar historial.
- Generar reportes.
- Consultar auditoría.
- Gestionar configuraciones autorizadas.

### Investigador
Puede:
- Registrar personas.
- Editar información autorizada.
- Gestionar muestras.
- Analizar audios.
- Ejecutar identificación 1:N.
- Ejecutar verificación 1:1.
- Consultar resultados.
- Consultar historial.
- Generar reportes.

No puede:
- Gestionar usuarios.
- Asignar roles.
- Modificar configuraciones administrativas.

### Analista
Puede:
- Cargar audio para análisis.
- Ejecutar análisis.
- Consultar resultados.
- Consultar historial permitido.
- Generar reportes permitidos.

No puede:
- Registrar personas.
- Gestionar muestras.
- Gestionar usuarios.
- Cambiar roles.
- Cambiar configuraciones.

---

## 11. Casos de uso principales

### CU-01 Gestionar muestras de voz
Actores:
- Administrador
- Investigador

### CU-02 Registrar persona
Actores:
- Administrador
- Investigador

### CU-03 Analizar audio forense
Actores:
- Administrador
- Investigador
- Analista

### CU-04 Comparar e identificar voz
Actores:
- Administrador
- Investigador
- Analista

### CU-05 Consultar resultados e historial
Actores:
- Administrador
- Investigador
- Analista

---

## 12. Base de datos PostgreSQL

Base de datos:

`voxtrace_db`

Esquema:

`voxtrace`

El modelo ER ya fue definido y debe respetarse.

### 12.1 Tabla `rol`

- `id_rol` SERIAL PK
- `nombre` VARCHAR(50) NOT NULL UNIQUE
- `descripcion` VARCHAR(255)

Relación:
- `rol 1:N usuario`

### 12.2 Tabla `usuario`

- `id_usuario` SERIAL PK
- `id_rol` INTEGER NOT NULL FK
- `nombre` VARCHAR(100) NOT NULL
- `correo` VARCHAR(150) NOT NULL UNIQUE
- `password_hash` VARCHAR(255) NOT NULL
- `fecha_creacion` TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
- `estado` BOOLEAN NOT NULL DEFAULT TRUE

FK:
- `id_rol -> rol.id_rol`

Acciones:
- ON UPDATE CASCADE
- ON DELETE RESTRICT

### 12.3 Tabla `persona`

- `id_persona` SERIAL PK
- `identificador` VARCHAR(50) NOT NULL UNIQUE
- `alias` VARCHAR(100)
- `descripcion` TEXT
- `observaciones` TEXT
- `fecha_registro` TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP

### 12.4 Tabla `audio`

- `id_audio` SERIAL PK
- `id_persona` INTEGER NOT NULL FK
- `id_usuario` INTEGER NOT NULL FK
- `ruta_archivo` VARCHAR(500) NOT NULL
- `nombre_original` VARCHAR(255) NOT NULL
- `formato_original` VARCHAR(20) NOT NULL
- `duracion_segundos` NUMERIC(10,2)
- `hash_archivo` VARCHAR(128) NOT NULL UNIQUE
- `fecha_subida` TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP

FK:
- `id_persona -> persona.id_persona`
- `id_usuario -> usuario.id_usuario`

Checks:
- formato en mp3, ogg, mp4, wav
- duración positiva si existe

### 12.5 Tabla `embedding`

- `id_embedding` SERIAL PK
- `id_audio` INTEGER NOT NULL UNIQUE FK
- `vector` TEXT NOT NULL
- `modelo_utilizado` VARCHAR(150) NOT NULL
- `fecha_generacion` TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP

FK:
- `id_audio -> audio.id_audio`

Acciones:
- ON UPDATE CASCADE
- ON DELETE CASCADE

Nota:
`vector` permanece como TEXT inicialmente. Evaluar pgvector cuando el modelo y la dimensión sean definitivos.

### 12.6 Tabla `analisis`

- `id_analisis` SERIAL PK
- `id_usuario` INTEGER NOT NULL FK
- `ruta_audio_consulta` VARCHAR(500) NOT NULL
- `nombre_original` VARCHAR(255) NOT NULL
- `formato_original` VARCHAR(20) NOT NULL
- `hash_audio_consulta` VARCHAR(128) NOT NULL
- `fecha_analisis` TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
- `estado` VARCHAR(30) NOT NULL DEFAULT 'completado'

FK:
- `id_usuario -> usuario.id_usuario`

Checks:
- formato permitido
- estado en pendiente, procesando, completado, error

### 12.7 Tabla `resultado_analisis`

- `id_resultado` SERIAL PK
- `id_analisis` INTEGER NOT NULL FK
- `id_persona` INTEGER NOT NULL FK
- `similitud` NUMERIC(6,3) NOT NULL
- `posicion` INTEGER NOT NULL
- `supera_umbral` BOOLEAN NOT NULL DEFAULT FALSE

FK:
- `id_analisis -> analisis.id_analisis`
- `id_persona -> persona.id_persona`

Checks:
- similitud entre 0 y 100
- posición > 0

Unique:
- `(id_analisis, id_persona)`
- `(id_analisis, posicion)`

### 12.8 Tabla `log`

- `id_log` BIGSERIAL PK
- `id_usuario` INTEGER NULL FK
- `accion` VARCHAR(150) NOT NULL
- `fecha` TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
- `direccion_ip` VARCHAR(45)
- `detalles` TEXT

FK:
- `id_usuario -> usuario.id_usuario`

Acciones:
- ON UPDATE CASCADE
- ON DELETE SET NULL

---

## 13. Relaciones ER obligatorias

Mantener:
- `rol 1:N usuario`
- `usuario 1:N audio`
- `usuario 1:N analisis`
- `usuario 1:N log`
- `persona 1:N audio`
- `audio 1:1 embedding`
- `analisis 1:N resultado_analisis`
- `persona 1:N resultado_analisis`

No alterar cardinalidades sin autorización.

---

## 14. Estructura de proyecto objetivo

```text
VoxTrace/
├── AGENTS.md
├── README.md
├── requirements.txt
├── .gitignore
├── .env.example
├── backend/
│   ├── main.py
│   ├── api/
│   │   ├── auth.py
│   │   ├── usuarios.py
│   │   ├── personas.py
│   │   ├── muestras.py
│   │   ├── analisis.py
│   │   ├── historial.py
│   │   └── auditoria.py
│   ├── models/
│   ├── schemas/
│   ├── services/
│   │   ├── auth_service.py
│   │   ├── audio_service.py
│   │   ├── embedding_service.py
│   │   ├── comparison_service.py
│   │   ├── report_service.py
│   │   └── audit_service.py
│   ├── database/
│   │   ├── connection.py
│   │   └── migrations/
│   ├── security/
│   ├── core/
│   └── templates/
├── frontend/
│   ├── static/
│   │   ├── css/
│   │   ├── js/
│   │   └── img/
│   └── templates/
├── storage/
│   └── audio/
│       ├── originales/
│       ├── procesados/
│       └── temporales/
├── tests/
├── scripts/
└── docs/
```

No crear carpetas vacías innecesarias si todavía no se usan.

---

## 15. Pantallas y funcionalidades

### Login
- Logo VoxTrace.
- Usuario o correo.
- Contraseña.
- Mostrar/ocultar contraseña.
- Iniciar sesión.

### Dashboard
- Sidebar.
- Perfil y rol.
- Personas registradas.
- Muestras de voz.
- Análisis realizados.
- Análisis recientes.
- Actividad reciente.
- Estado de análisis.
- Accesos rápidos.

### Personas registradas
- Búsqueda.
- Filtro.
- Registrar persona.
- Tabla.
- Ver/editar.
- Eliminar solo si el rol lo permite.

### Registrar persona
Campos alineados al ER:
- Identificador.
- Alias.
- Descripción.
- Observaciones.

Nota importante:
El prototipo visual mostró un campo `Nombre`, pero la tabla `persona` NO tiene columna `nombre`.
No implementarlo sin migración aprobada.

### Gestionar muestras
- Persona seleccionada.
- Listado de muestras.
- Formato.
- Duración.
- Reproductor.
- Carga drag and drop.
- Guardar muestra.
- Eliminar según permisos.

### Analizar audio
- Carga de archivo.
- Información del archivo.
- Identificación 1:N.
- Verificación 1:1.
- Progreso:
  1. Cargando archivo.
  2. Procesando audio.
  3. Extrayendo características.
  4. Comparando con base.
  5. Generando resultados.

### Resultado de análisis
Debe mostrar:
- Archivo analizado.
- Fecha.
- Tipo de análisis.
- Top 3 posibles coincidencias.
- Posición 1, 2 y 3.
- Identificador.
- Alias.
- Porcentaje de similitud.
- Barra visual.
- Estado respecto al umbral.
- Ver perfil.
- Generar reporte.
- Nuevo análisis.

No usar foto real por defecto si no existe en BD.

### Historial
- Rango de fechas.
- Tipo.
- Resultado.
- Búsqueda.
- Tabla.
- Ver detalle.
- Generar reporte.

Preferir conservar historial para trazabilidad.

---

## 16. Diseño visual aprobado

### Tipografía
Familia:
- Inter

Usos:
- Inter Bold: títulos
- Inter SemiBold: subtítulos, botones y menú
- Inter Regular: tablas, formularios y texto general

### Colores principales
- Azul marino: `#0F2747`
- Azul institucional: `#2563A6`
- Blanco: `#FFFFFF`
- Gris claro: `#F3F4F6`
- Gris medio: `#64748B`
- Gris oscuro: `#1E293B`

### Colores de estado
- Verde: `#22C55E`
- Amarillo: `#F59E0B`
- Rojo: `#DC3545`

Reglas:
- Sidebar azul marino.
- Acciones principales azul.
- Éxito/supera umbral verde.
- Advertencia amarillo.
- Error rojo.
- Alto contraste.
- Diseño limpio y institucional.

---

## 17. Seguridad

Implementar:
- Hash seguro de contraseñas con Argon2 o bcrypt.
- Nunca guardar contraseñas en texto plano.
- Variables sensibles en `.env`.
- `.env` fuera de Git.
- RBAC.
- Validación backend.
- Protección de rutas.
- Límites de subida.
- Sanitización de nombres.
- No ejecutar archivos cargados.
- Control de acceso a archivos.
- Auditoría.
- Logging sin secretos.
- Sesiones o tokens con expiración.
- Cookies HttpOnly/Secure/SameSite cuando aplique.

---

## 18. Trazabilidad forense

Registrar cuando sea posible:
- Usuario.
- Fecha/hora.
- IP.
- Nombre original.
- Hash SHA-256.
- Tipo.
- Duración.
- Procesamientos.
- Modelo utilizado.
- Resultado.
- Porcentajes.
- Umbral.
- Errores.

No sobrescribir el archivo original.

---

## 19. Reportes

Un reporte deberá poder incluir:
- ID de análisis.
- Fecha.
- Usuario.
- Archivo.
- Hash.
- Tipo.
- Top 3.
- Porcentajes.
- Umbral.
- Estado.
- Modelo.
- Observaciones técnicas.

No afirmar identidad definitiva.

---

## 20. Pruebas

Crear pruebas para:
- Login.
- RBAC.
- Validación.
- Registro de persona.
- Subida de muestras.
- Hash.
- Conversión.
- Embeddings.
- Similitud.
- Top 3.
- Umbral.
- Historial.
- Auditoría.

No usar datos reales sensibles en pruebas automatizadas.

---

## 21. Métricas académicas

Preparar para medir:
- Precisión.
- Falsos positivos.
- Falsos negativos.
- Tiempo de procesamiento.
- Comportamiento por umbral.
- Top-1 accuracy.
- Top-3 accuracy.

No inventar métricas.

---

## 22. Orden de implementación

### Fase 1 — Base
- Git
- `.venv`
- FastAPI
- Configuración
- `.env`
- `/health`
- README

### Fase 2 — PostgreSQL
- Conexión.
- SQLAlchemy.
- Modelos idénticos al ER.
- Alembic.
- Prueba de conexión.

### Fase 3 — Seguridad
- Usuario.
- Rol.
- Login.
- Password hash.
- Sesión/token.
- RBAC.

### Fase 4 — Personas
- CRUD autorizado.
- Identificador único.

### Fase 5 — Muestras
- Upload.
- Metadatos.
- Almacenamiento.
- Hash.
- Reproductor.
- Validación.

### Fase 6 — Audio
- FFmpeg.
- Conversión WAV.
- Duración.
- Preprocesamiento.

### Fase 7 — Embeddings
- SpeechBrain.
- ECAPA-TDNN.
- Persistencia.

### Fase 8 — Comparación
- 1:N.
- 1:1.
- Coseno.
- Ranking.
- Top 3.
- Umbral.

### Fase 9 — Resultados
- Persistencia.
- Pantalla Top 3.

### Fase 10 — Historial y reportes
- Filtros.
- Reportes.

### Fase 11 — Auditoría
- Logs.

### Fase 12 — Validación final
- Seguridad.
- Métricas.
- Pruebas.
- LAN.

---

## 23. Reglas para Codex

1. Leer `AGENTS.md` antes de cualquier cambio.
2. Respetar PostgreSQL y el ER existente.
3. No agregar columnas por conveniencia.
4. No modificar relaciones sin aprobación.
5. Mantener arquitectura de tres capas.
6. Evitar código monolítico.
7. Separar servicios.
8. Usar type hints.
9. Documentar decisiones relevantes.
10. Mantener código comprensible para tesis.
11. Actualizar README.
12. No saltar a biometría antes de tener backend/base/seguridad.
13. No introducir cloud.
14. No introducir pagos.
15. No introducir librerías innecesarias.
16. No inventar datos sensibles.
17. No afirmar identificación definitiva.
18. Mantener Top 3 como requisito obligatorio.
19. Mantener compatibilidad con Windows.
20. Antes de cambios grandes, explicar el plan.
21. Ejecutar pruebas después de cambios importantes.
22. Si hay conflicto entre prototipo y ER, priorizar el ER y señalarlo.
23. Si una decisión no está definida, no asumirla silenciosamente.

---

## 24. Decisiones pendientes

Antes de fijar:
- frecuencia de muestreo;
- canales;
- dimensión del embedding;
- modelo exacto/versión de SpeechBrain;
- umbral;
- calibración;
- efecto de la duración sobre el desempeño biométrico;
- pgvector;
- estrategia final de sesión;
- retención;
- backups;

Codex debe presentar alternativas antes de implementar.

---

## 25. Primera tarea recomendada para Codex

Después de leer este archivo:

1. Verificar Python.
2. Crear `.venv` si no existe.
3. Crear estructura mínima.
4. Crear FastAPI con `/health`.
5. Crear `.env.example`.
6. Configurar conexión a `voxtrace_db`.
7. Crear modelos SQLAlchemy idénticos al ER.
8. Crear prueba de conexión.
9. No implementar todavía SpeechBrain.
10. Mostrar el plan y los cambios.

---

## 26. Criterio de finalización de la primera fase

La primera fase se considera correcta cuando:
- FastAPI inicia sin errores.
- `/health` responde.
- PostgreSQL `voxtrace_db` conecta.
- Los modelos corresponden al ER.
- No hay cambios no autorizados en la BD.
- Existe README.
- Existe `.env.example`.
- Git ignora `.env`, `.venv` y audios sensibles.


## Decisiones finales adicionales — 2026-09-06

Estas decisiones sustituyen cualquier instrucción anterior incompatible dentro de este documento:

- Decisión actualizada: VoxTrace no utiliza una duración mínima fija como criterio de aceptación. FFprobe debe seguir obteniendo una duración positiva y válida como metadato; el efecto de la duración sobre el rendimiento biométrico se evaluará experimentalmente.

- La tabla `voxtrace.persona` incluye oficialmente `nombre VARCHAR(150) NOT NULL`. La base actualmente no contiene datos registrados.
- Los audios se almacenan físicamente en el servidor bajo `storage/`; PostgreSQL conserva metadatos, rutas, hashes, relaciones, embeddings y resultados.
- Estructura aprobada: `storage/audio/referencias/originales`, `storage/audio/referencias/procesados`, `storage/audio/consultas/originales`, `storage/audio/consultas/procesados`.
- No utilizar `localStorage` del navegador para audios, credenciales, embeddings, información de personas, evidencia ni resultados.
- Conservar el audio original sin modificación, calcular SHA-256 y procesar una copia. Usar nombres físicos internos seguros (por ejemplo UUID) y conservar el nombre original en PostgreSQL.
- Durante desarrollo se usará `localhost`; en LAN los clientes accederán a la IP privada/nombre interno del servidor mediante navegador. Los clientes nunca se conectan directamente a PostgreSQL ni a las carpetas de audio.
- Frontend inicial: HTML, CSS, JavaScript y Jinja2 cuando corresponda.
- Autenticación inicial preferida: sesión/cookies seguras; no guardar tokens sensibles en `localStorage`. Contraseñas con hash moderno (preferentemente Argon2).
- No implementar eliminación física indiscriminada de análisis, resultados ni logs. Cualquier política de borrado/retención requiere aprobación.
- No implementar SpeechBrain todavía en Fase 1. Modelo exacto, muestreo, estrategia multimuestra, calibración, umbral y pgvector quedan pendientes de aprobación/validación.
- La identificación 1:N debe producir Top 3 posibles coincidencias, ordenadas por similitud, con porcentaje y estado respecto al umbral. El umbral definitivo no debe inventarse.

### Primera instrucción recomendada para Codex

```text
Lee completamente AGENTS_VoxTrace_Maestro.md y úsalo como la especificación principal de VoxTrace.

Estamos comenzando el desarrollo desde cero. Por ahora trabaja únicamente en la Fase 1.

Antes de crear o modificar archivos:
1. Revisa el estado actual del proyecto.
2. Resume brevemente lo que entendiste.
3. Propón la estructura mínima necesaria para la Fase 1.
4. Enumera los archivos que crearías.
5. No implementes SpeechBrain ni biometría todavía.
6. No modifiques, recrees ni migres PostgreSQL.
7. La tabla persona ya incluye nombre VARCHAR(150) NOT NULL.
8. Utiliza storage/ del servidor; no localStorage del navegador para datos del sistema.
9. Espera mi aprobación antes de crear archivos.
```
