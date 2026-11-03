"""Inventário de metadados; somente Git e manifests são consultados."""

from fnmatch import fnmatch
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
from xml.etree import ElementTree

from pathspec import GitIgnoreSpec

from codedoc.config import Configuration, Repository, ScanError


SENSITIVE = (
    ".env*", "*.pem", "*.key", "*.pfx", "*.p12", "*.crt", "*.cer",
    "*.jks", "*.keystore", "*.sql", "*.dump", "*.bak", "*.sqlite*", "*.db",
    "*secret*", "*credential*", "*token*", "id_rsa*", "id_ed25519*",
    "appsettings*.json", "nuget.config", ".npmrc", ".pypirc", "web.config",
)
EXCLUDED_DIRECTORIES = {
    ".git", ".aws", ".ssh", ".azure", ".venv", "venv", "node_modules",
    "bin", "obj", "dist", "build", ".next", "coverage", "vendor", ".codedoc",
}
LANGUAGES = {".cs": "csharp", ".ts": "typescript", ".tsx": "typescript",
             ".js": "javascript", ".jsx": "javascript", ".py": "python"}
MAX_MANIFEST_BYTES = 2_000_000


def git(root: Path, *args: str, data: bytes | None = None, allowed=(0,)) -> bytes:
    try:
        result = subprocess.run(
            ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(root), *args], input=data,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except OSError:
        raise ScanError("Git indisponível. Instale o Git e confira o PATH.") from None
    if result.returncode not in allowed:
        raise ScanError("Falha ao consultar Git. Confira o repositório e suas permissões.")
    return result.stdout


def revision(repository: Repository) -> str:
    root = repository.path
    try:
        top = Path(os.fsdecode(git(root, "rev-parse", "--show-toplevel")).strip()).resolve()
        commit = git(root, "rev-parse", "--verify", "HEAD^{commit}").decode("ascii").strip()
    except (ScanError, ValueError, UnicodeError):
        raise ScanError(f"Repositório {repository.id}: informe uma raiz Git com pelo menos um commit.") from None
    if top != root:
        raise ScanError(f"Repositório {repository.id}: o caminho deve ser a raiz Git.")
    if git(root, "status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none"):
        raise ScanError(f"Repositório {repository.id}: há alterações pendentes. Salve-as em commit ou escolha uma cópia limpa; nenhuma alteração foi removida.")
    return commit


def eligible_name(relative: str, exclusions: GitIgnoreSpec) -> bool:
    parts = PurePosixPath(relative).parts
    if not parts or PurePosixPath(relative).is_absolute() or any(part in {"..", "."} for part in parts):
        return False
    if any(part.lower() in EXCLUDED_DIRECTORIES for part in parts):
        return False
    if any(fnmatch(part.lower(), pattern) for part in parts for pattern in SENSITIVE):
        return False
    if exclusions.match_file(relative):
        return False
    return True


def permitted(root: Path, relative: str, exclusions: GitIgnoreSpec) -> bool:
    if not eligible_name(relative, exclusions):
        return False
    candidate = root
    for part in PurePosixPath(relative).parts:
        candidate = candidate / part
        if candidate.is_symlink() or candidate.is_junction():
            return False
    return candidate.is_file() and candidate.resolve().is_relative_to(root)


def read_manifest(path: Path):
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        return None
    return path.read_text(encoding="utf-8-sig")


def project(path: Path, relative: str) -> dict | None:
    if path.name != "package.json" and path.suffix.lower() != ".csproj":
        return None
    try:
        content = read_manifest(path)
        if content is None:
            return {"manifest": relative, "technologies": [], "warning": "manifest_too_large"}
        if path.name == "package.json":
            package = json.loads(content)
            dependencies = set()
            for key in ("dependencies", "devDependencies", "peerDependencies"):
                values = package.get(key, {})
                if not isinstance(values, dict):
                    raise ValueError
                dependencies.update(values)
            technologies = ["nodejs"]
            technologies.extend(name for name in ("next", "react", "typescript", "axios") if name in dependencies)
        else:
            if "<!DOCTYPE" in content.upper() or "<!ENTITY" in content.upper():
                raise ValueError
            ElementTree.fromstring(content)
            technologies = ["dotnet", "csharp"]
        return {"manifest": relative, "technologies": sorted(technologies)}
    except (OSError, UnicodeError, ValueError, AttributeError, ElementTree.ParseError):
        return {"manifest": relative, "technologies": [], "warning": "manifest_unreadable"}


def scan_repository(repository: Repository, exclusions: GitIgnoreSpec, commit: str) -> dict:
    root = repository.path
    names = git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    # --no-index faz .gitignore valer também para arquivos já rastreados.
    ignored = set(git(root, "check-ignore", "--no-index", "--stdin", "-z",
                      data=names, allowed=(0, 1)).split(b"\0")) if names else set()
    files, projects, languages = [], [], set()
    for encoded in sorted(set(names.split(b"\0")) - ignored - {b""}):
        relative = os.fsdecode(encoded)
        if not permitted(root, relative, exclusions):
            continue
        path = root / relative
        files.append(relative)
        if language := LANGUAGES.get(path.suffix.lower()):
            languages.add(language)
        if detected := project(path, relative):
            projects.append(detected)
    return {"id": repository.id, "revision": commit, "files": files,
            "languages": sorted(languages), "projects": projects}


def scan(config: Configuration) -> dict:
    commits = {repository.id: revision(repository) for repository in config.repositories}
    for repository in config.repositories:
        if config.output.is_relative_to(repository.path):
            raise ScanError("A saída deve ficar fora dos repositórios analisados para preservar suas árvores limpas.")
    exclusions = GitIgnoreSpec.from_lines(config.exclude)
    inventory = {
        "schema_version": "1.0",
        "repositories": [scan_repository(repository, exclusions, commits[repository.id])
                         for repository in config.repositories],
        "destinations": [destination.model_dump() for destination in config.destinations],
    }
    for repository in config.repositories:
        if revision(repository) != commits[repository.id]:
            raise ScanError(f"Repositório {repository.id}: revisão mudou durante o inventário. Execute novamente.")
    return inventory


def write_inventory(path: Path, inventory: dict) -> None:
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         delete=False, suffix=".tmp") as stream:
            temporary = Path(stream.name)
            json.dump(inventory, stream, ensure_ascii=True, indent=2)
            stream.write("\n")
        temporary.replace(path)
    except OSError:
        raise ScanError("Não foi possível gravar o inventário. Confira a saída e suas permissões.") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
