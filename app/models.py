from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base

class Local(Base):
    __tablename__ = "locais"

    id = Column(Integer, primary_key=True)
    nome = Column(String)
    endereco = Column(String)
    regiao = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)

    eventos = relationship("Evento", back_populates="local")


class Evento(Base):
    __tablename__ = "eventos"

    id = Column(Integer, primary_key=True)
    nome = Column(String)
    descricao = Column(String)
    data_inicio = Column(Date)
    data_fim = Column(Date)
    publico_estimado = Column(Integer)
    porte = Column(String)
    local_id = Column(Integer, ForeignKey("locais.id"))

    local = relationship("Local", back_populates="eventos")