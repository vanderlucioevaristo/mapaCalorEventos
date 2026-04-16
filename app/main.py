from fastapi import FastAPI
from sqlalchemy.orm import Session
from .database import SessionLocal, engine, Base
from .models import Evento

Base.metadata.create_all(bind=engine)

app = FastAPI()


@app.get("/")
def home():
    return {"msg": "API Eventos BH 🚀"}


@app.get("/eventos")
def listar_eventos():
    db: Session = SessionLocal()
    eventos = db.query(Evento).all()
    return eventos


@app.get("/eventos/porte/{porte}")
def eventos_por_porte(porte: str):
    db: Session = SessionLocal()
    eventos = db.query(Evento).filter(Evento.porte == porte).all()
    return eventos