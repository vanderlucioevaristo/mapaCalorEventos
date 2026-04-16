from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from .database import SessionLocal, engine, Base
from .models import Evento, Local
import folium
import calendar
from datetime import datetime

# Meses em português
meses_pt = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", 
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

Base.metadata.create_all(bind=engine)

app = FastAPI()

#para executar 
# cd /Users/vanderevaristo/ProjetosVander/mapacaloreventos
# source .venv/bin/activate
# uvicorn mapaCalorEventos.app.main:app --reload


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


@app.get("/mapa", response_class=HTMLResponse)
def mapa_eventos():
    db: Session = SessionLocal()
    eventos = db.query(Evento).join(Local).all()

    # Centro do mapa em Belo Horizonte
    mapa = folium.Map(location=[-19.9191, -43.9386], zoom_start=12)

    # Cores por região
    cores = {
        "Oeste": "blue",
        "Pampulha": "green",
        "Centro": "orange"
    }

    for evento in eventos:
        cor = cores.get(evento.local.regiao, "gray")
        tooltip_text = f"{evento.nome} - {evento.local.nome} - Público estimado: {evento.publico_estimado}"
        popup_text = f"""
        <b>{evento.nome}</b><br>
        Descrição: {evento.descricao}<br>
        Data: {evento.data_inicio} a {evento.data_fim}<br>
        Público: {evento.publico_estimado}<br>
        Porte: {evento.porte}<br>
        Local: {evento.local.nome}
        """
        folium.Marker(
            location=[evento.local.latitude, evento.local.longitude],
            popup=popup_text,
            tooltip=tooltip_text,
            icon=folium.Icon(color=cor)
        ).add_to(mapa)

    # Adicionar legenda
    legenda_html = '''
    <div style="position: fixed; 
                bottom: 50px; left: 50px; width: 200px; height: 100px; 
                background-color: white; border:2px solid grey; z-index:9999; font-size:14px;
                padding: 10px">
    <b>Legenda - Região</b><br>
    <i style="background: blue; width: 10px; height: 10px; display: inline-block;"></i> Oeste<br>
    <i style="background: green; width: 10px; height: 10px; display: inline-block;"></i> Pampulha<br>
    <i style="background: orange; width: 10px; height: 10px; display: inline-block;"></i> Centro<br>
    </div>
    '''
    mapa.get_root().html.add_child(folium.Element(legenda_html))

    return mapa._repr_html_()


@app.get("/calendario", response_class=HTMLResponse)
def calendario_eventos():
    db: Session = SessionLocal()
    locais = db.query(Local).all()
    eventos = db.query(Evento).join(Local).all()

    # Encontrar todos os meses com eventos
    meses = set()
    for evento in eventos:
        meses.add((evento.data_inicio.year, evento.data_inicio.month))
    meses_ordenados = sorted(meses)

    # Agrupar eventos por local e mês
    eventos_por_local_mes = {}
    for evento in eventos:
        local_nome = evento.local.nome
        mes = (evento.data_inicio.year, evento.data_inicio.month)
        chave = (local_nome, mes)
        if chave not in eventos_por_local_mes:
            eventos_por_local_mes[chave] = []
        eventos_por_local_mes[chave].append(evento)

    # Cores por região
    cores = {
        "Oeste": "blue",
        "Pampulha": "green",
        "Centro": "orange"
    }

    html = """
    <html>
    <head>
        <title>Calendário de Eventos BH</title>
        <style>
            body { font-family: Arial, sans-serif; }
            .legenda { position: fixed; top: 10px; right: 10px; background: white; border: 2px solid grey; padding: 10px; }
            table { border-collapse: collapse; width: 100%; margin: 20px; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; vertical-align: top; }
            th { background-color: #f2f2f2; }
            .evento { margin: 2px 0; padding: 2px; border-radius: 3px; }
        </style>
    </head>
    <body>
        <h1>Calendário de Eventos de Belo Horizonte</h1>
        <div class="legenda">
            <b>Regiões</b><br>
            <span style="color: blue;">Oeste</span><br>
            <span style="color: green;">Pampulha</span><br>
            <span style="color: orange;">Centro</span>
        </div>
        <table>
            <tr>
                <th>Local</th>
    """

    # Cabeçalhos dos meses
    for ano_mes, mes in meses_ordenados:
        nome_mes = meses_pt[mes]
        html += f"<th>{nome_mes} {ano_mes}</th>"
    html += "</tr>"

    # Linhas dos locais
    for local in locais:
        cor_regiao = cores.get(local.regiao, "gray")
        html += f"<tr><td style='background-color: {cor_regiao}; color: white;'><b>{local.nome}</b><br><small>({local.regiao})</small></td>"
        for ano_mes, mes in meses_ordenados:
            cell_content = ""
            eventos_mes = eventos_por_local_mes.get((local.nome, (ano_mes, mes)), [])
            for evento in eventos_mes:
                cor = cores.get(local.regiao, "gray")
                cell_content += f'<div class="evento" style="background-color: {cor}; color: white;">{evento.nome}<br>{evento.data_inicio.strftime("%d/%m")} - {evento.data_fim.strftime("%d/%m")}</div>'
            html += f"<td>{cell_content}</td>"
        html += "</tr>"

    html += "</table></body></html>"
    return html