/**
 * Runtime proxy: /api/* -> the FastAPI service.
 *
 * Replaces the next.config rewrite. Next.js resolves rewrites at BUILD time, so the API address could not be
 * changed when starting the server (the e2e suite could not run its own API on another port). This handler reads
 * VERITYFORGE_API_URL on every request. The browser still talks only to this origin, so no CORS is needed.
 */
import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const FORWARD_HEADERS = ["content-type", "authorization", "accept"];

async function proxy(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const api = (process.env.VERITYFORGE_API_URL || "http://localhost:8000").replace(/\/$/, "");
  const { path } = await ctx.params;
  const url = `${api}/api/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;
  const headers = new Headers();
  for (const h of FORWARD_HEADERS) {
    const v = req.headers.get(h);
    if (v) headers.set(h, v);
  }
  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  try {
    const upstream = await fetch(url, {
      method: req.method,
      headers,
      body: hasBody ? await req.arrayBuffer() : undefined,
      cache: "no-store",
    });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return Response.json({ detail: `API unreachable at ${api}` }, { status: 502 });
  }
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as PATCH, proxy as DELETE };
