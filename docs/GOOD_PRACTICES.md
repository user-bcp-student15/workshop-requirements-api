# Buenas prácticas — API FastAPI

> Convenciones a las que debe converger el refactor. Se
> consultan durante el refactor, no después.

- **Modelos Pydantic**: request y response tipados, no `dict[str, Any]` crudo.
- **Capas separadas**: rutas (FastAPI) → servicio (reglas) → repositorio (SQL
  parametrizado). Nada de SQL directo dentro de la función de la ruta.
- **Autenticación real**: verificar firma, emisor, audiencia y expiración del
  token. Nada de decodificar Base64 y confiar en el contenido.
- **Autorización por identidad**: las consultas siempre usan
  `identity["username"]` (lo que viene del token verificado), nunca un
  parámetro `owner` que manda el cliente.
- **Archivos subidos**: normalizar el nombre, limitar extensión permitida y
  tamaño máximo antes de guardar. Nunca usar `file.filename` tal cual.
- **Errores**: `HTTPException` con mensajes genéricos. Nunca el `str(exception)`
  crudo en la respuesta al cliente.
- **Dependencias**: versiones sin CVEs conocidos; no silenciar advisories.
