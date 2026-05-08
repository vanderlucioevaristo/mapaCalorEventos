from datetime import date
from pydantic import BaseModel


class EventoResponse(BaseModel):
    id: int
    nome: str | None = None
    descricao: str | None = None
    data_inicio: date | None = None
    data_fim: date | None = None
    publico_estimado: int | None = None
    porte: str | None = None
    contato_telefone: str | None = None
    site_url: str | None = None
    tipo_evento: str
    local_id: int | None = None

    class Config:
        from_attributes = True


class VersionResponse(BaseModel):
    app: str
    version: str


class CalendarioEventoResponse(BaseModel):
    id: int
    nome: str | None = None
    descricao: str | None = None
    data_inicio: date | None = None
    data_fim: date | None = None
    publico_estimado: int | None = None
    porte: str | None = None
    contato_telefone: str | None = None
    site_url: str | None = None
    tipo_evento: str
    local_id: int | None = None
    local_nome: str | None = None
    regiao: str | None = None


class CalendarioResponse(BaseModel):
    estado_id: int | None = None
    municipio_id: int
    localidade: str
    ano: int
    tipo_evento: str
    total_eventos: int
    total_locais: int
    eventos: list[CalendarioEventoResponse]