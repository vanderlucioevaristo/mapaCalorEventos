
import pandas as pd
from datetime import datetime
from pathlib import Path
import sys
from sqlalchemy.orm import Session
from .database import SessionLocal, Base, engine
from .models import Evento, Local

Base.metadata.create_all(bind=engine)
BASE_DIR = Path(__file__).resolve().parents[1]
EVENTOS_CSV = BASE_DIR / "data" / "eventos.csv"


def normalizar_tipo_evento_csv(valor) -> str:
    if pd.isna(valor):
        return "Negócios"

    tipo = str(valor).strip()
    if not tipo or tipo.lower() == "nan":
        return "Negócios"

    return tipo

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


def _parse_bool_arg(value: str) -> bool:
    valor = (value or "").strip().lower()
    if valor in {"1", "true", "t", "yes", "y", "sim", "s"}:
        return True
    if valor in {"0", "false", "f", "no", "n", "nao", "não", ""}:
        return False
    raise ValueError(
        "Parâmetro inválido para limpar banco. Use true/false. "
        "Exemplo: python3 -m mapaCalorEventos.app.seed true"
    )


def seed(limpar_antes: bool = False):
    df = pd.read_csv(EVENTOS_CSV, sep=";")

    db: Session = SessionLocal()
    try:
        if limpar_antes:
            db.query(Evento).delete(synchronize_session=False)
            db.query(Local).delete(synchronize_session=False)
            db.flush()

        # Em modo append, reaproveita locais já existentes por nome.
        locais_dict = {}
        if not limpar_antes:
            locais_existentes = db.query(Local.id, Local.nome).all()
            locais_dict = {nome: local_id for local_id, nome in locais_existentes}

        # Criar locais únicos
        for _, row in df.iterrows():
            local_nome = row["LOCAL"]
            tipo_evento_csv = normalizar_tipo_evento_csv(row.get("TIPOEVENTO", ""))
            if local_nome not in locais_dict:
                local = Local(
                    nome=local_nome,
                    endereco=row["ENDERECO"],
                    regiao=row["REGIAO"],
                    latitude=row["LATITUDE"],
                    longitude=row["LONGITUDE"],
                    tipo_evento=tipo_evento_csv,
                    acessibilidade=True,
                    proximo_metro=True,
                    restaurantes=True,
                )
                db.add(local)
                db.flush()  # Para obter o ID
                locais_dict[local_nome] = local.id

        # Criar eventos
        for _, row in df.iterrows():
            local_id = locais_dict[row["LOCAL"]]
            tipo_evento_csv = normalizar_tipo_evento_csv(row.get("TIPOEVENTO", ""))
            evento = Evento(
                nome=row["EVENTO"],
                descricao=row["DESCRICAO"],
                data_inicio=parse_date(row["DATA_INICIO"]),
                data_fim=parse_date(row["DATA_FIM"]),
                publico_estimado=row["PUBLICO_ESTIMADO"],
                porte=row["PORTE_EVENTO"],
                tipo_evento=tipo_evento_csv,
                local_id=local_id
            )
            db.add(evento)

        db.commit()
        modo = "(com limpeza prévia)" if limpar_antes else "(append)"
        print(f"Dados inseridos 🚀 {modo}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    limpar = _parse_bool_arg(sys.argv[1]) if len(sys.argv) > 1 else False
    seed(limpar_antes=limpar)