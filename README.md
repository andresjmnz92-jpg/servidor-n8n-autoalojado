# servidor-n8n-autoalojado
n8n autoalojado con Docker y HTTPS en un VPS propio: montaje, seguridad y despliegue paso a paso.

# Servidor de n8n autoalojado

Monto mi propio servidor de automatización en un VPS: n8n corriendo en Docker, con HTTPS
y dominio propio, para dejar de depender de la nube de otro y poder ofrecer automatización
a empresas que no quieren sus datos afuera.

**Servidor:** Hetzner CX23 (2 vCPU, 4 GB RAM, 40 GB) · Ubuntu 26.04 LTS · Falkenstein, Alemania
**Stack:** Docker + Docker Compose + n8n
**Costo:** ~7 USD al mes

---

## Bitácora

### Día 1 — 6 de agosto de 2026 · El servidor, asegurado

Servidor creado y endurecido antes de instalar nada. El orden importa: un servidor recién
creado empieza a recibir intentos de acceso a los pocos minutos de estar en línea.

**Lo que se hizo:**

1. **Sistema actualizado** — `apt update && apt upgrade` y reinicio.
2. **Usuario propio con sudo** — se dejó de trabajar como `root`. Un error tecleado como
   root borra el sistema; como usuario normal, no.
3. **Acceso solo con llave SSH** — se generó un par de llaves ed25519. La pública vive en
   el servidor, la privada nunca sale de mi PC.
4. **Contraseñas desactivadas** — archivo `/etc/ssh/sshd_config.d/99-endurecer.conf` con:
   ```
   PermitRootLogin no
   PasswordAuthentication no
   KbdInteractiveAuthentication no
   ```
   Sin contraseña que adivinar, la fuerza bruta deja de ser una amenaza.
5. **Cortafuegos ufw activo** — solo abiertos SSH, 80 y 443. Todo lo demás, cerrado.
6. **Docker instalado** desde el repositorio oficial, verificando la firma GPG.
   `docker run hello-world` corrió correctamente. Docker Compose v5.4.0.

**Verificado, no asumido:**
- `sudo sshd -T | grep -Ei "permitrootlogin|passwordauthentication"` → `no` y `no`
- Sesión nueva abierta con la llave antes de cerrar la que funcionaba
- `docker run hello-world` ejecutó el contenedor de prueba
- `docker compose version` → v5.4.0

**Dos cosas que aprendí a golpes:**

- **Mirar el prompt antes de teclear.** `PS C:\...` es mi PC; `usuario@homelab` es el
  servidor. Intenté conectarme por SSH desde dentro del servidor, dos veces.
- **Autorizar antes de encender el cortafuegos.** Primero `ufw allow OpenSSH`, después
  `ufw enable`. Al revés te deja afuera de tu propio servidor.

**Siguiente:** apuntar un subdominio al servidor y levantar n8n con HTTPS.

---

## Nota de seguridad

Este repo es público. Aquí nunca entran: la llave SSH privada, archivos `.env`, ni
contraseñas. El `.gitignore` los bloquea.

