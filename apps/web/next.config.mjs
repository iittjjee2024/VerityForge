/** /api/* is proxied to the FastAPI service at RUNTIME by app/api/[...path]/route.ts (reads VERITYFORGE_API_URL
 * per request). A build-time rewrite was used before, but it froze the API address into the build. */
export default {};
