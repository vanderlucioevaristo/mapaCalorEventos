from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from .database import Base


class Regional(Base):
    __tablename__ = "regionais"

    id = Column(Integer, primary_key=True)
    nome = Column(String, unique=True, nullable=False)


class Local(Base):
    __tablename__ = "locais"

    id = Column(Integer, primary_key=True)
    nome = Column(String)
    endereco = Column(String)
    regiao = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    contato_telefone = Column(String)
    site_url = Column(String)
    tipo_evento = Column(String, default="Negócios", nullable=False)
    acessibilidade = Column(Boolean, default=False, nullable=False)
    proximo_metro = Column(Boolean, default=False, nullable=False)
    restaurantes = Column(Boolean, default=True, nullable=False)

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
    contato_telefone = Column(String)
    site_url = Column(String)
    tipo_evento = Column(String, default="Negócios", nullable=False)
    local_id = Column(Integer, ForeignKey("locais.id"))

    local = relationship("Local", back_populates="eventos")


class Anunciante(Base):
    __tablename__ = "anunciantes"

    id = Column(Integer, primary_key=True)
    nome = Column(String, nullable=False)
    endereco = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    tipo = Column(String, default="", nullable=False)
    contato_telefone = Column(String)
    site_url = Column(String)
    urlimagem = Column(String)
    datainicio = Column(Date)
    datafim = Column(Date)


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True)
    nome = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    cpf = Column(String, unique=True, nullable=False)
    senha_hash = Column(String, nullable=False)
    role = Column(String, default="admin", nullable=False)
    foto_url = Column(String)
    telefone = Column(String)
    endereco = Column(String)