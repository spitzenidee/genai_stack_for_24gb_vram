# vuln-scan-sloppy-joe — sloppy-joe (multi-ecosystem slopsquatting /
# typosquatting / provenance scanner)
#
# Upstream: https://github.com/brennhill/sloppy-joe (Apache-2.0, v1.1.0,
# commit 3d9d413605e384c98c243147441cdf25a6e2ba77).
# Prebuilt static musl binary from GitHub Releases — no build step, no
# runtime deps (single static binary -> FROM scratch).
#
# The release tarball extracts to sloppy-joe-<target>/sloppy-joe. The
# sha256 pins below are the release-asset digests for v1.1.0 (verified
# against the GitHub API + the published .sha256 files). To bump the
# version: update VERSION + both SHA256 args, rebuild, note in the board
# card Log.
#
# Build:  docker build -t vuln-scan-sloppy-joe:local -f sloppy-joe.Dockerfile .
# Run:    docker run --rm -v <repo>:/src:ro -v <cache>:/cache \
#             -v <skill>/docker:/config:ro \
#             vuln-scan-sloppy-joe:local check --json --dir /src \
#             --config /config/sloppy-joe-default-config.json --cache-dir /cache
#
# Privacy: `check` (default) is the fast offline guardrail (manifest
# parsing, lockfile/sync, provenance, canonical policy — no network).
# `--full`/`--ci` (opt-in) adds the online tier: registry existence +
# similarity queries + OSV.dev — package names only, never code.

FROM alpine:3.20 AS fetch
ARG VERSION=1.1.0
ARG TARGETARCH
# Release-asset sha256 pins for v1.1.0 (sloppy-joe-<arch>-unknown-linux-musl.tar.xz).
ARG X86_64_SHA256=f1bae62dd183ff4da42f7f59250e7876ad96d7629e29642b43c3b8fecee82a41
ARG AARCH64_SHA256=f2f60454f2fb89a180b1dbcdec2521ee8d12f8d9087feafed109bed9ab486879
RUN set -eux; \
    case "$TARGETARCH" in \
      amd64) target=x86_64-unknown-linux-musl;  sha=$X86_64_SHA256 ;; \
      arm64) target=aarch64-unknown-linux-musl; sha=$AARCH64_SHA256 ;; \
      *) echo "unsupported TARGETARCH: $TARGETARCH" >&2; exit 1 ;; \
    esac; \
    apk add --no-cache curl xz; \
    url="https://github.com/brennhill/sloppy-joe/releases/download/v${VERSION}/sloppy-joe-${target}.tar.xz"; \
    curl -fsSL -o /tmp/sj.tar.xz "$url"; \
    echo "${sha}  /tmp/sj.tar.xz" | sha256sum -c -; \
    tar -xJf /tmp/sj.tar.xz -C /tmp; \
    mv "/tmp/sloppy-joe-${target}/sloppy-joe" /tmp/sloppy-joe; \
    cp "/tmp/sloppy-joe-${target}/LICENSE" /tmp/sloppy-joe-LICENSE; \
    rm -rf /tmp/sj.tar.xz "/tmp/sloppy-joe-${target}"

FROM scratch
COPY --from=fetch /tmp/sloppy-joe /usr/local/bin/sloppy-joe
COPY --from=fetch /tmp/sloppy-joe-LICENSE /usr/local/share/sloppy-joe/LICENSE

ENTRYPOINT ["sloppy-joe"]
