"""Configuração compartilhada pelos comandos, relativa ao arquivo YAML."""

from pathlib import Path
from urllib.parse import urlsplit
import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
import yaml


class ScanError(Exception):
    """Diagnóstico seguro para apresentação ao usuário."""


class Repository(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    path: Path


class Destination(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str
    repository_id: str

    @field_validator("url")
    @classmethod
    def safe_url(cls, value: str) -> str:
        try:
            url = urlsplit(value)
            _ = url.port  # urlsplit valida a porta somente ao acessar esta propriedade.
        except ValueError:
            raise ValueError("Destino HTTP inválido") from None
        if (url.scheme not in {"http", "https"} or not url.hostname
                or url.username is not None or url.password is not None
                or url.query or url.fragment or "?" in value or "#" in value
                or re.search(r"[\s\\]", value)):
            raise ValueError("Use destino HTTP sem credenciais, query ou fragmento")
        return value.rstrip("/")


class Configuration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    repositories: list[Repository] = Field(min_length=1)
    destinations: list[Destination] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    output: Path = Path(".codedoc/inventory.json")

    @model_validator(mode="after")
    def references(self) -> "Configuration":
        ids = [repository.id for repository in self.repositories]
        if len(ids) != len(set(ids)):
            raise ValueError("IDs duplicados")
        if any(destination.repository_id not in ids for destination in self.destinations):
            raise ValueError("Destino referencia repositório desconhecido")
        return self


def load_config(path: Path) -> Configuration:
    try:
        config = Configuration.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, yaml.YAMLError, ValidationError):
        # Erros de parsers e Pydantic podem incluir o valor de entrada sensível.
        raise ScanError("Configuração inválida. Confira o YAML, IDs, caminhos e destinos sem credenciais.") from None
    try:
        base = path.resolve().parent
        for repository in config.repositories:
            repository.path = (base / repository.path).resolve()
        config.output = (base / config.output).resolve()
    except (OSError, ValueError):
        raise ScanError("Caminho inválido na configuração. Confira os repositórios e a saída.") from None
    if config.output == path.resolve():
        raise ScanError("A saída não pode substituir o arquivo de configuração.")
    roots = [repository.path for repository in config.repositories]
    if len(set(roots)) != len(roots):
        raise ScanError("Cada repositório deve ter um caminho distinto.")
    return config
