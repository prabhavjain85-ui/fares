/**
 * Backend API base URL for the FAERS frontend.
 *
 * - Empty string (default): same-origin — use when uvicorn serves UI + API together
 *   (local: http://127.0.0.1:8000).
 * - For Vercel static deploy: set to your Python backend URL, e.g.
 *   https://your-service.up.railway.app
 *   (no trailing slash).
 */
window.FARES_API_BASE_URL = '';
