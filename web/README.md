# WalkMLB Web (React + Vite)

# Dev: `npm install && npm run dev`
# Build: `npm run build` (outputs to `web/dist`)
# The API is served by FastAPI at `/api`. This SPA uses relative base and should work under subpaths.
# When `web/dist` exists, FastAPI serves it at `/`; otherwise it serves the legacy `static/` pages.

# Notes:
# - Footer menu is kept minimal (TOP / カレンダー). Settings page stores overrides in localStorage.
# - Top page uses `/api/steps/goal` and `/api/calendar/teams`.
