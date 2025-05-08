# Mock gRPC Server

This module provides a mock gRPC server for local agent development and testing. It implements the agent registration and status update services, logging all received requests.

## How to Run

From the project root (`community/`), run:

```bash
poetry run python -m mock_server.main --port 50051
```

**Common Import Issues:**

- If you see `ModuleNotFoundError: No module named 'agent'`, it means Python cannot find the `agent` package.
- Make sure you run from the project root (`community/`), not from inside `mock_server/`.
- If you still see this error, set the `PYTHONPATH` to the project root:

  ```bash
  PYTHONPATH=. poetry run python -m mock_server.main --port 50051
  ```

- If you want to run directly from inside `mock_server/`, use:
  ```bash
  poetry run python main.py --port 50051
  ```
  But you may need to adjust the import paths in `main.py` to use relative imports or fix the module path.

## Troubleshooting

- **ModuleNotFoundError: No module named 'agent'**  
  This error occurs if Python cannot resolve the `agent` package.  
  - Always run from the project root (`community/`) when using `-m mock_server.main`.
  - If running from inside `mock_server/`, either:
    - Set `PYTHONPATH` to the project root, or
    - Change import statements in `main.py` to use relative imports (not recommended for production).

- **General Advice:**  
  The recommended way is to always run from the project root and use the module path (`-m mock_server.main`). This ensures all imports resolve consistently with the microservices architecture.

- The default port is `50051`. You can specify a different port with `--port`.
- The agent can be pointed at `localhost:50051` for registration and status updates.
- All incoming requests are logged to the console.

## Purpose

Use this mock server to test agent registration, status updates, and command streaming without requiring a full backend server.

## Notes

- The mock server does not persist any data or forward commands.
- It is intended for local development and integration testing only.
