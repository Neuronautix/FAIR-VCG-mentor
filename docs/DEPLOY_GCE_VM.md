# Deploying FAIR CSV Mentor on a GCE VM

These instructions deploy the demo on a Google Compute Engine (GCE) e2-small or larger VM
running Debian/Ubuntu, using Docker Compose + Caddy for TLS.

## 1. Create the VM

```bash
gcloud compute instances create fair-mentor-demo \
  --machine-type=e2-small \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --boot-disk-size=20GB \
  --tags=http-server,https-server \
  --zone=us-central1-a
```

Allow HTTP/HTTPS traffic:

```bash
gcloud compute firewall-rules create allow-http \
  --allow tcp:80 \
  --target-tags http-server

gcloud compute firewall-rules create allow-https \
  --allow tcp:443 \
  --target-tags https-server
```

## 2. Install Docker and Docker Compose

SSH into the VM, then:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Install Docker Compose plugin
sudo apt-get update && sudo apt-get install -y docker-compose-plugin
docker compose version  # verify
```

## 3. Clone the repository

```bash
git clone https://github.com/your-org/FAIR-VCG-mentor.git
cd FAIR-VCG-mentor
git checkout deploy/fair-only-demo
```

## 4. Configure environment

```bash
cp .env.example .env
nano .env   # edit the variables below
```

Edit `.env`:

```
SESSION_DB=/data/sessions.db
CORS_ORIGINS=https://your-domain.example.com
OPENAI_MODEL=gpt-4o-mini
MAX_UPLOAD_MB=32
ENVIRONMENT=production
```

## 5. Configure Caddy

```bash
cp Caddyfile.example Caddyfile
nano Caddyfile
```

Replace `your-demo-domain.example` with your actual domain. To enable basic auth:

```bash
docker run --rm caddy:2-alpine caddy hash-password --plaintext 'yourpassword'
# Copy the hash into the basicauth block in Caddyfile
```

## 6. Create persistent data volume

```bash
sudo mkdir -p /data
sudo chown $USER /data
```

## 7. Build and start

```bash
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
```

Check health:

```bash
curl http://localhost:8000/api/health
docker compose -f docker-compose.prod.yml logs -f backend
```

Caddy will automatically provision a TLS certificate via Let's Encrypt once DNS is configured.

## 8. Point DNS to your VM

Get the VM's external IP:

```bash
gcloud compute instances describe fair-mentor-demo \
  --zone=us-central1-a \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)'
```

Create an A record: `your-domain.example.com` → `<external IP>`

Wait for DNS propagation (typically 1-5 minutes), then visit `https://your-domain.example.com`.

## 9. Updating the deployment

```bash
cd FAIR-VCG-mentor
git pull
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
```

## 10. Stopping the deployment

```bash
docker compose -f docker-compose.prod.yml down
```

## Security notes

- The OpenAI API key is stored only in server RAM. It is never written to the SQLite
  database or log files. It will be lost when the backend container restarts — users
  must re-enter it from the Settings page.
- The `.env` file contains your CORS origins. Do not commit it to version control.
- Enable GCE OS Login and restrict SSH access to your IP for production use.
- The `Caddyfile` is in `.gitignore` to prevent accidental commits of your domain config.

## Troubleshooting

### Backend does not start

```bash
docker compose -f docker-compose.prod.yml logs backend
```

Common causes: missing `/data` directory, SQLite permission error, missing env vars.

### Caddy cannot provision TLS certificate

- Verify DNS is pointing to the VM's IP
- Ensure ports 80 and 443 are open in the GCE firewall rules
- Check Caddy logs: `docker compose -f docker-compose.prod.yml logs caddy`

### File upload fails with 413

Increase `MAX_UPLOAD_MB` in `.env` and restart the backend.
