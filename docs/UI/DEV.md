# Iris UI — Dev

React + Vite frontend for the Iris agent. Connects to the FastAPI backend at `http://localhost:8000` by default (configurable in the sidebar).

## Setup

```bash
cd UI
npm install
```

## Run

```bash
# Start backend first (from project root)
uvicorn src.api.app:app --reload

# Then start the UI dev server
cd UI
npm run dev
```

Opens at `http://localhost:5173`.

## Build

```bash
npm run build      # outputs to UI/dist/
npm run preview    # preview the production build locally
```

## API URL

The backend URL can be changed at runtime via the input at the bottom of the sidebar. It persists in `localStorage` as `iris_api`.
