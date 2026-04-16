# Cloudflare Worker Proxy

This Worker serves the MNIST Web4 frontend for `icypee.xyz` by fetching `web4_get` from the deployed NEAR contract:

- Contract: `icypee.testnet`
- RPC: `https://rpc.testnet.near.org`

## Install

```bash
cd cloudflare-worker
npm install
```

## Deploy

```bash
npx wrangler deploy
```

If you want to test locally first:

```bash
npx wrangler dev
```

## Notes

- The Worker does not duplicate the frontend. It proxies the HTML returned by `web4_get`.
- The health endpoint is available at `/__health`.
- The route config is set for `icypee.xyz` and `www.icypee.xyz`.
