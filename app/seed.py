import pandas as pd
from datetime import datetime
from sqlalchemy.orm import Session
from .database import SessionLocal
from .models import Evento

def parse_date(date_str):
    return datetime.strptime(date_str, "%d/%m/%Y")


def seed():
    df = pd.read_csv("data/eventos.csv", sep=";")

    db: Session = SessionLocal()

    for _, row in df.iterrows():
        evento = Evento(
            nome=row["EVENTO"],
            descricao=row["DESCRICAO"],
            data_inicio=parse_date(row["DATA_INICIO"]),
            data_fim=parse_date(row["DATA_FIM"]),
            publico_estimado=row["PUBLICO_ESTIMADO"],
            porte=row["PORTE_EVENTO"],
            local_id=1  # simplificado
        )
        db.add(evento)

    db.commit()
    print("Dados inseridos 🚀")


if __name__ == "__main__":
    seed()