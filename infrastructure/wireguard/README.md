# WireGuard

Private tunnel between the Network Agent (on the Network VPS) and MikroTik
routers deployed at provider sites. Railway never connects to a router's
public IP directly — all router traffic goes:

```
FastAPI (Railway) --HTTPS--> Network Agent (VPS) --WireGuard--> MikroTik router
```

## Layout

```
infrastructure/wireguard/
  wg0.conf.example          # Server-side interface template for the Network VPS
  router-peer.conf.example  # RouterOS-side WireGuard + RADIUS client setup
```

Peer provisioning automation lives in `infrastructure/scripts/add-router-peer.sh`
(generates a key pair, assigns the next free tunnel IP, appends the `[Peer]`
block to the live `wg0.conf`, and prints the exact RouterOS commands + the
`clients.conf` block for that router).

## Notes

- Each MikroTik router is provisioned as a WireGuard peer with a unique
  key pair and an assigned tunnel IP in the `10.90.0.0/24` range (`.1` is
  the Network VPS itself).
- Real `wg0.conf` files, private keys, and pre-shared keys must never be
  committed — see the root `.gitignore` (`infrastructure/wireguard/*.conf`
  is ignored; only `*.conf.example` is tracked).
- The Network Agent resolves a router's WireGuard tunnel IP itself from its
  own `routers.yaml` registry, keyed by router UUID — it never accepts an
  IP/host from a caller (see `apps/network-agent/app/core/router_registry.py`).
