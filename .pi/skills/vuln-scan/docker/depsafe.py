#!/usr/bin/env python3
"""depsafe - Dependency Typosquatting & Slopsquatting Checker.

Zero-dependency Python CLI that scans requirements.txt, pyproject.toml,
and Pipfile for package names that look suspiciously similar to popular
packages. Catches typosquatting, AI hallucination squatting (slopsquatting),
and other supply chain naming attacks.

Usage:
    depsafe                             # Scan current directory
    depsafe requirements.txt            # Scan specific file
    depsafe --check                     # CI mode (exit 1 if suspicious)
    depsafe --json                      # JSON output
    depsafe --online                    # Query PyPI for package metadata
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.request import urlopen
from urllib.error import URLError, HTTPError


__version__ = "0.1.0"


# ── Popular PyPI packages ───────────────────────────────────────────────────
# Top ~500 most downloaded packages on PyPI (normalized names).
# Source: Hugo van Kemenade's hugovk/top-pypi-packages dataset.
# Names normalized: lowercased, hyphens → underscores.

POPULAR_PACKAGES: Set[str] = {
    # Core / utilities
    "pip", "setuptools", "wheel", "packaging", "six", "attrs", "certifi",
    "charset_normalizer", "idna", "urllib3", "requests", "typing_extensions",
    "python_dateutil", "pyasn1", "rsa", "pyyaml", "numpy", "pandas",
    "protobuf", "grpcio", "grpcio_status", "grpcio_tools",
    "importlib_metadata", "zipp", "platformdirs", "filelock", "tomli",
    "exceptiongroup", "iniconfig", "pluggy", "pytest", "coverage",
    "colorama", "tqdm", "click", "rich", "pygments", "markupsafe",
    "jinja2", "pydantic", "pydantic_core", "annotated_types",
    
    # AWS
    "boto3", "botocore", "s3transfer", "awscli", "aws_sam_cli",
    "aws_cdk_lib", "aws_cdk_core", "aws_xray_sdk",
    "amazon_ion", "awslambdaric",
    
    # Cloud / API
    "google_api_core", "google_auth", "google_cloud_core",
    "google_cloud_storage", "google_cloud_bigquery",
    "google_cloud_pubsub", "google_cloud_logging",
    "google_cloud_firestore", "google_cloud_secret_manager",
    "google_resumable_media", "google_api_python_client",
    "google_auth_httplib2", "googleapis_common_protos",
    "azure_core", "azure_identity", "azure_storage_blob",
    "azure_mgmt_core", "azure_mgmt_resource",
    "azure_keyvault_secrets", "azure_cosmos",
    
    # Web frameworks
    "flask", "django", "fastapi", "starlette", "uvicorn", "gunicorn",
    "werkzeug", "httpx", "aiohttp", "tornado", "bottle", "falcon",
    "sanic", "quart", "litestar",
    
    # HTTP / networking
    "httpcore", "h11", "h2", "httptools", "websockets", "websocket_client",
    "paramiko", "fabric", "invoke",
    
    # Database
    "sqlalchemy", "psycopg2", "psycopg2_binary", "pymysql", "pymongo",
    "redis", "celery", "kombu", "motor", "asyncpg", "aiopg",
    "alembic", "mako", "sqlparse", "peewee", "tortoise_orm",
    
    # Data science / ML
    "scipy", "scikit_learn", "sklearn", "matplotlib", "seaborn",
    "pillow", "opencv_python", "opencv_python_headless",
    "tensorflow", "torch", "torchvision", "torchaudio",
    "transformers", "tokenizers", "safetensors", "accelerate",
    "datasets", "huggingface_hub", "keras", "xgboost", "lightgbm",
    "catboost", "statsmodels", "networkx", "sympy",
    "polars", "pyarrow", "dask", "vaex",
    
    # LLM / AI
    "openai", "anthropic", "langchain", "langchain_core",
    "langchain_community", "langchain_openai", "langchain_anthropic",
    "langsmith", "llama_index", "chromadb", "pinecone_client",
    "tiktoken", "sentence_transformers", "ollama", "litellm",
    "instructor", "outlines", "vllm", "guidance",
    
    # DevOps / CLI
    "docker", "kubernetes", "ansible", "ansible_core",
    "terraform_cdk", "pulumi", "fabric2",
    
    # Crypto / security
    "cryptography", "pyjwt", "python_jose", "oauthlib",
    "requests_oauthlib", "msal", "pynacl", "bcrypt",
    "paramiko", "sshpubkeys", "certbot",
    
    # Serialization / parsing
    "orjson", "ujson", "simplejson", "msgpack", "cbor2",
    "toml", "tomli_w", "ruamel_yaml", "lxml", "beautifulsoup4",
    "html5lib", "cssselect", "xmltodict", "defusedxml",
    
    # Testing
    "pytest", "pytest_cov", "pytest_mock", "pytest_asyncio",
    "pytest_xdist", "hypothesis", "factory_boy", "faker",
    "responses", "vcrpy", "respx", "trustme", "mypy",
    "pyright", "ruff", "black", "isort", "flake8", "pylint",
    "bandit", "pre_commit",
    
    # Async
    "asyncio", "anyio", "trio", "sniffio", "greenlet",
    "gevent", "eventlet", "twisted",
    
    # Image / media
    "pillow", "imageio", "wand", "cairosvg",
    
    # Config / env
    "python_dotenv", "environs", "dynaconf", "pydantic_settings",
    "decouple", "python_decouple", "configparser",
    
    # Logging / monitoring
    "loguru", "structlog", "sentry_sdk", "datadog",
    "prometheus_client", "opentelemetry_api", "opentelemetry_sdk",
    "elastic_apm",
    
    # Task / scheduling
    "celery", "dramatiq", "rq", "apscheduler", "schedule",
    "huey", "arq",
    
    # File handling
    "openpyxl", "xlsxwriter", "xlrd", "python_docx",
    "python_pptx", "reportlab", "fpdf2", "pypdf", "pypdf2",
    "pdfplumber", "camelot_py", "tabula_py",
    
    # CLI / TUI
    "typer", "argparse", "fire", "docopt", "prompt_toolkit",
    "questionary", "textual", "blessed",
    
    # Validation / schema
    "marshmallow", "cerberus", "jsonschema", "voluptuous",
    "wtforms", "email_validator",
    
    # Date / time
    "arrow", "pendulum", "dateparser", "python_dateutil",
    "pytz", "tzdata", "babel",
    
    # Misc popular
    "wrapt", "decorator", "more_itertools", "toolz", "cytoolz",
    "cachetools", "tenacity", "retry", "backoff",
    "chardet", "soupsieve", "webencodings", "sniffio",
    "multidict", "yarl", "frozenlist", "aiosignal",
    "itsdangerous", "blinker", "deprecated", "semantic_version",
    "semver", "distlib", "virtualenv", "pipenv", "poetry",
    "poetry_core", "build", "twine", "flit", "hatchling", "hatch",
    "setuptools_scm", "pbr",
    "psutil", "py_cpuinfo", "distro", "netifaces",
    "regex", "parse", "pyparsing",
    "pathlib2", "pathspec", "watchdog", "watchfiles",
    "appdirs", "humanize", "tabulate",
    "pycparser", "cffi", "cython", "swig",
    "graphviz", "pydot",
    "markdown", "markdown2", "mistune",
    "sphinx", "sphinx_rtd_theme", "mkdocs", "mkdocs_material",
    "nbconvert", "jupyter", "jupyterlab", "notebook", "ipython",
    "ipykernel", "ipywidgets", "nbformat",
}


# ── Normalize package names ─────────────────────────────────────────────────

def normalize(name: str) -> str:
    """Normalize a PyPI package name (PEP 503)."""
    return re.sub(r'[-_.]+', '_', name).lower()


# ── Distance algorithms ─────────────────────────────────────────────────────

def damerau_levenshtein(s1: str, s2: str) -> int:
    """Compute Damerau-Levenshtein distance between two strings."""
    len1, len2 = len(s1), len(s2)
    d: Dict[Tuple[int, int], int] = {}

    for i in range(-1, len1 + 1):
        d[i, -1] = i + 1
    for j in range(-1, len2 + 1):
        d[-1, j] = j + 1

    for i in range(len1):
        for j in range(len2):
            cost = 0 if s1[i] == s2[j] else 1
            d[i, j] = min(
                d[i - 1, j] + 1,       # deletion
                d[i, j - 1] + 1,       # insertion
                d[i - 1, j - 1] + cost  # substitution
            )
            if i > 0 and j > 0 and s1[i] == s2[j - 1] and s1[i - 1] == s2[j]:
                d[i, j] = min(d[i, j], d[i - 2, j - 2] + 1)  # transposition

    return d[len1 - 1, len2 - 1]


# ── Typosquatting detection ─────────────────────────────────────────────────

# Adjacent keys on QWERTY keyboard for fat-finger detection
ADJACENT_KEYS: Dict[str, str] = {
    "q": "wa", "w": "qeas", "e": "wrds", "r": "etdf", "t": "ryfg",
    "y": "tugh", "u": "yijh", "i": "uojk", "o": "iplk", "p": "ol",
    "a": "qwsz", "s": "weadxz", "d": "erfcxs", "f": "rtgvcd",
    "g": "tyhbvf", "h": "yujnbg", "j": "uikmnh", "k": "ioljm",
    "l": "opk", "z": "asx", "x": "zsdc", "c": "xdfv",
    "v": "cfgb", "b": "vghn", "n": "bhjm", "m": "njk",
}

# Common separator confusion patterns
SEPARATOR_PATTERNS = [
    (r'_', '-'),  # underscore vs hyphen
    (r'-', '_'),
    (r'_', ''),   # separator removal
    (r'-', ''),
]


@dataclass
class SuspiciousPackage:
    """A package flagged as potentially suspicious."""
    name: str
    normalized: str
    rule: str
    severity: str  # critical, high, medium, low
    message: str
    similar_to: str = ""
    distance: int = 0
    fix: str = ""


def check_typosquatting(
    pkg_name: str,
    popular: Set[str],
    online_meta: Optional[Dict[str, Any]] = None,
) -> List[SuspiciousPackage]:
    """Check a package name for typosquatting indicators."""
    findings: List[SuspiciousPackage] = []
    norm = normalize(pkg_name)

    # Skip if it's a known popular package
    if norm in popular:
        return findings

    # ── R01: Close Levenshtein distance to popular package ───────────
    for pop in popular:
        # Only compare similar-length names (optimization)
        if abs(len(norm) - len(pop)) > 2:
            continue
        dist = damerau_levenshtein(norm, pop)
        if dist == 1:
            findings.append(SuspiciousPackage(
                name=pkg_name,
                normalized=norm,
                rule="R01",
                severity="high",
                message=f"Package '{pkg_name}' is 1 edit away from popular package '{pop}'. "
                        f"This is a common typosquatting pattern.",
                similar_to=pop,
                distance=dist,
                fix=f"Verify you meant '{pop}' instead of '{pkg_name}'."
            ))
        elif dist == 2 and len(norm) > 4:
            findings.append(SuspiciousPackage(
                name=pkg_name,
                normalized=norm,
                rule="R01",
                severity="medium",
                message=f"Package '{pkg_name}' is 2 edits away from popular package '{pop}'. "
                        f"Could be a typosquatting attempt.",
                similar_to=pop,
                distance=dist,
                fix=f"Verify you meant '{pop}' instead of '{pkg_name}'."
            ))

    # ── R02: Separator confusion ─────────────────────────────────────
    # python-dotenv vs python_dotenv vs pythondotenv
    for sep_from, sep_to in SEPARATOR_PATTERNS:
        variant = re.sub(sep_from, sep_to, norm)
        if variant != norm and variant in popular:
            if not any(f.similar_to == variant and f.rule == "R01" for f in findings):
                findings.append(SuspiciousPackage(
                    name=pkg_name,
                    normalized=norm,
                    rule="R02",
                    severity="medium",
                    message=f"Package '{pkg_name}' differs from '{variant}' only by separator. "
                            f"PyPI normalizes separators — verify the correct package name.",
                    similar_to=variant,
                    fix=f"Check if you meant '{variant}'."
                ))

    # ── R03: Character doubling ──────────────────────────────────────
    # requestss, requets (doubled or missing double)
    for i in range(len(norm)):
        # Try removing a doubled character
        if i > 0 and norm[i] == norm[i - 1]:
            reduced = norm[:i] + norm[i + 1:]
            if reduced in popular:
                if not any(f.similar_to == reduced for f in findings):
                    findings.append(SuspiciousPackage(
                        name=pkg_name,
                        normalized=norm,
                        rule="R03",
                        severity="high",
                        message=f"Package '{pkg_name}' has doubled character '{norm[i]}' — "
                                f"matches popular package '{reduced}' without it.",
                        similar_to=reduced,
                        fix=f"Verify you meant '{reduced}'."
                    ))
        # Try adding a doubled character
        doubled = norm[:i] + norm[i] + norm[i:]
        if doubled in popular:
            if not any(f.similar_to == doubled for f in findings):
                findings.append(SuspiciousPackage(
                    name=pkg_name,
                    normalized=norm,
                    rule="R03",
                    severity="high",
                    message=f"Package '{pkg_name}' is missing doubled character — "
                            f"matches popular package '{doubled}' with it.",
                    similar_to=doubled,
                    fix=f"Verify you meant '{doubled}'."
                ))

    # ── R04: Common prefix/suffix squatting ──────────────────────────
    # python-requests, requests-py, py-requests, requests2, requests3
    squatting_prefixes = ["python_", "py_", "lib_", "easy_", "fast_", "super_", "my_", "the_"]
    squatting_suffixes = ["_py", "_python", "_lib", "_sdk", "_api", "_cli", "_tool",
                          "_client", "_core", "_utils", "_helper", "_wrapper",
                          "2", "3", "4", "x", "_ng", "_next", "_plus", "_pro"]

    for prefix in squatting_prefixes:
        if norm.startswith(prefix):
            base = norm[len(prefix):]
            if base in popular:
                findings.append(SuspiciousPackage(
                    name=pkg_name,
                    normalized=norm,
                    rule="R04",
                    severity="medium",
                    message=f"Package '{pkg_name}' adds prefix '{prefix.rstrip('_')}' to "
                            f"popular package '{base}'. Common squatting pattern.",
                    similar_to=base,
                    fix=f"Verify you meant '{base}' instead of '{pkg_name}'."
                ))

    for suffix in squatting_suffixes:
        if norm.endswith(suffix):
            base = norm[:-len(suffix)]
            if base and base in popular:
                findings.append(SuspiciousPackage(
                    name=pkg_name,
                    normalized=norm,
                    rule="R04",
                    severity="medium",
                    message=f"Package '{pkg_name}' adds suffix '{suffix.lstrip('_')}' to "
                            f"popular package '{base}'. Common squatting pattern.",
                    similar_to=base,
                    fix=f"Verify you meant '{base}' instead of '{pkg_name}'."
                ))

    # ── R05: Homoglyph / lookalike substitution ──────────────────────
    # l→1, o→0, rn→m, etc.
    homoglyphs = {
        "l": ["1", "i"], "1": ["l", "i"], "i": ["l", "1"],
        "o": ["0"], "0": ["o"],
        "rn": ["m"], "m": ["rn"],
        "vv": ["w"], "w": ["vv"],
    }
    for char, replacements in homoglyphs.items():
        if char in norm:
            for repl in replacements:
                variant = norm.replace(char, repl, 1)
                if variant in popular:
                    if not any(f.similar_to == variant for f in findings):
                        findings.append(SuspiciousPackage(
                            name=pkg_name,
                            normalized=norm,
                            rule="R05",
                            severity="high",
                            message=f"Package '{pkg_name}' uses lookalike substitution "
                                    f"('{char}'→'{repl}') matching popular package '{variant}'.",
                            similar_to=variant,
                            fix=f"Verify you meant '{variant}'."
                        ))

    # ── R06: Scope/namespace confusion ───────────────────────────────
    # e.g., "google-cloud" when you meant "google-cloud-storage"
    for pop in popular:
        if pop.startswith(norm + "_") and len(pop) - len(norm) < 15:
            findings.append(SuspiciousPackage(
                name=pkg_name,
                normalized=norm,
                rule="R06",
                severity="low",
                message=f"Package '{pkg_name}' is a prefix of popular package '{pop}'. "
                        f"This could be namespace confusion.",
                similar_to=pop,
                fix=f"Did you mean the more specific package '{pop}'?"
            ))

    # ── R07: Online metadata checks (if enabled) ────────────────────
    if online_meta is not None:
        # Check package age
        age_days = online_meta.get("age_days")
        if age_days is not None and age_days < 30:
            findings.append(SuspiciousPackage(
                name=pkg_name,
                normalized=norm,
                rule="R07",
                severity="medium",
                message=f"Package '{pkg_name}' was created only {age_days} days ago on PyPI. "
                        f"Very new packages deserve extra scrutiny.",
                fix=f"Review the package source code and maintainer before trusting it."
            ))

        # Check download count
        # Note: we don't have download data from the simple JSON API,
        # but we can check if the package exists
        if online_meta.get("not_found"):
            findings.append(SuspiciousPackage(
                name=pkg_name,
                normalized=norm,
                rule="R07",
                severity="high",
                message=f"Package '{pkg_name}' was NOT FOUND on PyPI. "
                        f"This dependency cannot be installed from PyPI.",
                fix=f"Verify the package name and source. Remove if not needed."
            ))

        # Check for single-version packages
        versions = online_meta.get("versions", 0)
        if versions == 1 and age_days is not None and age_days < 90:
            findings.append(SuspiciousPackage(
                name=pkg_name,
                normalized=norm,
                rule="R07",
                severity="low",
                message=f"Package '{pkg_name}' has only 1 release and is {age_days} days old. "
                        f"Single-release packages may be abandoned or malicious.",
                fix=f"Verify this package is actively maintained."
            ))

    # Deduplicate: keep the highest severity for each similar_to
    seen_similar: Dict[str, SuspiciousPackage] = {}
    deduped: List[SuspiciousPackage] = []
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    for f in findings:
        key = f"{f.rule}:{f.similar_to or f.name}"
        existing = seen_similar.get(key)
        if existing is None or severity_order.get(f.severity, 5) < severity_order.get(existing.severity, 5):
            seen_similar[key] = f
    deduped = list(seen_similar.values())
    return sorted(deduped, key=lambda f: severity_order.get(f.severity, 5))


# ── PyPI API queries ─────────────────────────────────────────────────────────

def query_pypi(pkg_name: str) -> Dict[str, Any]:
    """Query PyPI JSON API for package metadata."""
    meta: Dict[str, Any] = {}
    url = f"https://pypi.org/pypi/{pkg_name}/json"
    try:
        with urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
            info = data.get("info", {})
            releases = data.get("releases", {})

            # Package age (from earliest release)
            import datetime
            earliest = None
            for ver, files in releases.items():
                for f in files:
                    upload_time = f.get("upload_time")
                    if upload_time:
                        try:
                            dt = datetime.datetime.fromisoformat(upload_time.replace("Z", "+00:00"))
                            # Local patch (not upstream): PyPI returns naive
                            # upload_time for old releases; normalize to UTC so
                            # naive/aware datetimes never mix (crashes --online).
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=datetime.timezone.utc)
                            if earliest is None or dt < earliest:
                                earliest = dt
                        except (ValueError, TypeError):
                            pass

            if earliest:
                now = datetime.datetime.now(datetime.timezone.utc)
                meta["age_days"] = (now - earliest).days

            meta["versions"] = len([v for v, files in releases.items() if files])
            meta["name"] = info.get("name", pkg_name)
            meta["summary"] = info.get("summary", "")
            meta["author"] = info.get("author", "")

    except HTTPError as e:
        if e.code == 404:
            meta["not_found"] = True
        # Other errors: just skip
    except (URLError, OSError, json.JSONDecodeError):
        pass  # Network errors: skip

    return meta


# ── Dependency file parsing ──────────────────────────────────────────────────

def parse_requirements(text: str) -> List[str]:
    """Parse requirements.txt format."""
    packages: List[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Handle -r includes, -e editable, etc.
        if line.startswith("-"):
            continue
        # Handle URLs
        if "://" in line:
            continue
        # Strip version specifiers
        name = re.split(r'[><=!~\[;@]', line)[0].strip()
        if name:
            packages.append(name)
    return packages


def parse_pyproject_toml(text: str) -> List[str]:
    """Parse dependencies from pyproject.toml."""
    packages: List[str] = []

    # Try stdlib tomllib (3.11+)
    try:
        import tomllib
        data = tomllib.loads(text)
        # PEP 621 dependencies
        deps = data.get("project", {}).get("dependencies", [])
        for dep in deps:
            name = re.split(r'[><=!~\[;@\s]', dep)[0].strip()
            if name:
                packages.append(name)
        # Optional deps
        opt_deps = data.get("project", {}).get("optional-dependencies", {})
        for group, deps in opt_deps.items():
            for dep in deps:
                name = re.split(r'[><=!~\[;@\s]', dep)[0].strip()
                if name:
                    packages.append(name)
        # Poetry deps
        poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
        for name in poetry_deps:
            if name.lower() != "python":
                packages.append(name)
        poetry_dev = data.get("tool", {}).get("poetry", {}).get("dev-dependencies", {})
        for name in poetry_dev:
            packages.append(name)
        return packages
    except (ImportError, Exception):
        pass

    # Fallback: regex parsing
    in_deps = False
    in_opt_deps = False
    bracket_depth = 0
    for line in text.splitlines():
        stripped = line.strip()

        if stripped == "[project]":
            continue
        if re.match(r'^\[project\.optional-dependencies\.\w+\]', stripped):
            in_opt_deps = True
            in_deps = False
            continue
        if stripped.startswith("["):
            in_deps = False
            in_opt_deps = False
            continue

        if stripped.startswith("dependencies") and "=" in stripped:
            in_deps = True
            # Check for inline array
            after_eq = stripped.split("=", 1)[1].strip()
            if after_eq.startswith("["):
                bracket_depth = 1
            continue

        if in_deps or in_opt_deps:
            if "[" in stripped:
                bracket_depth += 1
            if "]" in stripped:
                bracket_depth -= 1
                if bracket_depth <= 0:
                    in_deps = False
                    in_opt_deps = False
                    continue

            # Extract package name from quoted string
            m = re.match(r'^\s*["\']([^"\']+)["\']', stripped)
            if m:
                dep = m.group(1)
                name = re.split(r'[><=!~\[;@\s]', dep)[0].strip()
                if name:
                    packages.append(name)

    # Also try Poetry format
    in_poetry_deps = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped in ("[tool.poetry.dependencies]", "[tool.poetry.dev-dependencies]",
                        "[tool.poetry.group.dev.dependencies]"):
            in_poetry_deps = True
            continue
        if stripped.startswith("["):
            in_poetry_deps = False
            continue
        if in_poetry_deps:
            m = re.match(r'^(\S+)\s*=', stripped)
            if m:
                name = m.group(1)
                if name.lower() != "python":
                    packages.append(name)

    return packages


def parse_pipfile(text: str) -> List[str]:
    """Parse Pipfile format."""
    packages: List[str] = []
    in_packages = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped in ("[packages]", "[dev-packages]"):
            in_packages = True
            continue
        if stripped.startswith("["):
            in_packages = False
            continue
        if in_packages:
            m = re.match(r'^(\S+)\s*=', stripped)
            if m:
                packages.append(m.group(1))
    return packages


def find_dep_files(path: str) -> List[Tuple[str, str]]:
    """Find dependency files and return (filepath, format) pairs."""
    p = Path(path)
    results: List[Tuple[str, str]] = []

    if p.is_file():
        name = p.name.lower()
        if "requirements" in name and name.endswith(".txt"):
            return [(str(p), "requirements")]
        if name == "pyproject.toml":
            return [(str(p), "pyproject")]
        if name == "pipfile":
            return [(str(p), "pipfile")]
        # Try to auto-detect
        return [(str(p), "requirements")]

    if p.is_dir():
        # requirements*.txt
        for f in sorted(p.glob("requirements*.txt")):
            results.append((str(f), "requirements"))
        for f in sorted(p.glob("**/requirements*.txt")):
            if str(f) not in [r[0] for r in results]:
                results.append((str(f), "requirements"))
        # pyproject.toml
        pyproj = p / "pyproject.toml"
        if pyproj.exists():
            results.append((str(pyproj), "pyproject"))
        # Pipfile
        pipfile = p / "Pipfile"
        if pipfile.exists():
            results.append((str(pipfile), "pipfile"))

    return results


# ── Scoring ──────────────────────────────────────────────────────────────────

SEVERITY_SCORES = {"critical": 20, "high": 10, "medium": 5, "low": 2, "info": 0}
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def compute_grade(findings: List[SuspiciousPackage]) -> Tuple[str, int]:
    """Compute letter grade from findings."""
    penalty = sum(SEVERITY_SCORES.get(f.severity, 0) for f in findings)
    score = max(0, 100 - penalty)
    if score >= 95:
        return "A+", score
    elif score >= 85:
        return "A", score
    elif score >= 75:
        return "B", score
    elif score >= 65:
        return "C", score
    elif score >= 50:
        return "D", score
    return "F", score


RULE_DESCRIPTIONS = {
    "R01": "Name Similarity (Levenshtein)",
    "R02": "Separator Confusion",
    "R03": "Character Doubling",
    "R04": "Prefix/Suffix Squatting",
    "R05": "Homoglyph Substitution",
    "R06": "Namespace Confusion",
    "R07": "PyPI Metadata (Online)",
}


# ── Output ───────────────────────────────────────────────────────────────────

SEVERITY_COLORS = {
    "critical": "\033[91m",
    "high": "\033[93m",
    "medium": "\033[33m",
    "low": "\033[36m",
    "info": "\033[90m",
}
RESET = "\033[0m"
BOLD = "\033[1m"


def format_output(
    all_findings: Dict[str, List[SuspiciousPackage]],
    all_packages: Dict[str, List[str]],
    grade: str,
    score: int,
    verbose: bool = False,
    no_color: bool = False,
) -> str:
    """Format findings for terminal."""
    lines: List[str] = []
    b = BOLD if not no_color else ""
    r = RESET if not no_color else ""

    total = sum(len(f) for f in all_findings.values())
    total_pkgs = sum(len(p) for p in all_packages.values())

    sev_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for findings in all_findings.values():
        for f in findings:
            sev_counts[f.severity] = sev_counts.get(f.severity, 0) + 1

    lines.append(f"\n{b}depsafe{r} — Dependency Typosquatting Checker\n")
    lines.append(f"  Packages scanned: {total_pkgs}")
    lines.append(f"  Files checked:    {len(all_findings)}")
    lines.append(f"  Suspicious:       {total}")

    sev_parts = []
    for sev in ["critical", "high", "medium", "low"]:
        if sev_counts[sev] > 0:
            c = SEVERITY_COLORS[sev] if not no_color else ""
            sev_parts.append(f"{c}{sev_counts[sev]} {sev}{r}")
    if sev_parts:
        lines.append(f"  Severity:         {', '.join(sev_parts)}")

    gc = ""
    if not no_color:
        gc = "\033[92m" if score >= 85 else ("\033[93m" if score >= 65 else "\033[91m")
    lines.append(f"\n  {b}Grade: {gc}{grade} ({score}/100){r}\n")

    if total == 0:
        ok_c = SEVERITY_COLORS.get("info", "") if not no_color else ""
        lines.append(f"  {ok_c}✓ No suspicious packages detected{r}\n")
        return "\n".join(lines)

    for filepath, findings in sorted(all_findings.items()):
        if not findings:
            continue
        fname = os.path.basename(filepath)
        lines.append(f"  {b}── {fname} ──{r}")
        for f in findings:
            sc = SEVERITY_COLORS.get(f.severity, "") if not no_color else ""
            tag = f"[{f.severity.upper()}]"
            rule_desc = RULE_DESCRIPTIONS.get(f.rule, f.rule)
            lines.append(f"    {sc}{tag:12}{r} {b}{f.rule}{r}: {rule_desc}")
            lines.append(f"               {f.message}")
            if verbose and f.fix:
                lines.append(f"               {b}Fix:{r} {f.fix}")
            lines.append("")

    return "\n".join(lines)


def format_json_output(
    all_findings: Dict[str, List[SuspiciousPackage]],
    all_packages: Dict[str, List[str]],
    grade: str,
    score: int,
) -> str:
    """Format as JSON."""
    total = sum(len(f) for f in all_findings.values())
    sev_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    findings_list = []
    for filepath, findings in all_findings.items():
        for f in findings:
            sev_counts[f.severity] = sev_counts.get(f.severity, 0) + 1
            findings_list.append({
                "name": f.name,
                "normalized": f.normalized,
                "rule": f.rule,
                "rule_name": RULE_DESCRIPTIONS.get(f.rule, f.rule),
                "severity": f.severity,
                "message": f.message,
                "similar_to": f.similar_to,
                "distance": f.distance,
                "fix": f.fix,
                "file": os.path.basename(filepath),
            })
    return json.dumps({
        "version": __version__,
        "grade": grade,
        "score": score,
        "total_suspicious": total,
        "packages_scanned": sum(len(p) for p in all_packages.values()),
        "severity_counts": sev_counts,
        "findings": findings_list,
    }, indent=2)


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="depsafe",
        description="Dependency Typosquatting & Slopsquatting Checker. "
                    "Scans dependency files for suspicious package names.",
    )
    parser.add_argument(
        "path", nargs="?", default=".",
        help="Path to scan (directory, requirements.txt, pyproject.toml, or Pipfile)",
    )
    parser.add_argument("--json", dest="json_output", action="store_true",
                        help="Output as JSON")
    parser.add_argument("--check", action="store_true",
                        help="CI mode: exit 1 if suspicious packages found")
    parser.add_argument("--severity", default="low",
                        choices=["critical", "high", "medium", "low", "info"],
                        help="Minimum severity (default: low)")
    parser.add_argument("--ignore", default="",
                        help="Comma-separated rules to ignore (e.g., R06,R07)")
    parser.add_argument("--online", action="store_true",
                        help="Query PyPI for package metadata (age, existence)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show fix suggestions")
    parser.add_argument("--no-color", action="store_true",
                        help="Disable color output")
    parser.add_argument("--allowlist", default="",
                        help="Comma-separated packages to skip")
    parser.add_argument("--list-rules", action="store_true",
                        help="List all rules and exit")
    parser.add_argument("--version", action="version",
                        version=f"depsafe {__version__}")
    args = parser.parse_args()

    if args.list_rules:
        print("\ndepsafe rules:\n")
        for rid, desc in sorted(RULE_DESCRIPTIONS.items()):
            print(f"  {rid}: {desc}")
        print()
        return 0

    dep_files = find_dep_files(args.path)
    if not dep_files:
        msg = f"No dependency files found in '{args.path}'"
        if args.json_output:
            print(json.dumps({"error": msg}))
        else:
            print(msg)
            print("Looking for: requirements*.txt, pyproject.toml, Pipfile")
        return 1

    rules_ignore = {r.strip().upper() for r in args.ignore.split(",") if r.strip()}
    allowlist = {normalize(p.strip()) for p in args.allowlist.split(",") if p.strip()}
    min_sev = SEVERITY_ORDER.get(args.severity, 3)

    all_findings: Dict[str, List[SuspiciousPackage]] = {}
    all_packages: Dict[str, List[str]] = {}

    for filepath, fmt in dep_files:
        try:
            with open(filepath, encoding="utf-8") as f:
                content = f.read()
        except (OSError, IOError) as e:
            continue

        if fmt == "requirements":
            packages = parse_requirements(content)
        elif fmt == "pyproject":
            packages = parse_pyproject_toml(content)
        elif fmt == "pipfile":
            packages = parse_pipfile(content)
        else:
            packages = parse_requirements(content)

        # Deduplicate
        seen: Set[str] = set()
        unique_packages: List[str] = []
        for pkg in packages:
            norm = normalize(pkg)
            if norm not in seen:
                seen.add(norm)
                unique_packages.append(pkg)

        all_packages[filepath] = unique_packages
        file_findings: List[SuspiciousPackage] = []

        for pkg in unique_packages:
            if normalize(pkg) in allowlist:
                continue

            # Online check
            online_meta = None
            if args.online:
                online_meta = query_pypi(pkg)

            findings = check_typosquatting(pkg, POPULAR_PACKAGES, online_meta)

            # Filter by rules and severity
            findings = [
                f for f in findings
                if f.rule not in rules_ignore
                and SEVERITY_ORDER.get(f.severity, 5) <= min_sev
            ]
            file_findings.extend(findings)

        all_findings[filepath] = file_findings

    # Grade
    combined = []
    for ff in all_findings.values():
        combined.extend(ff)
    grade, score = compute_grade(combined)

    # Output
    if args.json_output:
        print(format_json_output(all_findings, all_packages, grade, score))
    else:
        nc = args.no_color or not sys.stdout.isatty()
        print(format_output(all_findings, all_packages, grade, score, args.verbose, nc))

    if args.check and combined:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
