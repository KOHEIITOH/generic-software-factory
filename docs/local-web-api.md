# Local Web API (experimental)

The initial API is intentionally **read-only**. It provides the foundation for
a React dashboard without exposing code execution or arbitrary filesystem access.

## Start on your Mac

```bash
uv sync --extra web
uv run --extra web uvicorn sf_factory.web_api:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/docs to inspect the API.

- `GET /api/health`: local API health
- `GET /api/runtimes`: registered runtime names (not availability or authentication)

Do not bind to `0.0.0.0` or expose this experimental service on the public internet.
The API has no authentication yet. No task execution endpoints are implemented.

## Next PRs

1. React/TypeScript dashboard consuming the read-only API.
2. Carefully scoped task management API with validation, user confirmation and
   loopback-only access controls.
3. Isolated Docker execution adapter with resource and filesystem restrictions.

Docker is not required to run the API.
