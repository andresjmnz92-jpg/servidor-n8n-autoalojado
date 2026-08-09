*[English](README.md) · **Español***

# n8n autoalojado — hecho para aguantar que lo ignoren

Mi propio servidor de automatización en un VPS: n8n en Docker, detrás de HTTPS en un dominio que
controlo. El punto no es ahorrarse la versión en la nube — es poder automatizar para empresas cuyos
datos no pueden salir de su propia infraestructura.

**Servidor:** Hetzner CX33 (4 vCPU, 8 GB de RAM, 40 GB) · Ubuntu 26.04 LTS · Falkenstein, Alemania
**Stack:** Docker + Docker Compose + n8n + Caddy · **~9 USD al mes**

---

## Qué corre encima, y cómo se mantiene en pie

No es una instancia de demostración. Ahí corre en producción el **bot de pedidos por Telegram de un
cliente**, más mis propias automatizaciones: un radar de empleo cada hora y un reporte semanal.

Cuatro cosas lo mantienen vivo sin mí:

| **Parcheo automático** | `unattended-upgrades` con ventana de reinicio a las 3 a.m. hora local |
| **Respaldos diarios** | volumen de n8n a las 2 a.m. → **Cloudflare R2**, 7 días dentro / 30 fuera |
| **Vigilante externo** | GitHub Actions pregunta por `/healthz` cada 30 min y avisa por correo |
| **HTTPS que se renueva solo** | Caddy + Let's Encrypt, sin intervención |

**Las dos alarmas se probaron en falso, no solo en verde.** Al vigilante se le apuntó a una ruta
que no existe para confirmar que se pone rojo. **Una alarma que nunca has visto sonar es una
suposición, no un aviso.**

**Y los respaldos se restauraron, no solo se escribieron.**

---

## El simulacro de restauración

Un respaldo guardado en el mismo disco que protege es una copia. Uno que nunca se ha restaurado es
una suposición. Esto se hizo el día dos **a propósito**: con la instancia casi vacía el simulacro
no da miedo, y lo que da miedo se aplaza para siempre.

Sin tocar la instancia viva: un volumen nuevo, un n8n desechable apuntando a él, y después
preguntarle qué tiene dentro.

```bash
docker volume create n8n_data_test
docker run --rm -v n8n_data_test:/data -v /home/user/backups:/backup alpine \
  sh -c "cd /data && tar xzf /backup/n8n-YYYY-MM-DD.tar.gz"
docker run -d --name n8n-test --env-file /ruta/al/.env \
  -v n8n_data_test:/home/node/.n8n docker.n8n.io/n8nio/n8n:stable
docker exec n8n-test n8n list:workflow      # <- la prueba
docker rm -f n8n-test && docker volume rm n8n_data_test
```

`n8n list:workflow` devolvió los workflows con sus IDs exactos, salidos de un `.tar.gz`. Después se
confirmó que la instancia viva seguía intacta y respondiendo 200 desde fuera.

**Tres cosas que enseñó el simulacro:**

- **El archivo `-wal` de SQLite es parte del respaldo.** `database.sqlite` era dos horas más viejo
  que `database.sqlite-wal`, y el trabajo más reciente vivía en ese `-wal`. Copiar solo el
  `.sqlite` habría restaurado una base sin las últimas horas.
- **Sin la clave de cifrado, el respaldo no abre.** El `.tar.gz` y la clave son dos piezas que solo
  funcionan juntas — por eso viven en sitios distintos.
- **Las restauraciones se prueban en un volumen aparte, nunca encima del vivo.** Un guion bajo
  separa `n8n_data_test` de `n8n_data`, y todos tus datos de ninguno.

---

## Tres fallos que vale la pena dejar escritos

### La clave de cifrado tiene una segunda copia

Rotar `N8N_ENCRYPTION_KEY` en el `.env` metió a n8n en un bucle de reinicios y el sitio empezó a
devolver 502. El registro decía lo que ninguna guía decía:

```
Error: Mismatching encryption keys. The encryption key in the settings file
/home/node/.n8n/config does not match the N8N_ENCRYPTION_KEY env var.
```

**n8n guarda una segunda copia de esa clave dentro de su propio volumen de datos.** Cambiar el
`.env` no basta: hay que actualizar también `/home/node/.n8n/config`.

Y hay una trampa anterior: esa misma clave cifra el secreto del 2FA y sus códigos de recuperación.
Rotarla con el 2FA activo te deja fuera de tu propia instancia. **Desactivar el 2FA antes de rotar.**

### Un cliente de hace cuatro años contra una API actual

Cada subida a R2 fallaba con `NotImplemented: 501` en el primer intento y funcionaba en el segundo.
El respaldo "funcionaba", pero dejaba un error en cada ejecución — el tipo de ruido que te entrena
a ignorar los errores.

Un archivo de prueba de **7 bytes** fallando igual lo delató: eso descarta tamaño, multipart y
chunking, y deja solo las cabeceras. La causa era la versión — `apt` trae rclone **v1.60.1, de
noviembre de 2022**. Con la compilación oficial (v1.75.0) el error desapareció, verificado con
`--retries 1` para que ningún reintento lo tapara.

> Ante un error raro de S3, revisar `rclone version` primero. Los paquetes de la distribución pueden
> ir años por detrás de los servicios con los que hablan.

### La ventana de reinicio va en UTC

`unattended-upgrades` ya estaba activo, pero **por defecto nunca reinicia** — así que los parches
del kernel se quedan descargados sin usar durante meses. El arreglo es un `99-automatic-reboot` con
una ventana horaria.

