# Deploy BOWLINGER on Ubuntu 24.04

These steps are for the server **BALU-001**. The app listens on port **8741** on all interfaces (`0.0.0.0`). Uploaded videos and the SQLite database live in two Docker volumes, so they survive image rebuilds.

## Install Docker and Git LFS

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git git-lfs
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
git lfs install
```

Log out and back in so the `docker` group applies.

## Clone and start

```bash
git clone https://github.com/gargee1608/bowlinger-ai.git
cd bowlinger-ai
git lfs pull
docker compose up -d --build
```

`git lfs pull` is required. `models/cricket.pt` and `Sample/*.mp4` are Git LFS files. The image build downloads `models/yolo11n.pt` if that file is missing, and it refuses to build if `models/cricket.pt` is still an LFS pointer.

Open `http://BALU-001:8741` from a machine that can reach the server, or `http://127.0.0.1:8741` on the server itself.

History and training are open when `BOWLINGER_ADMIN_PASSWORD` is unset or empty. Set it to require a password. Compose reads it from the environment. It is not written into the database.

```bash
export BOWLINGER_ADMIN_PASSWORD='choose-a-password'
docker compose up -d --build
```

| Page | URL |
| --- | --- |
| Analyse | `http://BALU-001:8741/` |
| One saved result | `http://BALU-001:8741/s/<session id>` (the history page uses the relative link `/s/<session id>`) |
| Save history | `http://BALU-001:8741/admin/history` |
| Box training | `http://BALU-001:8741/train` |
| Audio training | `http://BALU-001:8741/train/audio` |

`ffmpeg` is installed in the image. `yt-dlp` is installed from `requirements.txt`. A YouTube link is downloaded and analysed like an upload. The URL itself is not stored.

```bash
docker compose ps
docker compose logs -f bowlinger
```

Videos are in the `bowlinger-videos` volume (`/data` in the container). The database is `bowlinger.db` in the `bowlinger-db` volume.

## Update

```bash
cd bowlinger-ai
git pull
git lfs pull
docker compose up -d --build
```

Compose recreates the container with `restart: unless-stopped`. The two volumes are left in place.

## Tailscale

Use this when the people opening BOWLINGER are already on the tailnet. The port stays off the public internet.

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
tailscale ip -4
```

Then open `http://<tailscale-ip>:8741`. The name `BALU-001` also works from other tailnet machines if MagicDNS is on.

## Cloudflare Tunnel

Use this for an HTTPS name without opening port 8741 on the router.

```bash
curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o /tmp/cloudflared.deb
sudo apt-get install -y /tmp/cloudflared.deb
cloudflared tunnel login
cloudflared tunnel create bowlinger
cloudflared tunnel route dns bowlinger bowlinger.example.com
```

`~/.cloudflared/config.yml`:

```yaml
tunnel: bowlinger
credentials-file: /home/ubuntu/.cloudflared/<TUNNEL-ID>.json
ingress:
  - hostname: bowlinger.example.com
    service: http://127.0.0.1:8741
  - service: http_status:404
```

```bash
sudo cloudflared service install
sudo systemctl enable --now cloudflared
```

Replace the hostname and the credentials path with the values Cloudflare printed. A quick test without a name is `cloudflared tunnel --url http://127.0.0.1:8741`.
