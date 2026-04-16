const JSON_HEADERS = { "content-type": "application/json" };

export default {
  async fetch(request, env) {
    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method not allowed", { status: 405 });
    }

    const url = new URL(request.url);
    if (url.pathname === "/__health") {
      return Response.json({
        ok: true,
        contractId: env.CONTRACT_ID,
        rpcUrl: env.NEAR_RPC_URL,
      });
    }

    const query = {};
    for (const key of new Set(url.searchParams.keys())) {
      query[key] = url.searchParams.getAll(key);
    }

    const web4Request = {
      request: {
        accountId: env.CONTRACT_ID,
        path: url.pathname || "/",
        params: {},
        query,
      },
    };

    const rpcResponse = await fetch(env.NEAR_RPC_URL, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: "web4-proxy",
        method: "query",
        params: {
          request_type: "call_function",
          finality: "final",
          account_id: env.CONTRACT_ID,
          method_name: "web4_get",
          args_base64: toBase64(JSON.stringify(web4Request)),
        },
      }),
    });

    if (!rpcResponse.ok) {
      return new Response(`NEAR RPC HTTP error: ${rpcResponse.status}`, {
        status: 502,
      });
    }

    const rpcJson = await rpcResponse.json();
    if (rpcJson.error) {
      return new Response(
        `NEAR RPC returned an error: ${rpcJson.error.message || "unknown error"}`,
        { status: 502 },
      );
    }

    if (rpcJson.result?.error) {
      return new Response(
        `web4_get failed: ${rpcJson.result.error}`,
        { status: 502 },
      );
    }

    const web4Response = JSON.parse(
      new TextDecoder().decode(Uint8Array.from(rpcJson.result.result)),
    );

    if (typeof web4Response.status === "number") {
      return new Response(`Web4 returned status ${web4Response.status}`, {
        status: web4Response.status,
      });
    }

    const headers = new Headers({
      "content-type": web4Response.contentType || "text/plain; charset=UTF-8",
      "cache-control": "public, max-age=60",
      "x-web4-contract": env.CONTRACT_ID,
    });
    const body = Uint8Array.from(atob(web4Response.body), (char) =>
      char.charCodeAt(0),
    );

    if (request.method === "HEAD") {
      return new Response(null, { status: 200, headers });
    }

    return new Response(body, { status: 200, headers });
  },
};

function toBase64(value) {
  return btoa(String.fromCharCode(...new TextEncoder().encode(value)));
}
