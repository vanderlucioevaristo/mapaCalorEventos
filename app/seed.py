
import pandas as pd
from datetime import datetime
from sqlalchemy.orm import Session
from .database import SessionLocal, Base, engine
from .models import Evento, Local

Base.metadata.create_all(bind=engine)

def parse_date(date_str):
    date_str = str(date_str).strip()
    # Formato "17 a 18/06" ou "12 a 13/08" — pega o último número antes de /MM e assume ano corrente/próximo
    import re
    m = re.match(r"(\d+)\s+a\s+(\d+)/(\d+)", date_str)
    if m:
        dia_inicio, dia_fim, mes = m.group(1), m.group(2), m.group(3)
        ano = datetime.now().year
        try:
            return datetime.strptime(f"{dia_inicio}/{mes}/{ano}", "%d/%m/%Y")
        except ValueError:
            return datetime.strptime(f"{dia_fim}/{mes}/{ano}", "%d/%m/%Y")
    # Formato "16 a 19/09" já coberto acima; tenta padrão normal
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    # Formato "28/06" sem ano; assume o ano corrente.
    try:
        dia_str, mes_str = date_str.split("/")
        dia = int(dia_str)
        mes = int(mes_str)
        return datetime(datetime.now().year, mes, dia)
    except (ValueError, TypeError):
        pass

    raise ValueError(f"Formato de data não reconhecido: {date_str!r}")


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
                    longitude=row["LONGITUDE"],
                    acessibilidade=True,
                    proximo_metro=True,
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