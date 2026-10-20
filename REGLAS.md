# Contrato para agentes

1. Conserva los endpoints y formatos usados por el frontend.
2. Agrega pruebas de caracterización antes de separar el monolito.
3. No conviertas un hallazgo en un `# noqa` o exclusión de scanner.
4. Mantén consultas parametrizadas y autorización ligada a la identidad.
5. Controla nombre, tamaño y extensión de archivos.
6. No uses secretos reales ni valores de producción.
7. Meta de cobertura del código modificado: 85% o superior.

## Clean code

8. Cada función hace una sola cosa; si una ruta valida, arma el SQL y
   serializa la respuesta a la vez (como en `app/main.py` hoy), sepáralo en
   capas (ruta / servicio / repositorio).
9. Nombres que expliquen el propósito, no el tipo (evitar `data`, `temp`,
   `result2`, `handle_stuff`).
10. Sin duplicación: un bloque de código repetido en dos lugares se extrae a
    una función reutilizable.
11. Evitar anidamiento profundo (`if` dentro de `if` dentro de `if`, como en
    `summary()` hoy); usar retorno anticipado o condiciones combinadas.
12. Sin números o strings "mágicos" sueltos en el código; usar constantes con
    nombre.
