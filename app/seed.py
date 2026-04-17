
import pandas as pd
from datetime import datetime
from sqlalchemy.orm import Session
from .database import SessionLocal, Base, engine
from .models import Evento, Local

Base.metadata.create_all(bind=engine)

def parse_date(date_str):
    return datetime.strptime(date_str, "%d/%m/%Y")


def seed():
    df = pd.read_csv("mapaCalorEventos/data/eventos.csv", sep=";")

    db: Session = SessionLocal()
    try:
        # Limpa os dados existentes para evitar duplicidade em reexecucoes do seed.
        db.query(Evento).delete(synchronize_session=False)
        db.query(Local).delete(synchronize_session=False)

        # Criar locais únicos
        locais_dict = {}
        for _, row in df.iterrows():
            local_nome = row["LOCAL"]
            if local_nome not in locais_dict:
                local = Local(
                    nome=local_nome,
                    endereco=row["ENDERECO"],
                    regiao=row["REGIAO"],
                    latitude=row["LATITUDE"],
                    longitude=row["LONGITUDE"]
                )
                db.add(local)
                db.flush()  # Para obter o ID
                locais_dict[local_nome] = local.id

        # Criar eventos
        for _, row in df.iterrows():
            local_id = locais_dict[row["LOCAL"]]
            evento = Evento(
                nome=row["EVENTO"],
                descricao=row["DESCRICAO"],
                data_inicio=parse_date(row["DATA_INICIO"]),
                data_fim=parse_date(row["DATA_FIM"]),
                publico_estimado=row["PUBLICO_ESTIMADO"],
                porte=row["PORTE_EVENTO"],
                local_id=local_id
            )
            db.add(evento)

        db.commit()
        print("Dados inseridos 🚀")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()