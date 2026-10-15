from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Iterable

from .models import CheckResult, CheckStatus, VerificationLog


CHECK_NAMES = {
    "git": "Git repository",
    "lockfile": "Dependency lockfile",
    "runtime": "Runtime pinned",
    "dockerfile": "Dockerfile",
    "test-command": "Test command",
    "readme": "README",
    "env-example": ".env.example",
    "absolute-paths": "Absolute paths",
}

_SECRET_VALUE = re.compile(
    r"(?i)(\b(?:api[_-]?key|access[_-]?key|secret|token|password|passwd|private[_-]?key)\b\s*[=:]\s*)([^\s,;]+)"
)
_SECRET_TOKEN = re.compile(r"(?i)\b(?:sk-[a-z0-9]{12,}|gh[pousr]_[a-z0-9_]{12,}|AKIA[0-9A-Z]{12,})\b")
_ABSOLUTE_PATH = re.compile(
    r"(?<![\w.-])(?:/(?:home|Users|root|private|tmp|var|opt|mnt)/[^\s'\"`]+|[A-Za-z]:\\(?:Users|home)\\[^\s'\"`]+)"
)
_HASH = re.compile(r"^[0-9a-f]{40}$")


def redact(value: str) -> str:
    value = _SECRET_VALUE.sub(r"\1<REDACTED>", value)
    return _SECRET_TOKEN.sub("<REDACTED>", value)


def _result(
    check_id: str,
    status: CheckStatus,
    summary: str,
    evidence: Iterable[str] = (),
    recommendation: str | None = None,
    files: Iterable[str] = (),
) -> CheckResult:
    return CheckResult(
        id=check_id,
        name=CHECK_NAMES[check_id],
        status=status,
        summary=summary,
        evidence=[redact(item) for item in evidence],
        recommendation=recommendation,
        files=list(files),
    )


def _safe_path(root: Path, relative: str) -> Path | None:
    """Resolve a repository-relative path without escaping root via symlinks."""
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        return None
    candidate = (root / relative).resolve(strict=False)
    try:
        if os.path.commonpath((str(root), str(candidate))) != str(root):
            return None
    except ValueError:
        return None
    return candidate


def _read_text(root: Path, relative: str, limit: int = 1_000_000) -> str | None:
    path = _safe_path(root, relative)
    if path is None or not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return None


def _file(root: Path, relative: str) -> bool:
    path = _safe_path(root, relative)
    return path is not None and path.is_file()


def _dir(root: Path, relative: str) -> bool:
    path = _safe_path(root, relative)
    return path is not None and path.is_dir()


def _json(root: Path, relative: str) -> dict:
    text = _read_text(root, relative)
    if text is None:
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _git_dir(root: Path) -> Path | None:
    path = _safe_path(root, ".git")
    if path is None:
        return None
    if path.is_dir():
        return path
    if path.is_file():
        raw = _read_text(root, ".git", 4096)
        if not raw or not raw.startswith("gitdir:"):
            return None
        target = (root / raw.split(":", 1)[1].strip()).resolve(strict=False)
        try:
            if os.path.commonpath((str(root), str(target))) != str(root):
                return None
        except ValueError:
            return None
        return target if target.is_dir() else None
    return None


def _has_commit(git_dir: Path) -> bool:
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return False
    if _HASH.fullmatch(head):
        return True
    if not head.startswith("ref: "):
        return False
    ref = head[5:].strip()
    try:
        value = (git_dir / ref).read_text(encoding="ascii", errors="ignore").strip()
        if _HASH.fullmatch(value):
            return True
        packed = (git_dir / "packed-refs").read_text(encoding="ascii", errors="ignore")
    except OSError:
        return False
    return any(line.split(" ", 1)[-1].strip() == ref for line in packed.splitlines() if not line.startswith("#"))


def _iter_text_files(root: Path) -> Iterable[tuple[str, Path]]:
    ignored = {".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache"}
    for current, directories, filenames in os.walk(root, topdown=True, followlinks=False):
        directories[:] = [name for name in directories if name not in ignored and not (Path(current) / name).is_symlink()]
        for name in filenames:
            path = Path(current) / name
            if path.is_symlink() or path.stat().st_size > 2_000_000:
                continue
            relative = path.relative_to(root).as_posix()
            try:
                with path.open("rb") as handle:
                    sample = handle.read(4096)
                if b"\0" in sample:
                    continue
            except OSError:
                continue
            yield relative, path