El detalle que casi todo el mundo pasa por alto: esa hora usa el reloj del sistema, que aquí está
en **UTC**. Poner "02:00" habría reiniciado la máquina a las 9 de la noche hora local, a media
tarde de trabajo. Está en `08:00` UTC — las 3 a.m. en Colombia.

---

## La lección que quitó más código: −46 líneas, +1

El vigilante se escribió primero como un script de Python de 30 líneas. Hacía exactamente lo mismo
que esto:

```
curl -fsS --retry 3 --retry-delay 20 "$N8N_URL/healthz" | grep -q '"ok"'
```

Borrar el script dejó además sin sentido el paso `actions/checkout` — ya no había archivo que
clonar. **Quitar código quitó una dependencia entera.**

---

## Bitácora de construcción

### Día 1 — 6 de agosto de 2026 · Endurecer primero, instalar después

El servidor se blindó antes de instalarle nada. El orden importa: un servidor recién creado empieza
a recibir intentos de acceso a los pocos minutos de estar en línea.

1. **Sistema actualizado** — `apt update && apt upgrade`, y reinicio.
2. **Un usuario normal con sudo** — se dejó de trabajar como `root`. Un error de tipeo como root
   borra el sistema; el mismo error como usuario normal, no.
3. **Solo autenticación por llave SSH** — par de llaves ed25519. La privada nunca sale de mi máquina.
4. **Contraseñas desactivadas** — en `/etc/ssh/sshd_config.d/99-endurecer.conf`, como archivo
   aparte en vez de editar `sshd_config`, para que sobreviva a las actualizaciones del paquete:
   ```
   PermitRootLogin no
   PasswordAuthentication no
   KbdInteractiveAuthentication no
   ```
5. **ufw activado** — SSH, 80 y 443 abiertos. Todo lo demás cerrado.
6. **Docker instalado** desde el repositorio oficial, con la firma GPG verificada.

**Verificado, no asumido:**

- `sudo sshd -T | grep -Ei "permitrootlogin|passwordauthentication"` → `no` y `no`
- Se abrió una segunda sesión con la llave *antes* de cerrar la que funcionaba
- `docker run hello-world` corrió · `docker compose version` → v5.4.0

**Dos cosas aprendidas a golpes:**

- **Leer el prompt antes de teclear.** `PS C:\...` es mi máquina; `user@homelab` es el servidor.
  Intenté hacer SSH al servidor desde dentro del servidor. Dos veces.
- **Permitir antes de activar.** `ufw allow OpenSSH` primero, `ufw enable` después. Al revés te deja
  fuera de tu propia máquina.

### Día 2 — 7 de agosto de 2026 · HTTPS en mi propio dominio

**El flujo de despliegue es lo importante de este día:**

1. Los archivos se escriben en mi máquina, dentro del repo clonado.
2. `git push` a GitHub.
3. En el servidor: `git pull` y `docker compose up -d`.

**El servidor es tiempo de ejecución, no servidor de compilación.** El único archivo que existe allí
y no en este repo es el `.env` — guarda secretos, así que por definición no se versiona.

**Lo que se montó:**

- **Un registro A** apuntando el subdominio al servidor, con el **proxy de Cloudflare desactivado**
  (nube gris). Con la nube naranja, Cloudflare intercepta el desafío ACME y el certificado nunca se
  emite.
- **Caddy** como proxy inverso — obtiene y renueva el certificado sin intervención, y añade cuatro
  cabeceras de seguridad (HSTS, nosniff, SAMEORIGIN, referrer-policy).
- **n8n no publica puertos.** No está expuesto a internet: solo Caddy lo está, y llega a n8n por la
  red privada de Docker.
- **Secretos generados en el servidor** con `openssl rand -base64 32`, nunca copiados de otro lado ni
  tecleados a mano. `.env` en modo `600`.
- **2FA activado** en la cuenta dueña.

**Verificado, no asumido:**

- `docker compose exec n8n wget -qO- http://localhost:5678/healthz` → `{"status":"ok"}`
- `docker compose logs caddy | grep -i "certificate obtained"` → certificado emitido
- `/healthz` pedido desde fuera del servidor → HTTP 200

---

## Lo que todavía falta

Va escrito porque un estado sin sus huecos no es un estado.

- **Los despliegues siguen siendo manuales.** `git pull` + `docker compose up -d` por SSH.
  Automatizarlo con GitHub Actions es el siguiente paso, y la forma segura es una llave restringida
  en `authorized_keys` con `restrict,command="/ruta/desplegar.sh"` — para que una llave filtrada
  solo pueda desplegar y nunca abrir una shell.
- **n8n corre en modo single con SQLite.** Suficiente para esta carga; un modo de cola con Postgres
  es lo que pediría un montaje multiinquilino.
- **Las actualizaciones de n8n son manuales a propósito.** `N8N_IMAGE_TAG` está fijado, porque rompe
  entre versiones mayores y actualizar sin supervisión lo que corre el bot de un cliente no es un
  riesgo que valga la pena automatizar.

## Una nota sobre secretos

Este repositorio es público. La llave SSH privada, los archivos `.env` y las contraseñas nunca entran
aquí, y el `.gitignore` los bloquea. La clave de cifrado de n8n en particular descifra todas las
credenciales guardadas — un respaldo sin ella es un archivo que nadie puede abrir, que es
exactamente por lo que las dos se guardan separadas.
