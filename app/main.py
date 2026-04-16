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
            table { border-collapse: collapse; width: 100%; margin: 20px; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; vertical-align: top; }
            th { background-color: #f2f2f2; }
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
        html += f"<th>{nome_mes} {ano_mes}</th>"
    html += "</tr>"

    # Linhas dos locais
    for local in locais:
        cor_regiao = cores.get(local.regiao, "gray")
        html += f"<tr><td style='background-color: {cor_regiao}; color: white; vertical-align: top;'><b>{local.nome}</b><br><small>({local.regiao})</small></td>"
        for ano_mes, mes in meses_ordenados:
            cell_content = '<table style="width: 100%; border-collapse: collapse; font-size: 11px;">'
            
            # Cabeçalho do calendário
            cell_content += '<tr><th style="border: 1px solid #ddd; padding: 2px;">Seg</th><th style="border: 1px solid #ddd; padding: 2px;">Ter</th><th style="border: 1px solid #ddd; padding: 2px;">Qua</th><th style="border: 1px solid #ddd; padding: 2px;">Qui</th><th style="border: 1px solid #ddd; padding: 2px;">Sex</th><th style="border: 1px solid #ddd; padding: 2px;">Sab</th><th style="border: 1px solid #ddd; padding: 2px;">Dom</th></tr>'
            
            # Gerar calendário
            import calendar as cal_module
            mes_cal = cal_module.monthcalendar(ano_mes, mes)
            
            for semana in mes_cal:
                cell_content += '<tr>'
                for dia in semana:
                    if dia == 0:
                        cell_content += '<td style="border: 1px solid #ddd; padding: 2px; height: 80px;"></td>'
                    else:
                        # Obter eventos deste dia
                        eventos_do_dia = []
                        for evento in eventos_por_local_mes.get((local.nome, (ano_mes, mes)), []):
                            if evento.data_inicio.day <= dia <= evento.data_fim.day:
                                eventos_do_dia.append(evento)
                        
                        if eventos_do_dia:
                            # Célula com eventos
                            cell_content += f'<td style="border: 1px solid #ddd; padding: 2px; height: 80px; background-color: {cor_regiao}; color: white; font-size: 9px; vertical-align: top; overflow: auto;">'
                            cell_content += f'<div style="font-weight: bold; margin-bottom: 2px;">{dia}</div>'
                            for evento in eventos_do_dia:
                                cell_content += f'<div style="font-size: 8px; margin: 2px 0; padding: 2px; background-color: rgba(0,0,0,0.3); border-radius: 2px;"><b>{evento.nome}</b><br>{evento.data_inicio.strftime("%d/%m")} - {evento.data_fim.strftime("%d/%m")}<br>👥 {evento.publico_estimado}</div>'
                            cell_content += '</td>'
                        else:
                            # Célula sem eventos
                            cell_content += f'<td style="border: 1px solid #ddd; padding: 2px; height: 80px; vertical-align: top;">{dia}</td>'
                cell_content += '</tr>'
            
            cell_content += '</table>'
            
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