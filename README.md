# docker-vps-starter

[![CI](https://github.com/Aleksandar0232/docker-vps-starter/actions/workflows/ci.yml/badge.svg)](https://github.com/Aleksandar0232/docker-vps-starter/actions/workflows/ci.yml)

A small, real multi-container project for learning Docker Compose on a **cPanel/WHM VPS**. It runs next to Apache without touching ports 80/443.

Three containers work together: **nginx** takes the requests, a **Python (Flask) app** handles them, and **Redis** stores a visit counter that survives restarts, rebuilds and reboots.

```
  Internet
     │
     ▼  YOUR-SERVER-IP:8080
┌─────────┐             ┌─────────┐             ┌─────────┐
│  nginx  │ ──────────► │   app   │ ──────────► │  redis  │
│ (proxy) │  frontend   │ (Flask) │   backend   │ (data)  │
└─────────┘             └─────────┘             └────┬────┘
                                                     │
                                            volume: redis-data

Apache (cPanel) keeps ports 80 and 443. Nothing here touches it.
```

Only nginx is published on the server. The app and Redis can't be reached from the internet, and nginx can't reach Redis either. Each container can only talk to what it needs.

---

## What's in the repo

```
docker-vps-starter/
├── compose.yaml          # the whole stack: 3 services, 2 networks, 1 volume
├── .env.example          # settings template (port, bind IP, title, timezone)
├── app/
│   ├── Dockerfile        # recipe for building the app image
│   ├── main.py           # the Flask app (visit counter + /health + /api/stats)
│   ├── templates/index.html
│   └── requirements.txt  # pinned Python dependencies
├── nginx/default.conf    # reverse-proxy config
├── tests/test_app.py     # unit tests (run without Docker)
└── .github/workflows/ci.yml  # GitHub builds & tests the full stack on every push
```

## Four words you need

| Word | Meaning | In this project |
|---|---|---|
| **Image** | A read-only template: OS files + your app + its dependencies | `nginx:stable-alpine`, `redis:7-alpine` (pulled), `docker-vps-starter-app` (built by you) |
| **Container** | A running (or stopped) instance of an image | `docker-vps-starter-nginx-1`, `-app-1`, `-redis-1` |
| **Volume** | Storage that lives outside the container, so data survives it | `redis-data` holds the counter |
| **Network** | A private virtual network; containers on it find each other **by service name** | `frontend` (nginx↔app), `backend` (app↔redis) |

---

## Step-by-step on the VPS

All commands run as `root` over SSH (or WHM → Terminal).

### Step 1: Clean up the first experiments

What your earlier commands actually did:

- `docker run hello-world!` gave **invalid reference format** because image names may only contain lowercase letters, digits and `.` `_` `-` `/` `:`. The `!` broke it.
- `docker run hello-world` works, but **every** `docker run` creates a brand-new container that stays behind after it exits. Add `--rm` to auto-delete it: `docker run --rm hello-world`.
- `my-nginx` with status **Created** means Docker made the container but it **never started**. On a cPanel server this almost always means it asked for port 80, which Apache already holds.

See the real reason, then clean up:

```bash
docker start my-nginx          # shows the error, e.g. "port is already allocated" / "address already in use"
ss -tlnp | grep -E ':(80|443) '   # you'll see httpd (Apache) owns 80 and 443

docker rm my-nginx             # delete that container
docker container prune         # delete ALL stopped containers (the hello-world ones); asks y/N
docker ps -a                   # should now be empty
```

### Step 2: Make sure Docker starts on boot and Compose is installed

```bash
systemctl enable --now docker    # start now + start after every reboot
docker compose version           # e.g. "Docker Compose version v2.x"
```

If you get `'compose' is not a docker command`, install the plugin (AlmaLinux/CentOS with Docker's repo):

```bash
dnf install -y docker-compose-plugin
```

### Step 3: Check the port is free

We use **8080** on the server because Apache has 80/443.

```bash
ss -tlnp | grep ':8080 '     # no output = free
```

If something is listed, pick another port (e.g. 8090) in Step 5.

### Step 4: Get the code

```bash
cd /opt
git clone https://github.com/Aleksandar0232/docker-vps-starter.git
cd docker-vps-starter
```

`/opt` keeps the project separate from cPanel accounts in `/home`.

### Step 5: Create your settings file

```bash
cp .env.example .env
nano .env        # or: vi .env
```

| Setting | Default | What it does |
|---|---|---|
| `HOST_PORT` | `8080` | Port on the server that nginx listens on |
| `BIND_IP` | `0.0.0.0` | `0.0.0.0` = reachable from the internet; `127.0.0.1` = only from the server itself (Step 11) |
| `APP_TITLE` | `Docker VPS Starter` | Page title |
| `TZ` | `UTC` | Timezone for the app, e.g. `Europe/Belgrade` |

Compose reads `.env` automatically. `.env` is in `.gitignore`, so your real settings never get pushed to GitHub.

### Step 6: Build and start everything

```bash
docker compose up -d --build
```

What happens, in order:

1. **Pull** `nginx:stable-alpine` and `redis:7-alpine` from Docker Hub.
2. **Build** the app image from `app/Dockerfile`: start from Python 3.12, install requirements, copy code, switch to a non-root user.
3. **Create** networks `frontend` + `backend` and volume `redis-data`.
4. **Start in dependency order**: Redis first, then the app once Redis is *healthy*, then nginx once the app is *healthy* (`depends_on` + `healthcheck` in `compose.yaml`).

`-d` = detached (runs in the background). `--build` = rebuild the app image if the code changed.

### Step 7: Check that it works

```bash
docker compose ps                              # STATUS should say "Up … (healthy)" for all 3
curl -s http://127.0.0.1:8080/api/stats        # JSON with the visit counter
docker compose logs -f app                     # live logs (Ctrl+C to exit)
```

Then open **`http://YOUR-SERVER-IP:8080`** in a browser. Refresh a few times and the counter goes up.

### Step 8: Firewall (only if the browser can't reach it)

Docker adds its own `iptables` rules for published ports, and these usually apply **before** the host firewall's normal input rules. So a published port is often reachable even though CSF doesn't list it. Two consequences:

- **If you want something private, don't rely on the firewall. Bind it to `127.0.0.1`** (see `BIND_IP`). That's also why Redis has no `ports:` at all.
- If the page still doesn't load from outside, add `8080` to `TCP_IN` in `/etc/csf/csf.conf` and run `csf -r`.

> **CSF gotcha:** restarting CSF (`csf -r`) flushes iptables, which can delete Docker's rules. Symptoms: the page stops loading, or containers lose internet access. Fix: `systemctl restart docker` (containers come back automatically thanks to `restart: unless-stopped`). Newer CSF versions have a `DOCKER` option in `csf.conf` meant to handle this; check the comments in your `csf.conf`.

### Step 9: Experiments that teach you Docker

**a) Data survives: volumes**

```bash
docker compose down        # stop and DELETE all 3 containers
docker compose up -d       # create them again
```

The counter is still there, because it lives in the `redis-data` volume, not in the container. Now try `docker compose down -v`: the `-v` deletes volumes too, and the counter resets. `docker volume ls` shows your volumes.

**b) Self-healing: restart policy**

```bash
docker compose exec redis redis-cli shutdown   # crash Redis on purpose
docker compose ps                              # a few seconds later: redis is back up
```

`restart: unless-stopped` restarts any container that stops on its own, and the counter is intact because Redis writes to disk (`--appendonly yes`).

**c) Run 3 copies of the app: scaling**

