# Reto — API FastAPI

Los contratos que hay que preservar están en `docs/ENDPOINTS.md`. Este archivo
es solo la lista de lo que hay que encontrar.

## Hallazgos sembrados

| Área | Caso | Objetivo |
|---|---|---|
| SCA | `urllib3 2.5.0` y `python-multipart 0.0.21` | Analizar CVEs y aplicar versiones corregidas. |
| Auth | Token Base64 con secreto embebido | Verificar firma, emisor, audiencia y expiración. |
| Autorización | El cliente puede consultar otro `owner` | Aplicar autorización por identidad/rol. |
| SQL | Filtros e inserts concatenados | Parametrizar consultas. |
| Files | Se conserva directamente `upload.filename` | Normalizar nombre, limitar extensión y tamaño. |
| Arquitectura | Rutas, DB, reglas y serialización en un archivo | Separar capas. |
| Calidad | `dict`, excepciones amplias, condicionales y duplicación | Aplicar Pydantic, tipos y funciones pequeñas. |

No se incluyen payloads de explotación.
