"""Exercise backend HTTP routes in an isolated interpreter for cross-service tests."""

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND = Path(__file__).parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from main import app


def main() -> None:
    method, path = sys.argv[1:3]
    body = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
    headers = {
        "X-API-Key": "cross-service-admin-secret",
        "Origin": "http://localhost:5173",
    }
    with TestClient(app) as client:
        response = client.request(method, path, headers=headers, json=body)
    print(
        "HTTP_PROBE_RESULT="
        + json.dumps(
            {
                "status_code": response.status_code,
                "body": response.json(),
                "headers": dict(response.headers),
            }
        )
    )


if __name__ == "__main__":
    main()
