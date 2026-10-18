/* Foreli runtime config (public — never put secrets here).
 *
 * Local / self-hosted (backend serves the frontend): leave empty for same-origin.
 * Production (frontend on Vercel, backend hosted elsewhere): set the backend
 * origin, e.g.
 *     window.FORELI_API_BASE = "https://your-foreli-api.example.com";
 */
window.FORELI_API_BASE = window.FORELI_API_BASE || "";
