/** Proxy /api/* to the FastAPI service so the browser never needs CORS. */
const API = process.env.VERITYFORGE_API_URL || "http://localhost:8000";
export default {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
};
