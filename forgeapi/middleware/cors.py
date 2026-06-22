from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware as _CORSMiddleware


def add_cors(
    app: FastAPI,
    origins: list[str] = ["*"],
    allow_credentials: bool = True,
    allow_methods: list[str] = ["*"],
    allow_headers: list[str] = ["*"],
) -> None:
    app.add_middleware(
        _CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=allow_methods,
        allow_headers=allow_headers,
    )