```bash
docker compose up -d --scale app=3
docker compose restart nginx       # nginx looks up the app copies when it starts
```

Refresh the page. **"Answered by container"** changes and the table shows visits split across 3 containers. All three share one Redis, so the total stays consistent. Go back with `--scale app=1` and restart nginx again.

**d) Look inside containers**

```bash
docker compose exec app sh                          # a shell inside the app container (type exit to leave)
docker compose exec redis redis-cli get visits:total
docker compose exec nginx ping -c1 app              # works: both on "frontend"
docker compose exec nginx ping -c1 redis            # "bad address": nginx can't even see redis
```

**e) Resource usage and limits**

```bash
docker stats --no-stream      # CPU / memory per container
```

`compose.yaml` caps memory (nginx 64M, app 256M, redis 64M), so one container can't eat the whole VPS.

### Step 10: Update after a change

Edit something (e.g. `APP_TITLE` in `.env`, or `app/templates/index.html`), then:

```bash
git pull                        # if the change came from GitHub
docker compose up -d --build    # only changed containers are recreated
```

### Step 11 (optional): Put it on a real domain through cPanel's Apache

This gives you `https://app.yourdomain.com` with a free AutoSSL certificate, and port 8080 is closed to the outside.

1. In `.env` set `BIND_IP=127.0.0.1`, then `docker compose up -d`.
2. In cPanel, create the subdomain (e.g. `app.yourdomain.com`) so AutoSSL issues a certificate for it.
3. Add an Apache include for that subdomain (replace `CPUSER` and the domain):

