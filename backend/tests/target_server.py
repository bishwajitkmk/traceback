"""A real HTTP server on 127.0.0.1 that replays are sent to in tests."""

import socket
import threading
import time

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response
from starlette.routing import Route

state = {"fixed": False}


async def echo(request: Request) -> Response:
    body = await request.body()
    return JSONResponse(
        {
            "method": request.method,
            "path": request.url.path,
            "query": dict(request.query_params.multi_items()),
            "headers": {k.lower(): v for k, v in request.headers.items()},
            "body": body.decode() if body else None,
        }
    )


async def checkout(request: Request) -> Response:
    payload = await request.json()
    if int(payload.get("quantity", 1)) <= 0:
        if state["fixed"]:
            return JSONResponse({"error": {"code": "invalid_quantity"}}, status_code=422)
        return JSONResponse({"detail": "Internal Server Error"}, status_code=500)
    return JSONResponse({"order_id": "ord_1", "total": 19.99}, status_code=201)


async def redirect_out(_: Request) -> Response:
    return RedirectResponse("http://169.254.169.254/latest/meta-data/", status_code=302)


async def redirect_in(_: Request) -> Response:
    return RedirectResponse("/echo?from=redirect", status_code=302)


async def big(_: Request) -> Response:
    return PlainTextResponse("x" * 400_000)


async def slow(_: Request) -> Response:
    time.sleep(2.5)  # deliberately blocks: this server only exists for tests
    return PlainTextResponse("late")


app = Starlette(
    routes=[
        Route("/echo", echo, methods=["GET", "POST", "PUT", "PATCH", "DELETE"]),
        Route("/checkout", checkout, methods=["POST"]),
        Route("/redirect-out", redirect_out),
        Route("/redirect-in", redirect_in),
        Route("/big", big),
        Route("/slow", slow),
    ]
)


class TargetServer:
    def __init__(self) -> None:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.server = uvicorn.Server(
            uvicorn.Config(
                app, host="127.0.0.1", port=self.port, log_level="warning", lifespan="off"
            )
        )
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("target server did not start")
            time.sleep(0.05)

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5)
