# Cloudflare Worker Proxy

This Worker serves Web4 frontends by fetching `web4_get` from deployed NEAR contracts.

Current configs:

| Config | Hostname | Contract |
| --- | --- | --- |
| `wrangler.jsonc` | `icypee.xyz`, `www.icypee.xyz` | `icypee.testnet` |
| `wrangler.hotdog.jsonc` | `hotdog.icypee.xyz` | `hotdog-icypee.testnet` |
| `wrangler.flappy.jsonc` | `ironclaw.icypee.xyz` | `flappy.hotdog-icypee.testnet` |

## Install

```bash
cd cloudflare-worker
npm install
```

## Deploy

```bash
npx wrangler deploy
```

To deploy a specific hostname config:

```bash
npx wrangler deploy -c wrangler.flappy.jsonc
```

From the repo root, the helper script accepts the config filename:

```bash
./scripts/deploy-cloudflare-worker.sh wrangler.flappy.jsonc
```

If you want to test locally first:

```bash
npx wrangler dev
```

## Notes

- The Worker does not duplicate the frontend. It proxies the HTML returned by `web4_get`.
- The health endpoint is available at `/__health`.
- Route config is split by hostname so each Worker can point at a different contract.
