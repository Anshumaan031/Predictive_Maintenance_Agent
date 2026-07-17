# Docker Setup

## Option 1 — Docker Compose (recommended)

Starts Redis + API together with networking pre-configured.

```bash
# Build and start all services
docker compose up --build

# Run in detached (background) mode
docker compose up --build -d

# Stop everything
docker compose down
```

## Option 2 — Manual Build + Run

Requires a running Redis instance separately.

```bash
# Build the image
docker build -t machine-iris-agent .

# Run the container
docker run --rm -p 8000:8000 --env-file .env -e REDIS_URL=redis://host.docker.internal:6379 machine-iris-agent
```

## Useful Commands

```bash
# View logs (detached mode)
docker compose logs -f api

# Rebuild without cache
docker compose build --no-cache api
```

## Endpoints

| Service       | URL                     |
|---------------|-------------------------|
| API           | http://localhost:8000   |
| RedisInsight  | http://localhost:8001   |
