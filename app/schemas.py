from pydantic import BaseModel
from datetime import date

class Evento(BaseModel):
    nome: str
    descricao: str
    data_inicio: date
    data_fim: date
    publico_estimado: int
    porte: str

    class Config:
        from_attributes = True