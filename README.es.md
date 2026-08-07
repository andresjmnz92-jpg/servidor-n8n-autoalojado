*[English](README.md) · **Español***

# Servidor de n8n autoalojado

Monto mi propio servidor de automatización en un VPS: n8n corriendo en Docker, con HTTPS
y dominio propio, para dejar de depender de la nube de otro y poder ofrecer automatización
a empresas que no quieren sus datos afuera.

**Servidor:** Hetzner CX23 (2 vCPU, 4 GB RAM, 40 GB) · Ubuntu 26.04 LTS · Falkenstein, Alemania
**Stack:** Docker + Docker Compose + n8n + Caddy
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

### Día 2 — 7 de agosto de 2026 · n8n con HTTPS y dominio propio

n8n corriendo detrás de Caddy, con certificado de Let's Encrypt que se renueva solo.
Desplegado sin editar un solo archivo en el servidor.

**El flujo, que es el punto de este día:**

1. Los archivos se escriben en el PC, dentro del repo clonado.
2. `git push` a GitHub.
3. En el servidor, `git clone` y `docker compose up -d`.

El servidor es runtime, no build server. Lo único que existe allá y no está en este repo es
el `.env` — porque contiene secretos y por definición no puede versionarse.

**Lo que se montó:**

- **Registro DNS tipo A** apuntando el subdominio al servidor, con el **proxy de Cloudflare
  apagado** (nube gris). Con el proxy encendido, Cloudflare intercepta el desafío de
  Let's Encrypt y el certificado nunca se emite.
- **Caddy** como proxy inverso. Consigue y renueva el certificado sin intervención, y añade
  cuatro cabeceras de seguridad (HSTS, nosniff, SAMEORIGIN, referrer-policy).
- **n8n sin puertos publicados.** No está expuesto a internet: solo Caddy lo está, y le pasa
  el tráfico por la red privada de Docker.
- **Secretos generados en el servidor**, nunca copiados de otro lado ni escritos a mano:
  `openssl rand -base64 32`. El `.env` con permisos `600`.
- **2FA activado** en la cuenta de dueño.

**Verificado, no asumido:**

- `docker compose exec n8n wget -qO- http://localhost:5678/healthz` → `{"status":"ok"}`
- `docker compose logs caddy | grep -i "certificate obtained"` → certificado emitido
- `/healthz` consultado desde fuera del servidor → HTTP 200
- Certificado emitido por Let's Encrypt, válido hasta el 5 de noviembre de 2026

**El error del día: rotar la clave de cifrado rompió n8n.**

Al cambiar `N8N_ENCRYPTION_KEY` en el `.env`, n8n entró en bucle de reinicio y el sitio
devolvía 502. El log dijo lo que ninguna guía decía:

```
Error: Mismatching encryption keys. The encryption key in the settings file
/home/node/.n8n/config does not match the N8N_ENCRYPTION_KEY env var.
```

**n8n guarda una segunda copia de la clave dentro de su volumen de datos.** Cambiar solo el
`.env` no basta: hay que actualizar también `/home/node/.n8n/config`.

Y hay una trampa antes de esa: la misma clave cifra el secreto del 2FA y sus códigos de
respaldo. Rotarla con el 2FA activo te deja fuera de tu propia instancia. **El 2FA se
desactiva antes de rotar y se reactiva después.**

Ninguna de las dos cosas salió buscando en Google. Salieron de leer los registros del
programa que estaba fallando.

**Siguiente:** automatizar el `git pull` del servidor con GitHub Actions.

---

## Qué falta

Esto es un laboratorio en construcción, no una plantilla terminada. Todavía no tiene
respaldos automáticos, ni monitoreo, ni despliegue automático. Va en ese orden.

## Nota de seguridad

Este repo es público. Aquí nunca entran: la llave SSH privada, archivos `.env`, ni
contraseñas. El `.gitignore` los bloquea.
