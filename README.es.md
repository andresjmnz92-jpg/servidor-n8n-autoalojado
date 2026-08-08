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

### Segunda parte del día · Que se cuide solo

Un servidor que hay que atender a mano no está terminado. Tres cosas, ningún script propio.

**Parches automáticos.** `unattended-upgrades` ya venía encendido, pero **por defecto nunca
reinicia** — así que los parches del kernel se quedan descargados sin efecto. Se añadió un
drop-in `99-reinicio-automatico` con la ventana de reinicio.

El detalle que se salta casi todo el mundo: esa hora usa el reloj del sistema, que aquí está en
**UTC**. Poner "02:00" habría reiniciado el servidor a las 9 de la noche, en plena hora de uso.
Va en `08:00` UTC, que son las 3 de la mañana en Colombia.

**Un vigilante que vive fuera del servidor.** Corre en las máquinas de GitHub cada 30 minutos y
pregunta si `/healthz` responde. Si no, el workflow termina en rojo y llega el correo.

Vive fuera a propósito: un monitor instalado en la máquina que vigila no puede avisar el día que
esa máquina se caiga.

**Respaldos diarios** del volumen de n8n a las 2 de la mañana, una hora antes del reinicio, con
borrado automático de los de más de 7 días. Sin esa limpieza, el disco se llena y el servidor
termina cayéndose por culpa de sus propios respaldos.

**La lección del día, en números: −46 líneas, +1.**

El vigilante se escribió primero como un script de Python de 30 líneas. Hacía exactamente lo
mismo que esto:

```
curl -fsS --retry 3 --retry-delay 20 "$N8N_URL/healthz" | grep -q '"ok"'
```

Al borrar el script también sobró el paso `actions/checkout`, porque ya no había ningún archivo
que descargar. Quitar código quitó una dependencia entera.

**Y la alarma se probó en los dos sentidos.** Verde con la URL buena, y **rojo** apuntándola a
una ruta que no existe. Una alarma que nunca se ha visto sonar es una suposición, no un aviso.

### Tercera parte · Sacar los respaldos y probar que sirven

Un respaldo guardado en el mismo disco que protege no es un respaldo, es una copia. Y uno que
nunca se ha restaurado no es un seguro, es una suposición. Las dos cosas se arreglaron el mismo
día.

**Fuera del servidor: Cloudflare R2.** 10 GB gratis permanentes. Los respaldos pesan ~480 KB, así
que noventa días caben en 40 MB. Se descartó pagar almacenamiento: no tiene sentido pagar por
mover 3 MB.

El token está limitado a **un solo bucket** con permiso de lectura y escritura de objetos. Si se
filtra, no alcanza nada más de la cuenta. Detalle que cuesta media hora si no se sabe: con un
token acotado así, `rclone` necesita `no_check_bucket = true` — si no, falla al intentar
comprobar un bucket que el token no puede listar.

**El bug que enseñó algo:** cada subida fallaba con `NotImplemented: 501` en el primer intento y
pasaba en el segundo. El respaldo "funcionaba", pero dejaba un error en cada corrida — el tipo de
ruido que acostumbra a ignorar los errores.

Lo delató un archivo de prueba de **7 bytes** que fallaba igual: eso descarta tamaño, subida por
partes y trozos, y deja solo los encabezados. La causa era la versión: `apt` instala rclone
**v1.60.1, de noviembre de 2022**. Un cliente de hace cuatro años hablándole a un servicio que ya
no acepta lo que le manda. Con la versión oficial (v1.75.0) el error desapareció, verificado con
`--retries 1` para que ningún reintento lo tapara.

> Ante un error raro de S3, lo primero es `rclone version`. Las herramientas de `apt` pueden ir
> años por detrás de los servicios en la nube con los que hablan.

**La restauración, probada de verdad.** Sin tocar la instancia viva: volumen nuevo, un n8n
temporal apuntando a él, y a preguntarle qué tiene adentro.

```bash
docker volume create n8n_data_prueba
docker run --rm -v n8n_data_prueba:/data -v /home/usuario/respaldos:/backup alpine \
  sh -c "cd /data && tar xzf /backup/n8n-AAAA-MM-DD.tar.gz"
docker run -d --name n8n-prueba --env-file /ruta/al/.env \
  -v n8n_data_prueba:/home/node/.n8n docker.n8n.io/n8nio/n8n:stable
docker exec n8n-prueba n8n list:workflow      # <- la prueba
docker rm -f n8n-prueba && docker volume rm n8n_data_prueba
```

`n8n list:workflow` devolvió los workflows con sus IDs exactos, salidos de un `.tar.gz`. Después
se comprobó que la instancia real seguía intacta y respondiendo 200 desde fuera.

**Tres cosas que enseñó el ejercicio:**

- **El `-wal` de SQLite es parte del respaldo.** El `database.sqlite` era de dos horas antes que
  el `database.sqlite-wal`, y en ese `-wal` vivía el trabajo más reciente. Copiar solo el
  `.sqlite` habría restaurado una base sin las últimas horas. Copiar el volumen completo evita
  ese error clásico.
- **Sin la clave de cifrado, el respaldo no abre.** El `.tar.gz` y la clave son dos piezas que
  solo sirven juntas, y por eso viven en sitios distintos.
- **La restauración se prueba en un volumen aparte, nunca encima del vivo.** Entre
  `n8n_data_prueba` y `n8n_data` hay un guion bajo de diferencia y todos los datos del mundo.

**Y se hizo hoy a propósito:** con la instancia casi vacía el ejercicio no da miedo. Con
credenciales de clientes adentro, da miedo — y lo que da miedo se pospone para siempre.

**Siguiente:** automatizar el `git pull` con GitHub Actions.

---

## Qué falta

Esto es un laboratorio en construcción, no una plantilla terminada. Todavía no tiene
respaldos automáticos, ni monitoreo, ni despliegue automático. Va en ese orden.

## Nota de seguridad

Este repo es público. Aquí nunca entran: la llave SSH privada, archivos `.env`, ni
contraseñas. El `.gitignore` los bloquea.