```bash
CPUSER=youruser
DOMAIN=app.yourdomain.com
for t in std ssl; do
  mkdir -p /etc/apache2/conf.d/userdata/$t/2_4/$CPUSER/$DOMAIN
  cat > /etc/apache2/conf.d/userdata/$t/2_4/$CPUSER/$DOMAIN/docker-proxy.conf <<'EOF'
ProxyPreserveHost On
ProxyPass        /.well-known/ !
ProxyPass        / http://127.0.0.1:8080/
ProxyPassReverse / http://127.0.0.1:8080/
EOF
done

httpd -M | grep proxy_http                           # confirm mod_proxy_http is loaded
/scripts/rebuildhttpdconf && /scripts/restartsrv_httpd
```

The `/.well-known/ !` line keeps AutoSSL validation working. To undo: delete those two `docker-proxy.conf` files, then rebuild and restart Apache again.

---

## Everyday commands

Run these from the project folder (`/opt/docker-vps-starter`).

| Task | Compose (this project) | Plain Docker equivalent |
|---|---|---|
| What's running | `docker compose ps` | `docker ps` |
| Start / create everything | `docker compose up -d` | `docker run …` for each |
| Stop (keep containers) | `docker compose stop` | `docker stop NAME` |
| Start again | `docker compose start` | `docker start NAME` |
| Stop and remove containers | `docker compose down` | `docker rm NAME` |
| Logs | `docker compose logs -f app` | `docker logs -f NAME` |
| Published ports | `docker compose port nginx 80` | `docker port NAME` |
| Shell inside | `docker compose exec app sh` | `docker exec -it NAME sh` |
| Disk used by Docker | `docker system df` | same |
| Remove unused images/cache | `docker image prune` / `docker builder prune` | same |

> `docker system prune` removes **all** stopped containers, unused networks and dangling images. Adding `--volumes` also deletes unused volumes, which means **data**. Read the prompt before typing `y`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `port is already allocated` / `address already in use` | Something already listens on `HOST_PORT` | `ss -tlnp \| grep :8080`, then change `HOST_PORT` in `.env` |
| Container stuck in **Created** | It failed to start | `docker start NAME` prints the reason |
| Build fails at `pip install` with `Temporary failure in name resolution` | Containers have no internet: Docker's firewall/NAT rules are missing (often wiped by a CSF restart) or IP forwarding is off | Test: `docker run --rm busybox ping -c 2 1.1.1.1`. Fix: `systemctl restart docker`, and check `sysctl net.ipv4.ip_forward` says `1` |
| `'compose' is not a docker command` | Compose plugin missing | `dnf install -y docker-compose-plugin` |
| `502 Bad Gateway` after scaling | nginx still points at old app copies | `docker compose restart nginx` |
| Page stopped loading after `csf -r` | CSF flushed Docker's iptables rules | `systemctl restart docker` |
| Page says **Redis is not reachable** | Redis down/restarting | `docker compose ps`, `docker compose logs redis` |
| Warning: *kernel does not support memory limit* | VPS kernel/cgroup limitation | Harmless; limits are just ignored |
| `permission denied … docker.sock` as a cPanel user | User not in `docker` group | `usermod -aG docker USER`. Note: the docker group is effectively **root** access |
| Disk filling up | Old images / build cache | `docker system df`, then `docker image prune`, `docker builder prune` |

## Tests

```bash
pip install -r app/requirements.txt
python -m unittest discover -s tests -v
```

On every push, GitHub Actions (`.github/workflows/ci.yml`) runs the unit tests, then **builds the real images, starts the full stack**, and checks that the counter increments through nginx, the data survives `down`/`up`, security headers are present, and Redis is **not** exposed on the host.

## Remove everything

```bash
cd /opt/docker-vps-starter
docker compose down -v --rmi all     # containers + networks + volume + all 3 images
cd .. && rm -rf docker-vps-starter
```

## License

MIT, see [LICENSE](LICENSE).
