# vuln-scan-depsafe — depsafe (Python typosquatting / slopsquatting checker)
#
# Upstream: https://github.com/kriskimmerle/depsafe (MIT, v0.1.0,
# commit 067b09d4424549cb14fe2e998998649f29d4ca4c — see depsafe-VERSION).
# Single zero-dependency Python file, vendored next to this Dockerfile so the
# build is reproducible and offline (only the base image is pulled).
#
# Build:  docker build -t vuln-scan-depsafe:local -f depsafe.Dockerfile .
# Run:    docker run --rm -v <repo>:/src:ro vuln-scan-depsafe:local --json --no-color /src
#
# Privacy: offline by default (built-in 500+ popular-PyPI corpus, no network).
# `--online` (opt-in) queries the PyPI JSON API for package names only.

FROM python:3.12-slim

COPY depsafe.py /usr/local/bin/depsafe
RUN chmod +x /usr/local/bin/depsafe

ENTRYPOINT ["depsafe"]
