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


@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
    <head>
        <title>Eventos BH</title>
        <style>
            body { font-family: Arial, sans-serif; background: #f8f9fb; margin: 0; padding: 0; }
            .page { max-width: 900px; margin: 40px auto; padding: 30px; background: white; border-radius: 12px; box-shadow: 0 16px 48px rgba(0,0,0,0.08); }
            h1 { margin-top: 0; color: #1f2937; }
            p { color: #4b5563; font-size: 16px; line-height: 1.6; }
            .menu { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 30px; }
            .card { flex: 1 1 250px; min-width: 220px; padding: 24px; border-radius: 14px; background: #eef2ff; color: #1f2937; text-decoration: none; box-shadow: 0 8px 24px rgba(15,23,42,0.08); transition: transform 0.2s ease, box-shadow 0.2s ease; }
            .card:hover { transform: translateY(-3px); box-shadow: 0 16px 32px rgba(15,23,42,0.16); }
            .card h2 { margin: 0 0 10px; font-size: 22px; }
            .card p { margin: 0; color: #374151; }
            .footer { margin-top: 32px; font-size: 14px; color: #6b7280; }
        </style>
    </head>
    <body>
        <div class="page">
            <h1>MapaCalorEventos BH</h1>
            <p>Bem-vindo ao painel de eventos de Belo Horizonte. Use os menus abaixo para visualizar o mapa interativo dos eventos ou o calendário de programação.</p>
            <div class="menu">
                <a class="card" href="/mapa">
                    <h2>Mapa de Eventos</h2>
                    <p>Visualize a localização de cada evento no mapa de Belo Horizonte com cores por região.</p>
                </a>
                <a class="card" href="/calendario">
                    <h2>Calendário de Eventos</h2>
                    <p>Veja os eventos organizados por local e mês em um calendário compacto e colorido.</p>
                </a>
            </div>
            <div class="footer">Acesse o mapa ou o calendário para explorar os eventos cadastrados.</div>
        </div>
    </body>
    </html>
    """


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
    dias_com_eventos = {}  # Para rastrear quais dias têm eventos
    
    for evento in eventos:
        local_nome = evento.local.nome
        mes = (evento.data_inicio.year, evento.data_inicio.month)
        chave = (local_nome, mes)
        if chave not in eventos_por_local_mes:
            eventos_por_local_mes[chave] = []
        eventos_por_local_mes[chave].append(evento)
        
        # Marcar todos os dias do período do evento
        for dia in range(evento.data_inicio.day, evento.data_fim.day + 1):
            dias_com_eventos[(local_nome, evento.data_inicio.year, evento.data_inicio.month, dia)] = True

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
            .header { display: flex; align-items: center; gap: 20px; margin: 20px; }
            .logo { width: 150px; height: 150px; }
            .header h1 { margin: 0; }
            .legenda { display: flex; gap: 10px; justify-content: center; margin: 20px 0; }
            .regiao-box { padding: 10px 20px; border-radius: 5px; color: white; font-weight: bold; }
            table { border-collapse: collapse; width: 100%; margin: 20px; font-size: 14px; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; vertical-align: top; }
            th { background-color: #f2f2f2; font-size: 16px; }
            .evento { margin: 2px 0; padding: 2px; border-radius: 3px; }
        </style>
    </head>
    <body>
        <div class="header">
            <img class="logo" src="https://visitebelohorizonte.com/wp-content/uploads/2025/07/LOGO-1.svg" alt="Logo BH">
            <h1>Calendário de Eventos de Belo Horizonte</h1>
        </div>
        <div class="legenda">
            <div class="regiao-box" style="background-color: blue;">Regional Oeste</div>
            <div class="regiao-box" style="background-color: green;">Regional Pampulha</div>
            <div class="regiao-box" style="background-color: orange;">Regional Centro</div>
        </div>
        <table>
            <tr>
                <th>Local</th>
    """

    # Cabeçalhos dos meses
    for ano_mes, mes in meses_ordenados:
        nome_mes = meses_pt[mes]
        html += f"<th style='text-align: center;'>{nome_mes} {ano_mes}</th>"
    html += "</tr>"

    # Linhas dos locais
    for local in locais:
        cor_regiao = cores.get(local.regiao, "gray")
        html += f"<tr><td style='background-color: {cor_regiao}; color: white; vertical-align: top;'><b>{local.nome}</b><br><small>({local.regiao})</small></td>"
        
        for ano_mes, mes in meses_ordenados:
            # Obter todos os eventos deste mês para este local
            eventos_do_mes = eventos_por_local_mes.get((local.nome, (ano_mes, mes)), [])
            
            if eventos_do_mes:
                # Agrupar eventos por período (mesmo dia de início e fim)
                eventos_agrupados = {}
                for evento in eventos_do_mes:
                    chave = (evento.data_inicio.day, evento.data_fim.day)
                    if chave not in eventos_agrupados:
                        eventos_agrupados[chave] = []
                    eventos_agrupados[chave].append(evento)
                
                cell_content = f'<div style="background-color: {cor_regiao}; color: white; padding: 8px; border-radius: 5px; font-size: 11px;">'
                cell_content += f'<div style="font-weight: bold; margin-bottom: 5px; text-align: center;">{len(eventos_do_mes)} evento(s)</div>'
                
                for (dia_inicio, dia_fim), eventos_periodo in eventos_agrupados.items():
                    if dia_inicio == dia_fim:
                        cell_content += f'<div style="margin: 3px 0; padding: 3px; background-color: rgba(255,255,255,0.2); border-radius: 3px;">'
                        cell_content += f'<b>Dia {dia_inicio}:</b><br>'
                    else:
                        cell_content += f'<div style="margin: 3px 0; padding: 3px; background-color: rgba(255,255,255,0.2); border-radius: 3px;">'
                        cell_content += f'<b>Dias {dia_inicio}-{dia_fim}:</b><br>'
                    
                    for evento in eventos_periodo:
                        cell_content += f'• {evento.nome}<br>'
                        cell_content += f'<small>👥 {evento.publico_estimado} pessoas</small><br>'
                    cell_content += '</div>'
                
                cell_content += '</div>'
            else:
                cell_content = '<div style="background-color: #f9f9f9; padding: 8px; border-radius: 5px; text-align: center; color: #666;">Sem eventos</div>'
            
            html += f"<td style='padding: 2px; vertical-align: top;'>{cell_content}</td>"
        html += "</tr>"

    # Adicionar rodapé com contagem de eventos
    total_eventos = len(eventos)
    html += f"""
    <tr>
        <td colspan="{len(meses_ordenados) + 1}" style="text-align: left; padding: 20px;">
            <div style="background-color: red; color: white; font-weight: bold; padding: 20px; border-radius: 5px; display: inline-block; min-width: 300px; font-size: 18px;">
                Total de Eventos Cadastrados: {total_eventos}
            </div>
        </td>
    </tr>
    """

    html += "</table></body></html>"
    return html