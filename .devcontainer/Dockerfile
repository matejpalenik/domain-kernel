FROM ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 AS uv

FROM mcr.microsoft.com/devcontainers/python:1-3.13-bookworm@sha256:0aa711e570b306c02946cdda67587ce8c65978dbb65691341cbcfd4854dfcfff
COPY --from=uv /uv /uvx /usr/local/bin/