class RepositoryAnalyzer:
    def __init__(self, root: str | Path, *, verify_docker: bool = True, verify_tests: bool = True) -> None:
        self.root = Path(root).expanduser().resolve()
        self.verify_docker = verify_docker
        self.verify_tests = verify_tests
        self.logs: list[VerificationLog] = []
        self._docker_image: str | None = None

    def analyze(self) -> tuple[list[CheckResult], list[VerificationLog], dict[str, str]]:
        if not self.root.is_dir():
            raise ValueError("repository path must be an existing directory")
        package = _json(self.root, "package.json")
        pyproject = _read_text(self.root, "pyproject.toml") or ""
        results = [
            self._git(),
            self._lockfile(package, pyproject),
            self._runtime(package, pyproject),
            self._dockerfile(),
            self._test_command(package),
            self._readme(),
            self._env_example(),
            self._absolute_paths(),
        ]
        return results, self.logs, {
            "language": "javascript" if package else ("python" if pyproject or _file(self.root, "requirements.txt") else "unknown"),
            "package_manager": self._package_manager(package, pyproject),
        }

    def _git(self) -> CheckResult:
        git_dir = _git_dir(self.root)
        if git_dir is None:
            return _result("git", CheckStatus.FAIL, "Git metadata is missing or escapes the selected repository.", recommendation="Initialize Git and create at least one commit.")
        if not _has_commit(git_dir):
            return _result("git", CheckStatus.FAIL, "Git metadata exists but no commit could be verified.", [".git metadata found; HEAD has no commit"], "Create at least one Git commit.", [".git"])
        return _result("git", CheckStatus.PASS, "A Git repository with at least one commit was found.", ["HEAD points to a commit object."], files=[".git"])

    def _package_manager(self, package: dict, pyproject: str) -> str:
        declared = package.get("packageManager") if package else None
        if isinstance(declared, str) and declared:
            return declared.split("@", 1)[0]
        if package:
            if _file(self.root, "pnpm-lock.yaml"):
                return "pnpm"
            if _file(self.root, "yarn.lock"):
                return "yarn"
            return "npm"
        if "poetry" in pyproject.lower() or _file(self.root, "poetry.lock"):
            return "poetry"
        if _file(self.root, "uv.lock"):
            return "uv"
        if pyproject or _file(self.root, "requirements.txt"):
            return "pip"
        return "unknown"

    def _lockfile(self, package: dict, pyproject: str) -> CheckResult:
        if not package and not pyproject and not _file(self.root, "requirements.txt"):
            return _result("lockfile", CheckStatus.SKIPPED, "No supported package manifest was detected.", recommendation="Add a supported package manifest and its lockfile.")
        manager = self._package_manager(package, pyproject)
        choices = {"npm": ["package-lock.json", "npm-shrinkwrap.json"], "yarn": ["yarn.lock"], "pnpm": ["pnpm-lock.yaml"], "poetry": ["poetry.lock"], "uv": ["uv.lock"], "pip": ["requirements.txt", "poetry.lock", "uv.lock"]}
        found = next((name for name in choices.get(manager, []) if _file(self.root, name)), None)
        if found:
            return _result("lockfile", CheckStatus.PASS, f"A {manager} dependency lockfile is present.", [f"Found {found} for {manager}."], files=[found])
        return _result("lockfile", CheckStatus.FAIL, f"The detected {manager} project has no supported lockfile.", recommendation=f"Add the appropriate {manager} lockfile.")

    def _runtime(self, package: dict, pyproject: str) -> CheckResult:
        candidates: list[str] = []
        if package:
            for name in (".nvmrc", ".node-version"):
                if _file(self.root, name):
                    candidates.append(name)
            if isinstance(package.get("engines"), dict) and package["engines"].get("node"):
                candidates.append("package.json: engines.node")
        if pyproject or _file(self.root, "requirements.txt"):
            for name in (".python-version", "runtime.txt"):
                if _file(self.root, name):
                    candidates.append(name)
            if re.search(r"requires-python\s*=\s*['\"][^'\"]*[0-9][^'\"]*['\"]", pyproject):
                candidates.append("pyproject.toml: requires-python")
        if _file(self.root, ".tool-versions"):
            candidates.append(".tool-versions")
        docker = _read_text(self.root, "Dockerfile") or ""
        if re.search(r"(?im)^\s*FROM\s+(?:[\w./-]+/)?(?:python|node):[\w.-]+", docker):
            candidates.append("Dockerfile: pinned base image")
        if candidates:
            return _result("runtime", CheckStatus.PASS, "A supported runtime version is explicitly specified.", ["; ".join(candidates)], files=candidates)
        if package or pyproject or _file(self.root, "requirements.txt"):
            return _result("runtime", CheckStatus.FAIL, "A supported project was detected but its runtime is not pinned.", recommendation="Add .python-version, .nvmrc, or an equivalent explicit runtime constraint.")
        return _result("runtime", CheckStatus.UNVERIFIED, "No supported runtime could be identified.", recommendation="Declare the project runtime explicitly.")

    def _dockerfile(self) -> CheckResult:
        if not _file(self.root, "Dockerfile"):
            return _result("dockerfile", CheckStatus.FAIL, "Dockerfile is missing.", recommendation="Add a Dockerfile that builds the project reproducibly.")
        if not self.verify_docker:
            return _result("dockerfile", CheckStatus.SKIPPED, "Docker verification was disabled for this audit.", files=["Dockerfile"])
        docker = shutil.which("docker")
        if not docker:
            self.logs.append(VerificationLog(check_id="dockerfile", command="docker build (network disabled)", status=CheckStatus.UNVERIFIED, container="unavailable"))
            return _result("dockerfile", CheckStatus.UNVERIFIED, "Docker is unavailable, so the Dockerfile could not be built.", ["docker executable not found"], "Run the audit where Docker is available.", ["Dockerfile"])
        tag = "cleanroom-audit-" + hashlib.sha256(str(self.root).encode()).hexdigest()[:16]
        started = time.monotonic()
        output, code = self._run_docker(docker, ["build", "--network=none", "--pull=false", "-t", tag, "."])
        elapsed = int((time.monotonic() - started) * 1000)
        status = CheckStatus.PASS if code == 0 else CheckStatus.FAIL
        self._docker_image = tag if code == 0 else None
        self.logs.append(VerificationLog(check_id="dockerfile", command="docker build --network=none --pull=false", status=status, output=redact(output), exit_code=code, duration_ms=elapsed, container="docker"))
        if status is CheckStatus.PASS:
            return _result("dockerfile", status, "Docker build completed successfully with network access disabled.", [redact(output[-1000:]) or "Build completed."], files=["Dockerfile"])
        return _result("dockerfile", status, "Docker build failed.", [redact(output[-1000:]) or "Docker returned a non-zero exit code."], "Fix the Docker build errors and rerun the audit.", ["Dockerfile"])

    def _run_docker(self, docker: str, args: list[str]) -> tuple[str, int]:
        try:
            result = subprocess.run([docker, *args], cwd=self.root, env={"PATH": os.environ.get("PATH", "")}, capture_output=True, text=True, timeout=120, check=False)
            return (result.stdout + result.stderr)[-20_000:], result.returncode
        except (OSError, subprocess.TimeoutExpired) as exc:
            return str(exc), 124

    def _test_command(self, package: dict) -> CheckResult:
        command: str | None = None
        scripts = package.get("scripts") if package else None
        if isinstance(scripts, dict) and isinstance(scripts.get("test"), str):
            command = "npm test"
        readme = next((name for name in ("README.md", "README.rst", "README") if _file(self.root, name)), None)
        if command is None and readme:
            text = _read_text(self.root, readme) or ""
            match = re.search(r"(?im)(?:^|[`$>\s:])((?:python(?:3)?\s+-m\s+pytest|pytest|npm\s+(?:test|run\s+test)|yarn\s+test|pnpm\s+test|make\s+test|go\s+test\b)[^\n`]*)", text)
            if match:
                command = match.group(1).strip()
        if command is None:
            return _result("test-command", CheckStatus.FAIL, "No documented test command was found.", "README and package scripts contain no supported test command.", "Document a reproducible test command in README or package metadata.")
        if not self.verify_tests:
            return _result("test-command", CheckStatus.SKIPPED, f"Test command found but execution was disabled: {command}", files=[readme] if readme else ["package.json"])
        if not self._docker_image:
            self.logs.append(VerificationLog(check_id="test-command", command=command, status=CheckStatus.UNVERIFIED, container="unavailable"))
            return _result("test-command", CheckStatus.UNVERIFIED, f"Test command was found ({command}) but could not be executed in an isolated Docker image.", ["Docker verification did not produce a runnable image."], "Run the audit with Docker available and a successful image build.", [readme] if readme else ["package.json"])
        docker = shutil.which("docker")
        started = time.monotonic()
        output, code = self._run_docker(docker, ["run", "--rm", "--network=none", "--read-only", "--cap-drop=ALL", "--tmpfs", "/tmp:rw", self._docker_image, "sh", "-lc", command])
        elapsed = int((time.monotonic() - started) * 1000)
        status = CheckStatus.PASS if code == 0 else CheckStatus.FAIL
        self.logs.append(VerificationLog(check_id="test-command", command=command, status=status, output=redact(output), exit_code=code, duration_ms=elapsed, container="docker"))
        return _result("test-command", status, "Documented test command completed successfully." if code == 0 else "Documented test command failed.", [redact(output[-1000:]) or "No command output."], "Fix the failing test command and rerun the audit." if code else None)

    def _readme(self) -> CheckResult:
        name = next((name for name in ("README.md", "README.rst", "README") if _file(self.root, name)), None)
        if not name:
            return _result("readme", CheckStatus.FAIL, "README is missing.", recommendation="Add setup, run, and test instructions to a README.")
        text = (_read_text(self.root, name) or "").lower()
        missing = [word for word in ("setup", "run", "test") if word not in text]
        if missing:
            return _result("readme", CheckStatus.FAIL, "README exists but is missing required instructions.", ["Missing sections or references: " + ", ".join(missing)], "Document setup, run, and test steps.", [name])
        return _result("readme", CheckStatus.PASS, "README contains setup, run, and test guidance.", ["Detected setup, run, and test instructions."], files=[name])

    def _env_example(self) -> CheckResult:
        name = ".env.example"
        if not _file(self.root, name):
            return _result("env-example", CheckStatus.FAIL, ".env.example is missing.", recommendation="Add .env.example with placeholders and no real credentials.")
        text = _read_text(self.root, name) or ""
        real_lines: list[str] = []
        for number, line in enumerate(text.splitlines(), 1):
            match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_-]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD)[A-Za-z0-9_-]*)\s*=\s*(.*?)\s*$", line, re.I)
            if match and match.group(2).strip().strip('"\'') and not re.search(r"(?i)(example|changeme|placeholder|your[_ -]?|<.*?>|xxx|redacted)", match.group(2)):
                real_lines.append(f"{name}:{number}: credential-like value is not a placeholder")
        if real_lines:
            return _result("env-example", CheckStatus.FAIL, ".env.example contains credential-like values that are not placeholders.", real_lines, "Replace example credentials with blank values or clear placeholders.", [name])
        return _result("env-example", CheckStatus.PASS, ".env.example exists and credential-like values are placeholders or blank.", ["No real credential-like values detected."], files=[name])

    def _absolute_paths(self) -> CheckResult:
        findings: list[str] = []
        for relative, path in _iter_text_files(self.root):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if _ABSOLUTE_PATH.search(line):
                    findings.append(f"{relative}:{number}: suspicious machine-specific absolute path detected")
                    if len(findings) >= 20:
                        break
            if len(findings) >= 20:
                break
        # A symlink outside the repository is unsafe even if its target is not text.
        for current, directories, filenames in os.walk(self.root, followlinks=False):
            for name in [*directories, *filenames]:
                candidate = Path(current) / name
                if candidate.is_symlink():
                    resolved = candidate.resolve(strict=False)
                    try:
                        outside = os.path.commonpath((str(self.root), str(resolved))) != str(self.root)
                    except ValueError:
                        outside = True
                    if outside:
                        findings.append(f"{candidate.relative_to(self.root).as_posix()}: symlink points outside selected repository")
            directories[:] = [name for name in directories if not (Path(current) / name).is_symlink()]
        if findings:
            return _result("absolute-paths", CheckStatus.FAIL, "Suspicious machine-specific absolute paths or escaping symlinks were detected.", findings, "Replace machine-specific paths with repository-relative paths and remove escaping symlinks.")
        return _result("absolute-paths", CheckStatus.PASS, "No suspicious machine-specific absolute paths were detected.", ["Scanned repository text files and symlink targets safely."])
