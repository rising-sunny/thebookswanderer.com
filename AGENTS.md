# Continuidad y credenciales

Lee primero [docs/CONTINUITY.md](docs/CONTINUITY.md). Es la guía para retomar
The Books Wanderer desde otra cuenta o entorno; distingue hechos comprobados,
estado reportado y tareas pendientes.

- Las credenciales de proveedores y las operaciones con esos proveedores deben
  permanecer en el VPS. No copies `.env`, claves, tokens, bases de producción ni
  archivos de credenciales a Codex, al repositorio o a la conversación.
- Desarrolla y prueba localmente con datos ficticios, bases temporales y clientes
  simulados. Para consultar producción, usa el MCP autorizado del VPS si está
  disponible. Si falta acceso, prepara el comando para que el dueño lo ejecute
  allí y devuelve únicamente estados sanitizados, nunca los valores secretos.
- Autorizar GitHub no autoriza el VPS. Conectar un repositorio no conecta su MCP.
  La disponibilidad de herramientas y las autorizaciones se comprueban en cada
  sesión; no se heredan del historial de otra cuenta.
- No vuelques el entorno, `.env`, `/proc/*/environ`, claves privadas ni logs sin
  filtrar en salidas. Si necesitas comprobar presencia de una credencial en el
  VPS, muestra solamente su nombre y un booleano o estado.
- Antes de usar instrucciones antiguas que proponen copiar claves al entorno
  local, aplica la política actual de credenciales exclusivamente en el VPS.
- `main` activa un despliegue automático (salvo cambios solo en `*.md`,
  `docs/`, `deploy/admin-api/` o `deploy/mcp/`). Trabaja en una rama y prepara
  un PR; no mezcles una actualización documental con un despliegue no solicitado.
- Una solicitud de diagnóstico no autoriza pagos, pedidos reales, publicación
  de productos, mensajes o anuncios. Respeta el alcance solicitado y las
  autorizaciones explícitas vigentes; no asumas que todas las integraciones
  tienen las mismas capacidades o restricciones.
