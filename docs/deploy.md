# Deploying Imagery to armitage

armitage already fronts everything with **nginx-proxy-manager**, and NPM reaches
backends through the **docker0 gateway `172.17.0.1`** -- never by container name,
never over loopback. `app/docker-compose.yml` therefore publishes on
`172.17.0.1:8010`, which is reachable by NPM and invisible to the LAN.

> This is the same trap that bit OkuLaser: binding `127.0.0.1` makes the app
> unreachable from NPM and takes the site down; binding `0.0.0.0` exposes it to
> the whole LAN, bypassing the proxy. See `findings-from-screenshots.md` and the
> vault note.

## Steps

```bash
# on armitage
git clone <this repo> ~/imagery && cd ~/imagery/app
cp .env.example .env         # leave IMAGERY_ADMIN_PASSPHRASE empty
docker compose up -d --build
docker compose logs | grep setup/      # the one-time admin link
```

Then in NPM at `armitage:81`:

1. **Hosts -> Proxy Hosts -> Add Proxy Host**
2. Domain: the hostname you want. Forward to **`172.17.0.1`** port **`8010`**.
3. Tick **Block Common Exploits** and **Websockets Support**.
4. **SSL tab -> Request a new SSL Certificate**, plus **Force SSL** and **HTTP/2**.
   Leave HSTS off until you have confirmed HTTPS works -- it is sticky in browsers.

`IMAGERY_SECURE_COOKIE` must stay `1` once it is behind HTTPS, which is the default.

## Checks after deploying

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://<host>/healthz     # 200
curl -sI https://<host>/ | grep -i content-security                 # CSP present
# and from another machine on the LAN -- must refuse, not connect:
curl --max-time 5 http://<armitage-lan-ip>:8010/                    # refused
```

## Backups

Everything is in the `imagery_data` volume -- database, uploads, session secret.

```bash
docker run --rm -v imagery_data:/data -v "$PWD":/out alpine \
  tar czf /out/imagery-backup-$(date +%F).tar.gz -C /data .
```

Per the standing storage rule, write backups to `/dev/sdc1`, not the root disk.

## Prototyping over HTTPS with Tailscale

Recording needs a secure context, so a plain-http prototype cannot test the
feature that matters most. `tailscale serve` gives a real Let's Encrypt
certificate on the tailnet with no public DNS, no port forwarding and no
exposure beyond your own devices.

One-time, on the host:

```bash
sudo tailscale set --operator=$USER      # so serve/cert do not need root
# then enable "HTTPS Certificates" in the Tailscale admin console, under DNS
```

Then bind the container to localhost only and put serve in front of it:

```bash
docker run -d --name imagery -v imagery_data:/data \
  -p 127.0.0.1:8011:8000 \
  -e IMAGERY_ADMIN=bear -e IMAGERY_SECURE_COOKIE=1 imagery:dev

tailscale serve --bg --https=443 http://127.0.0.1:8011
```

The app is then at `https://<host>.<tailnet>.ts.net/` for every device on the
tailnet, and `IMAGERY_SECURE_COOKIE=1` is correct because the connection really
is secure. The serve configuration persists across reboots.

To take it down again: `tailscale serve --https=443 off`.

**Note that BYOD iPads are not on the tailnet.** This is the right setup for
testing on your own devices; workshops still need the public deployment in
`docker-compose.prod.yml`.
