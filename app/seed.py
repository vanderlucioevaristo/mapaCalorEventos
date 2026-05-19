
import pandas as pd
from datetime import datetime
from pathlib import Path
import sys
import hashlib
from sqlalchemy.orm import Session
from .database import SessionLocal, Base, engine
from .models import Evento, Local

Base.metadata.create_all(bind=engine)
BASE_DIR = Path(__file__).resolve().parents[1]
EVENTOS_CSV = BASE_DIR / "data" / "eventos.csv"


def _normalizar_nome_coluna(nome: str) -> str:
    return str(nome or "").replace("\ufeff", "").strip().upper()


def _resolver_colunas(df: pd.DataFrame) -> dict[str, str]:
    return {_normalizar_nome_coluna(col): col for col in df.columns}


def _valor_coluna(row, colunas: dict[str, str], nome: str, default=""):
    col_real = colunas.get(nome)
    if not col_real:
        return default
    return row.get(col_real, default)


def _normalizar_hora_inicio_csv(valor) -> str:
    if pd.isna(valor):
        return "09:00"

    texto = str(valor).strip()
    if not texto or texto.lower() == "nan":
        return "09:00"

    try:
        return datetime.strptime(texto, "%H:%M").strftime("%H:%M")
    except ValueError:
        pass

    if texto.isdigit() and 0 <= int(texto) <= 23:
        return f"{int(texto):02d}:00"

    return "09:00"


def _normalizar_id_evento_csv(valor, row, colunas: dict[str, str]) -> str:
    if not pd.isna(valor):
        texto = str(valor).strip()
        if texto and texto.lower() != "nan":
            return texto

    # Fallback determinístico para linhas sem ID no CSV.
    local_nome = str(_valor_coluna(row, colunas, "LOCAL", "")).strip()
    evento_nome = str(_valor_coluna(row, colunas, "EVENTO", "")).strip()
    data_inicio = str(_valor_coluna(row, colunas, "DATA_INICIO", "")).strip()
    base = f"{local_nome}|{evento_nome}|{data_inicio}"
    return hashlib.md5(base.encode("utf-8")).hexdigest()


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
    colunas = _resolver_colunas(df)
    eventos_ignorados_existentes: list[tuple[str, str]] = []
    eventos_inseridos = 0

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

        eventos_por_id_evento: dict[str, Evento] = {}
        if not limpar_antes:
            eventos_existentes = db.query(Evento).all()
            eventos_por_id_evento = {
                str(evento.id_evento).strip(): evento
                for evento in eventos_existentes
                if evento.id_evento and str(evento.id_evento).strip()
            }

        # Criar locais únicos
        for _, row in df.iterrows():
            local_nome = str(_valor_coluna(row, colunas, "LOCAL", "")).strip()
            if not local_nome:
                continue
            tipo_evento_csv = normalizar_tipo_evento_csv(
                _valor_coluna(row, colunas, "TIPOEVENTO", "")
            )
            if local_nome not in locais_dict:
                local = Local(
                    nome=local_nome,
                    endereco=_valor_coluna(row, colunas, "ENDERECO", ""),
                    regiao=_valor_coluna(row, colunas, "REGIAO", ""),
                    latitude=_valor_coluna(row, colunas, "LATITUDE", None),
                    longitude=_valor_coluna(row, colunas, "LONGITUDE", None),
                    tipo_evento=tipo_evento_csv,
                    acessibilidade=True,
                    proximo_metro=False,
                    restaurantes=True,
                )
                db.add(local)
                db.flush()  # Para obter o ID
                locais_dict[local_nome] = local.id

        # Criar eventos
        for _, row in df.iterrows():
            local_nome = str(_valor_coluna(row, colunas, "LOCAL", "")).strip()
            if not local_nome or local_nome not in locais_dict:
                continue

            local_id = locais_dict[local_nome]
            tipo_evento_csv = normalizar_tipo_evento_csv(
                _valor_coluna(row, colunas, "TIPOEVENTO", "")
            )
            id_evento_csv = _normalizar_id_evento_csv(
                _valor_coluna(row, colunas, "ID", ""),
                row,
                colunas,
            )

            if not limpar_antes and id_evento_csv in eventos_por_id_evento:
                # Em modo append, não regrava eventos já existentes.
                nome_evento_csv = str(_valor_coluna(row, colunas, "EVENTO", "")).strip()
                eventos_ignorados_existentes.append((id_evento_csv, nome_evento_csv))
                continue

            evento = Evento(id_evento=id_evento_csv)
            db.add(evento)
            eventos_por_id_evento[id_evento_csv] = evento
            eventos_inseridos += 1

            evento.nome = _valor_coluna(row, colunas, "EVENTO", "")
            evento.descricao = _valor_coluna(row, colunas, "DESCRICAO", "")
            evento.data_inicio = parse_date(_valor_coluna(row, colunas, "DATA_INICIO", ""))
            evento.hora_inicio = _normalizar_hora_inicio_csv(
                _valor_coluna(row, colunas, "HORAINICIO", "")
            )
            evento.data_fim = parse_date(_valor_coluna(row, colunas, "DATA_FIM", ""))
            evento.publico_estimado = _valor_coluna(row, colunas, "PUBLICO_ESTIMADO", None)
            evento.porte = _valor_coluna(row, colunas, "PORTE_EVENTO", "")
            evento.tipo_evento = tipo_evento_csv
            evento.local_id = local_id

        db.commit()
        modo = "(com limpeza prévia)" if limpar_antes else "(append)"
        print(f"Dados inseridos 🚀 {modo}")
        print(f"Eventos inseridos nesta execução: {eventos_inseridos}")
        if not limpar_antes:
            print(
                "Eventos não incluídos por já existirem na base: "
                f"{len(eventos_ignorados_existentes)}"
            )
            if eventos_ignorados_existentes:
                print("Lista de eventos ignorados (id_evento | nome):")
                for id_evento, nome in eventos_ignorados_existentes:
                    print(f"- {id_evento} | {nome}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    limpar = _parse_bool_arg(sys.argv[1]) if len(sys.argv) > 1 else False
    seed(limpar_antes=limpar)