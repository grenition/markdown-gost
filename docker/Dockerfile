# markdown-gost — single multi-stage image.
#
# Build from the repository root (the context needs docker/ + src/ + tests/):
#   docker build -f docker/Dockerfile -t markdown-gost:local .
#
# Stages:
#   base    — python 3.13 + LibreOffice Writer + fonts + pandoc + unoserver
#   deps    — base + production dependencies from the lock file
#   test    — deps + dev dependencies + playwright + tests
#   runtime — deps + installed markdown_gost package + CLI entrypoint
#             (default target: plain `docker build` yields the CLI image)
#
# The image is dual-purpose: OSS users get a fully-working converter out of
# the box (PDF included), and downstream conversion services use it as a
# base image so the engine, fonts and LibreOffice stay in rendering parity
# with CI.
ARG PYTHON_BASE=python:3.13.15-slim-bookworm@sha256:ed86c82274b3c69b52fb5820f358f0bd7df0b603332063cb5c6e32bd220c3e6e

# ============================================================================
# base — system layer
# ============================================================================
FROM ${PYTHON_BASE} AS base

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    UNOSERVER_HOST=127.0.0.1 \
    UNOSERVER_PORT=2003 \
    UNOSERVER_UNO_PORT=2002

# ForceIPv4 + a small retry loop: BuildKit networking occasionally drops
# connections to deb.debian.org mid-fetch and apt's internal retries do
# not always recover.
ARG APT_OPTS="-o Acquire::ForceIPv4=true -o Acquire::Retries=10 -o Acquire::http::Pipeline-Depth=0 -o Acquire::http::No-Cache=true -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30"

RUN set -eux; \
    success=0; \
    for i in 1 2 3; do \
        apt-get $APT_OPTS update && \
        apt-get $APT_OPTS install -y --no-install-recommends \
            libreoffice-core \
            libreoffice-writer \
            libreoffice-math \
            python3-uno \
            python3-pip \
            fonts-liberation \
            fonts-liberation2 \
            fonts-dejavu \
            fonts-dejavu-core \
            fonts-cantarell \
            fonts-noto-core \
            poppler-utils \
            curl \
            ca-certificates \
            tini \
            netcat-openbsd \
        && { success=1; break; } \
        || { echo "apt attempt $i failed, retrying..."; \
             apt-get $APT_OPTS -f install -y || true; \
             sleep $((i * 5)); }; \
    done; \
    [ "$success" = "1" ] || { echo "apt install failed after 3 attempts"; exit 1; }; \
    /usr/lib/libreoffice/program/soffice.bin --version > /dev/null; \
    rm -rf /var/lib/apt/lists/*

# pandoc — deterministic upstream .deb with a pinned checksum per arch.
# Debian bookworm ships 2.17.x in apt; the import pipeline needs >= 2.19.
ARG PANDOC_VERSION=3.1.13
ARG PANDOC_SHA256_AMD64=b51029afd2e302679aabb9464cd96bda378145d48bb853bd32d93c57b93a293d
ARG PANDOC_SHA256_ARM64=960c88d7286e8a4b4c438f6fac6b6d7ea8f1db7b255ba1f99a30ff8cd466dd40
RUN set -eux; \
    deb_arch="$(dpkg --print-architecture)"; \
    case "$deb_arch" in \
        amd64) pandoc_sha256="${PANDOC_SHA256_AMD64}" ;; \
        arm64) pandoc_sha256="${PANDOC_SHA256_ARM64}" ;; \
        *) echo "unsupported arch for pandoc .deb: $deb_arch"; exit 1 ;; \
    esac; \
    curl -fsSL --retry 5 --retry-delay 3 -o /tmp/pandoc.deb \
        "https://github.com/jgm/pandoc/releases/download/${PANDOC_VERSION}/pandoc-${PANDOC_VERSION}-1-${deb_arch}.deb"; \
    echo "${pandoc_sha256}  /tmp/pandoc.deb" | sha256sum -c -; \
    dpkg -i /tmp/pandoc.deb; \
    rm /tmp/pandoc.deb; \
    pandoc --version | head -1 | grep -q 'pandoc 3\.' || { echo "pandoc version check failed"; exit 1; }

# unoserver must run on the system Python that has the uno bindings
# (python3.11 from python3-uno). The app runs on python3.13 and talks to
# unoserver over XML-RPC at 127.0.0.1:2003.
RUN /usr/bin/python3 -m pip install --no-cache-dir --break-system-packages \
        "unoserver==3.2"

RUN pip install --no-cache-dir "poetry>=2.0,<3"

WORKDIR /app

# ============================================================================
# deps — production python deps from the lock file
# ============================================================================
FROM base AS deps

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --without dev

# ============================================================================
# test — dev deps + playwright + tests (CI / make test-in-docker)
# ============================================================================
FROM deps AS test

RUN poetry install --no-root
RUN playwright install --with-deps chromium

COPY src ./src
COPY README.md ./
RUN poetry install --only-root

COPY tests ./tests
COPY docs ./docs
COPY pytest.ini mypy.ini ruff.toml ./

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh \
    && mkdir -p /tmp/lo-profile && chmod 1777 /tmp/lo-profile

ENV APP_MODE=test \
    LO_USER_PROFILE=/tmp/lo-profile \
    PYTHONPATH=/app/src

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
CMD ["pytest", "-v"]

# ============================================================================
# runtime — installed package + CLI entrypoint (default target)
# ============================================================================
FROM deps AS runtime

COPY src ./src
COPY README.md ./
RUN poetry install --only-root

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh \
    && mkdir -p /tmp/lo-profile && chmod 1777 /tmp/lo-profile

RUN groupadd --gid 10001 markdown-gost \
 && useradd --uid 10001 --gid 10001 --no-create-home \
      --home-dir /tmp/markdown-gost-home --shell /usr/sbin/nologin markdown-gost
ENV HOME=/tmp/markdown-gost-home \
    XDG_CACHE_HOME=/tmp/markdown-gost-home/.cache \
    XDG_CONFIG_HOME=/tmp/markdown-gost-home/.config \
    LO_USER_PROFILE=/tmp/lo-profile \
    APP_MODE=cli \
    PYTHONPATH=/app/src

USER 10001:10001

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh", "markdown-gost"]
CMD ["--help"]
