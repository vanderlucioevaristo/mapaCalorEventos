from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from .database import SessionLocal, engine, Base
from .models import (
    Evento,
    Local,
    Regional,
    Anunciante,
    Usuario,
    InteracaoClique,
    Estado,
    Municipio,
)
from authlib.integrations.starlette_client import OAuth, OAuthError
from dotenv import load_dotenv
from starlette.middleware.sessions import SessionMiddleware
import folium
from folium.plugins import MarkerCluster
import calendar
from datetime import datetime, date
from html import escape
from typing import Optional
import math
import json
import os
import httpx
import hashlib
import hmac
import secrets
import re
from urllib.parse import quote_plus
from pathlib import Path

#para executar 
# cd /Users/vanderevaristo/ProjetosVander/mapacaloreventos source .venv/bin/activate uvicorn mapaCalorEventos.app.main:app --reload
# python3 mapaCalorEventos/app/main.py

#  python3 -m uvicorn mapaCalorEventos.app.main:app --port 8004
#  python3 -m mapaCalorEventos.app.seed
#. lsof -i :8004 | grep -v COMMAND | awk '{print $2}' | xargs kill -9

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")
ENV_FILE_PATH = BASE_DIR / ".env"


def _resolver_versao_app() -> str:
    # Funciona tanto em execucao via "mapaCalorEventos.app.main" quanto "app.main".
    try:
        from mapaCalorEventos import __version__ as version

        return version
    except Exception:
        try:
            init_file = Path(__file__).resolve().parents[1] / "__init__.py"
            content = init_file.read_text(encoding="utf-8")
            match = re.search(r'__version__\s*=\s*"([^"]+)"', content)
            if match:
                return match.group(1)
        except Exception:
            pass

    return "0.0.0"


APP_VERSION = _resolver_versao_app()

# Meses em português
meses_pt = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", 
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

Base.metadata.create_all(bind=engine)

TIPOS_EVENTO = ["Carnaval", "Negócios", "Turismo"]
ESTADO_PADRAO_NOME = "Minas Gerais"
ESTADO_PADRAO_SIGLA = "MG"
MUNICIPIO_PADRAO_NOME = "Belo Horizonte"


def normalizar_tipo_evento(tipo_evento: Optional[str]) -> str:
    if tipo_evento in TIPOS_EVENTO:
        return tipo_evento
    return "Negócios"


def garantir_colunas_locais():
    with engine.begin() as conn:
        colunas = {
            row[1] for row in conn.execute(text("PRAGMA table_info(locais)"))
        }
        if "acessibilidade" not in colunas:
            conn.execute(
                text(
                    "ALTER TABLE locais ADD COLUMN acessibilidade INTEGER NOT NULL DEFAULT 0"
                )
            )
        if "proximo_metro" not in colunas:
            conn.execute(
                text(
                    "ALTER TABLE locais ADD COLUMN proximo_metro INTEGER NOT NULL DEFAULT 0"
                )
            )
        if "restaurantes" not in colunas:
            conn.execute(
                text(
                    "ALTER TABLE locais ADD COLUMN restaurantes INTEGER NOT NULL DEFAULT 1"
                )
            )
        if "tipo_evento" not in colunas:
            conn.execute(
                text(
                    "ALTER TABLE locais ADD COLUMN tipo_evento TEXT NOT NULL DEFAULT 'Negócios'"
                )
            )
        if "contato_telefone" not in colunas:
            conn.execute(text("ALTER TABLE locais ADD COLUMN contato_telefone TEXT"))
        if "site_url" not in colunas:
            conn.execute(text("ALTER TABLE locais ADD COLUMN site_url TEXT"))
        if "municipio_id" not in colunas:
            conn.execute(text("ALTER TABLE locais ADD COLUMN municipio_id INTEGER"))
        conn.execute(
            text(
                "UPDATE locais SET tipo_evento = 'Negócios' WHERE tipo_evento IS NULL OR TRIM(tipo_evento) = ''"
            )
        )


def garantir_colunas_eventos():
    with engine.begin() as conn:
        colunas = {
            row[1] for row in conn.execute(text("PRAGMA table_info(eventos)"))
        }
        if "tipo_evento" not in colunas:
            conn.execute(
                text(
                    "ALTER TABLE eventos ADD COLUMN tipo_evento TEXT NOT NULL DEFAULT 'Negócios'"
                )
            )
        if "contato_telefone" not in colunas:
            conn.execute(text("ALTER TABLE eventos ADD COLUMN contato_telefone TEXT"))
        if "site_url" not in colunas:
            conn.execute(text("ALTER TABLE eventos ADD COLUMN site_url TEXT"))
        conn.execute(
            text(
                "UPDATE eventos SET tipo_evento = 'Negócios' WHERE tipo_evento IS NULL OR TRIM(tipo_evento) = ''"
            )
        )


def garantir_colunas_anunciantes():
    with engine.begin() as conn:
        colunas = {
            row[1] for row in conn.execute(text("PRAGMA table_info(anunciantes)"))
        }
        if "datainicio" not in colunas:
            conn.execute(text("ALTER TABLE anunciantes ADD COLUMN datainicio DATE"))
        if "datafim" not in colunas:
            conn.execute(text("ALTER TABLE anunciantes ADD COLUMN datafim DATE"))
        if "tipo" not in colunas:
            conn.execute(text("ALTER TABLE anunciantes ADD COLUMN tipo TEXT NOT NULL DEFAULT ''"))
        if "contato_telefone" not in colunas:
            conn.execute(text("ALTER TABLE anunciantes ADD COLUMN contato_telefone TEXT"))
        if "site_url" not in colunas:
            conn.execute(text("ALTER TABLE anunciantes ADD COLUMN site_url TEXT"))
        conn.execute(
            text("UPDATE anunciantes SET tipo = '' WHERE tipo IS NULL")
        )


def garantir_colunas_usuarios():
    with engine.begin() as conn:
        colunas = {
            row[1] for row in conn.execute(text("PRAGMA table_info(usuarios)"))
        }
        if not colunas:
            return
        if "role" not in colunas:
            conn.execute(text("ALTER TABLE usuarios ADD COLUMN role TEXT NOT NULL DEFAULT 'admin'"))
        if "foto_url" not in colunas:
            conn.execute(text("ALTER TABLE usuarios ADD COLUMN foto_url TEXT"))
        if "telefone" not in colunas:
            conn.execute(text("ALTER TABLE usuarios ADD COLUMN telefone TEXT"))
        if "endereco" not in colunas:
            conn.execute(text("ALTER TABLE usuarios ADD COLUMN endereco TEXT"))
        conn.execute(text("UPDATE usuarios SET role = 'admin' WHERE role IS NULL OR TRIM(role) = ''"))


garantir_colunas_locais()
garantir_colunas_eventos()
garantir_colunas_anunciantes()
garantir_colunas_usuarios()


def seed_localidades_padrao():
    db: Session = SessionLocal()
    try:
        estado = db.query(Estado).filter(Estado.nome == ESTADO_PADRAO_NOME).first()
        if not estado:
            estado = Estado(nome=ESTADO_PADRAO_NOME, sigla=ESTADO_PADRAO_SIGLA)
            db.add(estado)
            db.flush()

        municipio = (
            db.query(Municipio)
            .filter(Municipio.nome == MUNICIPIO_PADRAO_NOME, Municipio.estado_id == estado.id)
            .first()
        )
        if not municipio:
            municipio = Municipio(nome=MUNICIPIO_PADRAO_NOME, estado_id=estado.id)
            db.add(municipio)
            db.flush()

        db.query(Local).filter(Local.municipio_id.is_(None)).update(
            {Local.municipio_id: municipio.id}, synchronize_session=False
        )
        db.commit()
    finally:
        db.close()


seed_localidades_padrao()

REGIONAIS_PADRAO = [
    "Barreiro", "Centro-Sul", "Leste", "Nordeste", "Noroeste", "Norte", "Oeste", "Pampulha", "Sul", "Venda Nova"
]

CORES_REGIONAIS = {
    "Barreiro": "red",
    "Leste": "purple",
    "Nordeste": "cadetblue",
    "Noroeste": "darkgreen",
    "Norte": "darkred",
    "Oeste": "blue",
    "Pampulha": "darkblue",
    "Sul": "green",
    "Venda Nova": "orange",
}

def seed_regionais():
    db: Session = SessionLocal()
    try:
        for nome in REGIONAIS_PADRAO:
            existe = db.query(Regional).filter(Regional.nome == nome).first()
            if not existe:
                db.add(Regional(nome=nome))
        db.commit()
    finally:
        db.close()


def cor_regional(nome_regional: str) -> str:
    return CORES_REGIONAIS.get(nome_regional, "gray")


def coordenadas_validas(latitude, longitude) -> bool:
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return False
    if math.isnan(lat) or math.isnan(lon):
        return False
    return -90 <= lat <= 90 and -180 <= lon <= 180


def _pontos_estado(db: Session, estado_id: Optional[int]) -> list[tuple[float, float]]:
    if not estado_id:
        return []

    locais_estado = (
        db.query(Local)
        .join(Municipio, Local.municipio_id == Municipio.id)
        .filter(Municipio.estado_id == estado_id)
        .all()
    )

    pontos = []
    for local in locais_estado:
        if coordenadas_validas(local.latitude, local.longitude):
            pontos.append((float(local.latitude), float(local.longitude)))
    return pontos


def _centro_mapa_por_estado(db: Session, estado_id: Optional[int]) -> tuple[float, float, int]:
    """Retorna centro e zoom sugerido usando os locais do estado selecionado."""
    pontos = _pontos_estado(db, estado_id)

    if not pontos:
        return (-19.9191, -43.9386, 12)

    lats = [lat for lat, _ in pontos]
    lons = [lon for _, lon in pontos]
    centro_lat = sum(lats) / len(lats)
    centro_lon = sum(lons) / len(lons)

    lat_span = max(lats) - min(lats)
    lon_span = max(lons) - min(lons)
    span = max(lat_span, lon_span)

    if span > 8:
        zoom = 5
    elif span > 4:
        zoom = 6
    elif span > 2:
        zoom = 7
    elif span > 1:
        zoom = 8
    elif span > 0.5:
        zoom = 9
    else:
        zoom = 10

    return (centro_lat, centro_lon, zoom)


def _bounds_mapa_por_estado(db: Session, estado_id: Optional[int]) -> Optional[list[list[float]]]:
    pontos = _pontos_estado(db, estado_id)
    if not pontos:
        return None

    lats = [lat for lat, _ in pontos]
    lons = [lon for _, lon in pontos]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)

    if min_lat == max_lat and min_lon == max_lon:
        delta = 0.03
        min_lat -= delta
        max_lat += delta
        min_lon -= delta
        max_lon += delta

    return [[min_lat, min_lon], [max_lat, max_lon]]


def _normalizar_site_url(site_url: str) -> str:
    url = (site_url or "").strip()
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return f"https://{url}"


def _site_html(site_url: str) -> str:
    url = _normalizar_site_url(site_url)
    if not url:
        return ""
    return f'<a href="{escape(url)}" target="_blank" rel="noopener noreferrer">Site</a><br>'


def _site_html_rastreado(site_url: str, entidade_tipo: str, entidade_id: int) -> str:
    url = _normalizar_site_url(site_url)
    if not url:
        return ""
    destino = quote_plus(url)
    href = f"/interacoes/site?entidade_tipo={quote_plus(entidade_tipo)}&entidade_id={entidade_id}&destino={destino}"
    return f'<a href="{href}" target="_blank" rel="noopener noreferrer">Site</a><br>'


def _telefone_html(telefone: str) -> str:
    telefone_limpo = (telefone or "").strip()
    if not telefone_limpo:
        return "Telefone: Não informado<br>"
    return f"Telefone: {escape(telefone_limpo)}<br>"


def _registrar_interacao(entidade_tipo: str, entidade_id: int, acao: str) -> None:
    tipo = (entidade_tipo or "").strip().lower()
    acao_normalizada = (acao or "").strip().lower()
    if tipo not in {"local", "evento", "anunciante"}:
        return
    if acao_normalizada not in {"visualizado", "acessado"}:
        return
    if not isinstance(entidade_id, int) or entidade_id <= 0:
        return

    hoje = datetime.now().date()
    db: Session = SessionLocal()
    try:
        db.add(
            InteracaoClique(
                entidade_tipo=tipo,
                entidade_id=entidade_id,
                acao=acao_normalizada,
                data_referencia=hoje,
                criado_em=hoje,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def geocodificar_endereco(endereco: str) -> tuple[Optional[float], Optional[float]]:
    endereco_limpo = (endereco or "").strip()
    if not endereco_limpo:
        return None, None

    consulta = f"{endereco_limpo}, Belo Horizonte, MG, Brasil"
    url = "https://nominatim.openstreetmap.org/search"
    headers = {
        "User-Agent": "mapa-calor-eventos/1.0 (contato: admin@sistema.local)"
    }
    params = {
        "q": consulta,
        "format": "json",
        "limit": 1,
        "addressdetails": 0,
    }

    try:
        with httpx.Client(timeout=8.0) as client:
            response = client.get(url, params=params, headers=headers)
            response.raise_for_status()
            resultados = response.json()
    except Exception:
        return None, None

    if not resultados:
        return None, None

    try:
        latitude = float(resultados[0].get("lat"))
        longitude = float(resultados[0].get("lon"))
    except (TypeError, ValueError):
        return None, None

    if not coordenadas_validas(latitude, longitude):
        return None, None

    return latitude, longitude


def anunciante_ativo_em_data(anunciante: Anunciante, referencia: date) -> bool:
    if anunciante.datainicio and referencia < anunciante.datainicio:
        return False
    if anunciante.datafim and referencia > anunciante.datafim:
        return False
    return True


def popup_anunciante_html(anunciante: Anunciante, map_name: str) -> str:
    lat = float(anunciante.latitude)
    lon = float(anunciante.longitude)
    tipo_anunciante = (anunciante.tipo or "").strip()
    tipo_html = (
        f"Tipo: {escape(tipo_anunciante)}<br>"
        if tipo_anunciante
        else "Tipo: Não informado<br>"
    )
    periodo = ""
    if anunciante.datainicio and anunciante.datafim:
        periodo = f"Ativo: {anunciante.datainicio} a {anunciante.datafim}<br>"
    elif anunciante.datainicio:
        periodo = f"Ativo desde: {anunciante.datainicio}<br>"
    elif anunciante.datafim:
        periodo = f"Ativo até: {anunciante.datafim}<br>"

    imagem_html = ""
    if anunciante.urlimagem:
        imagem_url = escape(anunciante.urlimagem)
        imagem_html = (
            f'<br><img src="{imagem_url}" alt="Imagem do anunciante" '
            'style="max-width:180px; max-height:120px; border-radius:6px; object-fit:cover;">'
        )

    return (
        f"<div data-track-entidade=\"anunciante\" data-track-id=\"{anunciante.id}\">"
        f"<b>Anunciante: {escape(anunciante.nome or '')}</b><br>"
        f"{tipo_html}"
        f"Endereço: {escape(anunciante.endereco or '')}<br>"
        f"{_telefone_html(anunciante.contato_telefone)}"
        f"{_site_html_rastreado(anunciante.site_url, 'anunciante', anunciante.id)}"
        f"{periodo}"
        f"Lat: {lat}, Lon: {lon}"
        f"{imagem_html}"
        f"{link_rota_html(lat, lon, map_name, anunciante.nome or 'Anunciante')}"
        "</div>"
    )


def icone_anunciante(anunciante: Anunciante):
    if anunciante.urlimagem:
        try:
            return folium.CustomIcon(
                icon_image=anunciante.urlimagem,
                icon_size=(42, 42),
                icon_anchor=(21, 21),
                popup_anchor=(0, -18),
            )
        except Exception:
            # Se a URL da imagem estiver inválida, usa ícone padrão.
            pass
    return folium.Icon(color="lightgray", icon="bullhorn", prefix="fa")


def adicionar_marcador_anunciante(mapa, anunciante: Anunciante, map_name: str) -> None:
    lat = float(anunciante.latitude)
    lon = float(anunciante.longitude)
    tipo_anunciante = (anunciante.tipo or "").strip()
    tooltip_tipo = f" ({tipo_anunciante})" if tipo_anunciante else ""

    # Halo para destacar o anunciante no mapa.
    folium.CircleMarker(
        location=[lat, lon],
        radius=20,
        color="#166534",
        weight=3,
        fill=True,
        fill_color="#22c55e",
        fill_opacity=0.45,
        opacity=1,
    ).add_to(mapa)

    marcador_html = (
        '<div style="position:relative;width:40px;height:40px;">'
        '<style>'
        '@keyframes pulseAnuncianteVerde {'
        '0% { transform: scale(0.82); opacity: 0.85; }'
        '70% { transform: scale(1.35); opacity: 0.08; }'
        '100% { transform: scale(1.45); opacity: 0; }'
        '}'
        '.anunciante-pulse-green {'
        'position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);'
        'width:22px;height:22px;border-radius:50%;'
        'background:rgba(22,163,74,0.55);'
        'animation:pulseAnuncianteVerde 1.1s infinite ease-out;'
        '}'
        '.anunciante-arrow-green {'
        'position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);'
        'width:22px;height:22px;border-radius:50%;'
        'background:#22c55e;border:2px solid #14532d;'
        'display:flex;align-items:center;justify-content:center;'
        'box-shadow:0 4px 14px rgba(20,83,45,.7);'
        '}'
        '</style>'
        '<div class="anunciante-pulse-green"></div>'
        '<div class="anunciante-arrow-green">'
        '<span style="color:#fff;font-size:16px;font-weight:900;line-height:1;">↓</span>'
        '</div>'
        '</div>'
    )

    folium.Marker(
        location=[lat, lon],
        popup=popup_anunciante_html(anunciante, map_name),
        tooltip=f"Anunciante ativo: {anunciante.nome}{tooltip_tipo}",
        icon=folium.DivIcon(html=marcador_html, icon_size=(40, 40), icon_anchor=(20, 20)),
        z_index_offset=2000,
    ).add_to(mapa)


def painel_anunciantes_ativos_html(total: int) -> str:
    return f'''
    <div style="position: fixed;
                bottom: 12px; right: 18px; z-index: 9999;
                background: white; border: 2px solid #f59e0b;
                border-radius: 10px; padding: 8px 10px;
                box-shadow: 0 8px 20px rgba(0,0,0,0.15);
                font-size: 13px; color: #111827;">
        <b>📢 Anunciantes ativos:</b> {total}
    </div>
    '''


def legenda_mapa_html(
    regionais: list[str],
    cabecalho: str = "Legenda - Regional",
    contagem_por_regional: dict[str, int] = None,
    exibir_contagem: bool = True,
) -> str:
    if contagem_por_regional is None:
        contagem_por_regional = {}

    def _rotulo_regional(regional: str) -> str:
        nome = escape(regional)
        if not exibir_contagem:
            return nome
        return f"{nome} ({contagem_por_regional.get(regional, 0)})"

    itens = "".join(
        [
            f'<i style="background: {cor_regional(regional)}; width: 10px; height: 10px; display: inline-block;"></i> {_rotulo_regional(regional)}<br>'
            for regional in regionais
        ]
    )
    return f'''
    <div style="position: fixed;
                top: 50px; left: 50px; width: 290px;
                background-color: white; border:2px solid grey; z-index:9999; font-size:14px;
                padding: 10px">
    <b>{escape(cabecalho)}</b><br>
    {itens}
    </div>
    '''


def atalho_inicio_mapa_html() -> str:
    return f'''
    <div style="position: fixed;
                top: 12px; left: 64px; z-index: 9999;
                box-shadow: 0 8px 20px rgba(0,0,0,0.12);">
        {botao_voltar_portal_html()}
    </div>
    '''


def botao_voltar_portal_html(label: str = "Voltar ao portal", extra_style: str = "") -> str:
    estilo = (
        "display:inline-flex;align-items:center;gap:8px;"
        "padding:10px 14px;border-radius:999px;"
        "background:#ffffff;color:#0f172a;text-decoration:none;font-weight:700;"
        "border:1px solid #d7e2ee;box-shadow:0 8px 20px rgba(15,23,42,0.10);"
        + (extra_style or "")
    )
    return f'<a href="{PORTAL_PUBLICO_PATH}" style="{estilo}">&#8592; {escape(label)}</a>'


def recursos_rota_mapa_html(map_name: str) -> str:
    map_name_json = json.dumps(map_name)
    return f'''
    <style>
        .leaflet-control-clear-route button {{
            background: #b91c1c;
            color: #fff;
            border: none;
            border-radius: 4px;
            padding: 6px 10px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
        }}
        .leaflet-control-clear-route button:hover {{
            background: #991b1b;
        }}
        .leaflet-control-route-distance {{
            background: #ffffff;
            border: 2px solid #1d4ed8;
            border-radius: 8px;
            padding: 6px 10px;
            box-shadow: 0 8px 20px rgba(0,0,0,0.12);
            color: #0f172a;
            font-size: 12px;
            font-weight: 600;
            min-width: 145px;
        }}
    </style>
    <script>
        window.routeLayer_{map_name} = null;
        window.routeOriginMarker_{map_name} = null;
        window.routeDestinationMarker_{map_name} = null;
        window.selectedOrigin_{map_name} = null;
        window.routeDistanceControl_{map_name} = null;
        window.routeDistanceContainer_{map_name} = null;

        function formatarDistancia_{map_name}(metros) {{
            if (!Number.isFinite(metros)) return '--';
            if (metros < 1000) return `${{Math.round(metros)}} m`;
            return `${{(metros / 1000).toFixed(2)}} km`;
        }}

        function formatarDuracao_{map_name}(segundos) {{
            if (!Number.isFinite(segundos) || segundos <= 0) return '--';
            const totalMin = Math.round(segundos / 60);
            if (totalMin < 60) return `${{totalMin}} min`;
            const horas = Math.floor(totalMin / 60);
            const minutos = totalMin % 60;
            if (minutos === 0) return `${{horas}} h`;
            return `${{horas}} h ${{minutos}} min`;
        }}

        function mostrarResumoRota_{map_name}(metros, segundos) {{
            const mapa = window[{map_name_json}];
            if (!mapa) return;

            if (!window.routeDistanceControl_{map_name}) {{
                const RouteDistanceControl = L.Control.extend({{
                    options: {{ position: 'bottomleft' }},
                    onAdd: function() {{
                        const container = L.DomUtil.create('div', 'leaflet-control-route-distance');
                        container.style.display = 'none';
                        L.DomEvent.disableClickPropagation(container);
                        window.routeDistanceContainer_{map_name} = container;
                        return container;
                    }}
                }});

                window.routeDistanceControl_{map_name} = new RouteDistanceControl();
                mapa.addControl(window.routeDistanceControl_{map_name});
            }}

            if (window.routeDistanceContainer_{map_name}) {{
                window.routeDistanceContainer_{map_name}.innerHTML =
                    `Distância: <b>${{formatarDistancia_{map_name}(metros)}}</b><br>Tempo estimado: <b>${{formatarDuracao_{map_name}(segundos)}}</b>`;
                window.routeDistanceContainer_{map_name}.style.display = 'block';
            }}
        }}

        function limparRotaMapa_{map_name}() {{
            const mapa = window[{map_name_json}];
            if (!mapa) return;

            if (window.routeLayer_{map_name}) {{
                mapa.removeLayer(window.routeLayer_{map_name});
                window.routeLayer_{map_name} = null;
            }}
            if (window.routeOriginMarker_{map_name}) {{
                mapa.removeLayer(window.routeOriginMarker_{map_name});
                window.routeOriginMarker_{map_name} = null;
            }}
            if (window.routeDestinationMarker_{map_name}) {{
                mapa.removeLayer(window.routeDestinationMarker_{map_name});
                window.routeDestinationMarker_{map_name} = null;
            }}
            if (window.routeDistanceContainer_{map_name}) {{
                window.routeDistanceContainer_{map_name}.style.display = 'none';
                window.routeDistanceContainer_{map_name}.innerHTML = '';
            }}
        }}

        function adicionarControleLimparRota_{map_name}() {{
            const mapa = window[{map_name_json}];
            if (!mapa || window.clearRouteControl_{map_name}) return;

            const ClearControl = L.Control.extend({{
                options: {{ position: 'topright' }},
                onAdd: function() {{
                    const container = L.DomUtil.create('div', 'leaflet-control leaflet-bar leaflet-control-clear-route');
                    const button = L.DomUtil.create('button', '', container);
                    button.type = 'button';
                    button.innerText = 'Limpar rota';
                    L.DomEvent.disableClickPropagation(container);
                    L.DomEvent.on(button, 'click', function() {{
                        limparRotaMapa_{map_name}();
                    }});
                    return container;
                }}
            }});

            window.clearRouteControl_{map_name} = new ClearControl();
            mapa.addControl(window.clearRouteControl_{map_name});
        }}

        async function desenharRota_{map_name}(origLat, origLon, destLat, destLon, origemNome, destinoNome) {{
            const mapa = window[{map_name_json}];
            if (!mapa) return;
            limparRotaMapa_{map_name}();

            window.routeOriginMarker_{map_name} = L.marker([origLat, origLon])
                .addTo(mapa)
                .bindPopup(origemNome || 'Origem');

            window.routeDestinationMarker_{map_name} = L.marker([destLat, destLon])
                .addTo(mapa)
                .bindPopup(destinoNome || 'Destino');

            const url = `https://router.project-osrm.org/route/v1/driving/${{origLon}},${{origLat}};${{destLon}},${{destLat}}?overview=full&geometries=geojson`;

            try {{
                const response = await fetch(url);
                const data = await response.json();
                if (!response.ok || !data.routes || !data.routes.length) {{
                    throw new Error('Rota não encontrada');
                }}

                const coordinates = data.routes[0].geometry.coordinates.map(function(coord) {{
                    return [coord[1], coord[0]];
                }});
                const distanciaMetros = Number(data.routes[0].distance || 0);
                const duracaoSegundos = Number(data.routes[0].duration || 0);

                window.routeLayer_{map_name} = L.polyline(coordinates, {{
                    color: '#2563eb',
                    weight: 5,
                    opacity: 0.85
                }}).addTo(mapa);

                if (Number.isFinite(distanciaMetros) && distanciaMetros > 0) {{
                    window.routeLayer_{map_name}.bindPopup(
                        `Distância da rota: <b>${{formatarDistancia_{map_name}(distanciaMetros)}}</b><br>Tempo estimado: <b>${{formatarDuracao_{map_name}(duracaoSegundos)}}</b>`
                    );
                }}

                mostrarResumoRota_{map_name}(distanciaMetros, duracaoSegundos);

                mapa.fitBounds(window.routeLayer_{map_name}.getBounds(), {{ padding: [30, 30] }});
            }} catch (error) {{
                alert('Não foi possível traçar a rota neste momento.');
            }}
        }}

        function definirOrigem_{map_name}(origLat, origLon, origemNome) {{
            window.selectedOrigin_{map_name} = {{
                lat: origLat,
                lon: origLon,
                nome: origemNome || 'Origem selecionada'
            }};
            alert(`Origem definida: ${{window.selectedOrigin_{map_name}.nome}}`);
        }};

        async function tracarRotaOrigemSelecionada_{map_name}(destLat, destLon, destinoNome) {{
            const origem = window.selectedOrigin_{map_name};
            if (!origem) {{
                alert('Defina um ponto de origem em um marcador antes de traçar a rota.');
                return;
            }}

            await desenharRota_{map_name}(
                origem.lat,
                origem.lon,
                destLat,
                destLon,
                origem.nome,
                destinoNome || 'Destino'
            );
        }}

        async function tracarRota_{map_name}(destLat, destLon, destinoNome) {{
            const mapa = window[{map_name_json}];
            if (!mapa) return;

            if (!navigator.geolocation) {{
                alert('Geolocalização não disponível neste navegador.');
                return;
            }}

            navigator.geolocation.getCurrentPosition(
                async function(posicao) {{
                    await desenharRota_{map_name}(
                        posicao.coords.latitude,
                        posicao.coords.longitude,
                        destLat,
                        destLon,
                        'Sua localização',
                        destinoNome || 'Destino'
                    );
                }},
                function() {{
                    alert('Não foi possível obter sua localização para traçar a rota.');
                }},
                {{ enableHighAccuracy: true, timeout: 10000 }}
            );
        }}

        function registrarInteracao_{map_name}(entidadeTipo, entidadeId, acao) {{
            const tipo = (entidadeTipo || '').toLowerCase();
            const acaoNormalizada = (acao || '').toLowerCase();
            if (!tipo || !entidadeId || !acaoNormalizada) return;
            const url = `/interacoes/registrar?entidade_tipo=${{encodeURIComponent(tipo)}}&entidade_id=${{encodeURIComponent(entidadeId)}}&acao=${{encodeURIComponent(acaoNormalizada)}}`;
            fetch(url, {{ method: 'GET', keepalive: true }}).catch(function() {{}});
        }}

        function configurarRastreioPopup_{map_name}() {{
            const mapa = window[{map_name_json}];
            if (!mapa || window.popupTrackingBound_{map_name}) return;
            window.popupTrackingBound_{map_name} = true;

            mapa.on('popupopen', function(ev) {{
                const popupEl = ev && ev.popup && ev.popup.getElement ? ev.popup.getElement() : null;
                if (!popupEl) return;
                const trackEl = popupEl.querySelector('[data-track-entidade][data-track-id]');
                if (!trackEl) return;

                const entidadeTipo = trackEl.getAttribute('data-track-entidade');
                const entidadeId = trackEl.getAttribute('data-track-id');
                registrarInteracao_{map_name}(entidadeTipo, entidadeId, 'visualizado');
            }});
        }}

        setTimeout(adicionarControleLimparRota_{map_name}, 0);
        setTimeout(configurarRastreioPopup_{map_name}, 0);
    </script>
    '''


def link_rota_html(latitude: float, longitude: float, map_name: str, destino_nome: str) -> str:
    destino_nome_json = json.dumps(destino_nome)
    return (
        '<br><br>'
        f"<button type=\"button\" onclick='definirOrigem_{map_name}({latitude}, {longitude}, {destino_nome_json})' "
        'style="display:inline-block; margin-right:6px; margin-bottom:6px; padding:6px 10px; background:#334155; color:white; '
        'text-decoration:none; border:none; border-radius:6px; font-weight:600; cursor:pointer;">Definir origem</button>'
        f"<button type=\"button\" onclick='tracarRotaOrigemSelecionada_{map_name}({latitude}, {longitude}, {destino_nome_json})' "
        'style="display:inline-block; margin-right:6px; margin-bottom:6px; padding:6px 10px; background:#0f766e; color:white; '
        'text-decoration:none; border:none; border-radius:6px; font-weight:600; cursor:pointer;">Rota da origem selecionada</button>'
        f"<button type=\"button\" onclick='tracarRota_{map_name}({latitude}, {longitude}, {destino_nome_json})' "
        'style="display:inline-block; margin-bottom:6px; padding:6px 10px; background:#2563eb; color:white; '
        'text-decoration:none; border:none; border-radius:6px; font-weight:600; cursor:pointer;">Traçar rota</button>'
    )


def legenda_mapa_html_interativa(
    regionais: list[str],
    cabecalho: str,
    map_name: str,
    bounds_por_regional: dict[str, dict[str, float]],
    contagem_por_regional: dict[str, int] = None,
    exibir_contagem: bool = True,
) -> str:
    map_name_json = json.dumps(map_name)
    if contagem_por_regional is None:
        contagem_por_regional = {}
    itens = []
    for regional in regionais:
        estilo_ponto = (
            f'background: {cor_regional(regional)}; width: 10px; height: 10px; '
            'display: inline-block; margin-right: 6px;'
        )
        contagem = contagem_por_regional.get(regional, 0)
        if exibir_contagem:
            rotulo_regional = f"{escape(regional)} ({contagem})"
        else:
            rotulo_regional = escape(regional)
        if regional in bounds_por_regional:
            itens.append(
                f'<button type="button" class="legend-link" '
                f'onclick="zoomParaRegional_{map_name}({json.dumps(regional)})">'
                f'<i style="{estilo_ponto}"></i>{rotulo_regional}</button>'
            )
        else:
            itens.append(
                f'<span class="legend-disabled"><i style="{estilo_ponto}"></i>{rotulo_regional}</span>'
            )

    bounds_json = json.dumps(bounds_por_regional)
    itens_html = "".join(item + "<br>" for item in itens)

    return f'''
    <div style="position: fixed;
                top: 50px; left: 50px; width: 290px;
                background-color: white; border:2px solid grey; z-index:9999; font-size:14px;
                padding: 10px">
    <b>{escape(cabecalho)}</b><br>
    <small>Clique na regional para aproximar</small><br><br>
    {itens_html}
    </div>
    <style>
        .legend-link {{
            border: none;
            background: transparent;
            padding: 2px 0;
            cursor: pointer;
            color: #1d4ed8;
            text-align: left;
            font-size: 14px;
        }}
        .legend-link:hover {{ text-decoration: underline; }}
        .legend-disabled {{ color: #6b7280; }}
    </style>
    <script>
        const boundsRegionais_{map_name} = {bounds_json};
        function zoomParaRegional_{map_name}(regional) {{
            const bounds = boundsRegionais_{map_name}[regional];
            if (!bounds) return;
            const mapa = window[{map_name_json}];
            if (!mapa) return;
            const unicoPonto =
                bounds.min_lat === bounds.max_lat && bounds.min_lon === bounds.max_lon;
            if (unicoPonto) {{
                mapa.setView([bounds.min_lat, bounds.min_lon], 15);
                return;
            }}
            mapa.fitBounds([
                [bounds.min_lat, bounds.min_lon],
                [bounds.max_lat, bounds.max_lon]
            ]);
        }}
    </script>
    '''

seed_regionais()

app = FastAPI()
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "troque-esta-chave-em-producao"),
)

oauth = OAuth()

if os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"):
    oauth.register(
        name="google",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

if os.getenv("FACEBOOK_CLIENT_ID") and os.getenv("FACEBOOK_CLIENT_SECRET"):
    oauth.register(
        name="facebook",
        client_id=os.getenv("FACEBOOK_CLIENT_ID"),
        client_secret=os.getenv("FACEBOOK_CLIENT_SECRET"),
        access_token_url="https://graph.facebook.com/v19.0/oauth/access_token",
        authorize_url="https://www.facebook.com/v19.0/dialog/oauth",
        api_base_url="https://graph.facebook.com/v19.0/",
        client_kwargs={"scope": "email,public_profile"},
    )

if os.getenv("APPLE_CLIENT_ID") and os.getenv("APPLE_CLIENT_SECRET"):
    oauth.register(
        name="apple",
        client_id=os.getenv("APPLE_CLIENT_ID"),
        client_secret=os.getenv("APPLE_CLIENT_SECRET"),
        server_metadata_url="https://appleid.apple.com/.well-known/openid-configuration",
        client_kwargs={"scope": "name email"},
    )


def _provedores_oauth_disponiveis() -> list[str]:
    if not USE_SOCIAL_LOGIN:
        return []

    provedores = []
    for nome in ("google", "facebook", "apple"):
        if oauth.create_client(nome):
            provedores.append(nome)
    return provedores


def _oauth_base_url(request: Request) -> str:
    base = os.getenv("OAUTH_BASE_URL")
    if base:
        return base.rstrip("/")
    return str(request.base_url).rstrip("/")


def _oauth_redirect_uri(request: Request, provider: str) -> str:
    return f"{_oauth_base_url(request)}/auth/{provider}/callback"


def _next_path_or_default(valor: Optional[str], default: str = "/") -> str:
    destino = (valor or "").strip()
    if not destino.startswith("/"):
        return default
    return destino


USUARIO_MESTRE = {
    "provider": "sistema",
    "id": "mestre",
    "name": "Administrador",
    "email": "admin@sistema.local",
    "role": "super_admin",
}

EMAILS_ADMIN = {
    "vanderlucio.evaristo@gmail.com",
    "vanderlucioevaristo@gmail.com",
}

REQUIRE_LOGIN = os.getenv("REQUIRE_LOGIN", "true").lower() not in ("false", "0", "no")
USE_SOCIAL_LOGIN = REQUIRE_LOGIN and os.getenv("USE_SOCIAL_LOGIN", "true").lower() not in ("false", "0", "no")
SENHA_SALT = os.getenv("PASSWORD_SALT", "eventos-bh-salt")
EXIBIR_LOGO = os.getenv("EXIBIR_LOGO", "true").lower() not in ("false", "0", "no")
EXIBIR_CONTAGEM_LOCAIS_MAPA = os.getenv("EXIBIR_CONTAGEM_LOCAIS_MAPA", "true").lower() not in ("false", "0", "no")
EXIBIR_CONTAGEM_EVENTOS_MAPA = os.getenv("EXIBIR_CONTAGEM_EVENTOS_MAPA", "true").lower() not in ("false", "0", "no")
EXIBIR_ANUNCIANTES_MAPA = os.getenv("EXIBIR_ANUNCIANTES_MAPA", "true").lower() not in ("false", "0", "no")
LOGO_URL = os.getenv(
    "LOGO_URL",
    "https://visitebelohorizonte.com/wp-content/uploads/2025/07/LOGO-1.svg",
).strip()
PORTAL_PUBLICO_PATH = "/public/portal"


def _usuario_atual(request: Request) -> dict:
    """Retorna o usuário da sessão ou o mestre quando login não é exigido."""
    if not REQUIRE_LOGIN:
        return request.session.get("user") or USUARIO_MESTRE
    return request.session.get("user") or {}


def _chaves_localidade(_publico: bool = False) -> tuple[str, str]:
    if _publico:
        return ("public_estado_id", "public_municipio_id")
    return ("admin_estado_id", "admin_municipio_id")


def _definir_localidade_sessao(
    request: Request,
    estado_id: int,
    municipio_id: int,
    _publico: bool = False,
) -> None:
    chave_estado, chave_municipio = _chaves_localidade(_publico)
    request.session[chave_estado] = int(estado_id)
    request.session[chave_municipio] = int(municipio_id)


def _obter_localidade_sessao(request: Request, _publico: bool = False) -> tuple[Optional[int], Optional[int]]:
    chave_estado, chave_municipio = _chaves_localidade(_publico)
    estado_id = request.session.get(chave_estado)
    municipio_id = request.session.get(chave_municipio)
    try:
        estado_id = int(estado_id) if estado_id is not None else None
        municipio_id = int(municipio_id) if municipio_id is not None else None
    except (TypeError, ValueError):
        return (None, None)
    return (estado_id, municipio_id)


def _localidade_valida(db: Session, estado_id: int, municipio_id: int) -> bool:
    municipio = db.query(Municipio).filter(Municipio.id == municipio_id).first()
    if not municipio:
        return False
    return municipio.estado_id == estado_id


def _redirect_se_localidade_nao_definida(request: Request, _publico: bool = False):
    estado_id, municipio_id = _obter_localidade_sessao(request, _publico=_publico)
    if not estado_id or not municipio_id:
        destino = "/public/localidade" if _publico else "/localidade"
        return RedirectResponse(url=destino, status_code=303)

    db: Session = SessionLocal()
    try:
        if not _localidade_valida(db, estado_id, municipio_id):
            destino = "/public/localidade" if _publico else "/localidade"
            return RedirectResponse(url=destino, status_code=303)
    finally:
        db.close()

    return None


def _normalizar_cpf(cpf: str) -> str:
    return re.sub(r"\D", "", cpf or "")


def _hash_senha(senha: str) -> str:
    salt = secrets.token_hex(16)
    derivacao = hashlib.pbkdf2_hmac(
        "sha256",
        (senha or "").encode("utf-8"),
        f"{SENHA_SALT}:{salt}".encode("utf-8"),
        120000,
    )
    return f"{salt}${derivacao.hex()}"


def _verificar_senha(senha: str, senha_hash: str) -> bool:
    if not senha_hash or "$" not in senha_hash:
        return False
    salt, esperado = senha_hash.split("$", 1)
    derivacao = hashlib.pbkdf2_hmac(
        "sha256",
        (senha or "").encode("utf-8"),
        f"{SENHA_SALT}:{salt}".encode("utf-8"),
        120000,
    )
    return hmac.compare_digest(derivacao.hex(), esperado)


def _usuario_para_sessao(usuario: Usuario) -> dict:
    return {
        "provider": "local",
        "id": str(usuario.id),
        "name": usuario.nome,
        "email": usuario.email,
        "cpf": usuario.cpf,
        "role": usuario.role or "admin",
    }


def _eh_super_admin(user: dict) -> bool:
    if (user.get("role") or "").lower() == "super_admin":
        return True
    email = (user.get("email") or "").lower()
    return email in {e.lower() for e in EMAILS_ADMIN}


def _eh_admin_ou_super_admin(user: dict) -> bool:
    role = (user.get("role") or "").lower()
    return role in {"admin", "super_admin"} or _eh_super_admin(user)


def _redirect_se_nao_autenticado(request: Request):
    user = _usuario_atual(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    # Garante que a sessão reflita o usuário mestre quando login não é exigido
    if not REQUIRE_LOGIN and not request.session.get("user"):
        request.session["user"] = USUARIO_MESTRE
    return None


def _redirect_se_nao_admin(request: Request):
    user = _usuario_atual(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if not _eh_admin_ou_super_admin(user):
        return RedirectResponse(url="/?acesso=negado", status_code=303)
    return None


def _redirect_se_nao_super_admin(request: Request):
    user = _usuario_atual(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if not _eh_super_admin(user):
        return RedirectResponse(url="/?acesso=negado", status_code=303)
    return None


def _atualizar_variavel_env(chave: str, valor: str) -> None:
    conteudo = ENV_FILE_PATH.read_text(encoding="utf-8") if ENV_FILE_PATH.exists() else ""
    linhas = conteudo.splitlines()
    prefixo = f"{chave}="
    atualizada = False

    for i, linha in enumerate(linhas):
        if linha.startswith(prefixo):
            linhas[i] = f"{chave}={valor}"
            atualizada = True
            break

    if not atualizada:
        if linhas and linhas[-1].strip() != "":
            linhas.append("")
        linhas.append(f"{chave}={valor}")

    ENV_FILE_PATH.write_text("\n".join(linhas) + "\n", encoding="utf-8")


@app.get("/interacoes/registrar")
def registrar_interacao_get(entidade_tipo: str, entidade_id: int, acao: str):
    _registrar_interacao(entidade_tipo, entidade_id, acao)
    return {"ok": True}


@app.get("/interacoes/site")
def registrar_e_redirecionar_site(entidade_tipo: str, entidade_id: int, destino: str):
    _registrar_interacao(entidade_tipo, entidade_id, "acessado")
    destino_normalizado = _normalizar_site_url(destino)
    if not destino_normalizado:
        return RedirectResponse(url="/", status_code=303)
    return RedirectResponse(url=destino_normalizado, status_code=303)


@app.get("/board-interacoes", response_class=HTMLResponse)
def board_interacoes(request: Request):
    redirect = _redirect_se_nao_admin(request)
    if redirect:
        return redirect

    db: Session = SessionLocal()
    try:
        interacoes = db.query(InteracaoClique).order_by(InteracaoClique.data_referencia.desc()).all()
        nomes_locais = {
            item_id: nome or ""
            for item_id, nome in db.query(Local.id, Local.nome).all()
        }
        nomes_eventos = {
            item_id: nome or ""
            for item_id, nome in db.query(Evento.id, Evento.nome).all()
        }
        nomes_anunciantes = {
            item_id: nome or ""
            for item_id, nome in db.query(Anunciante.id, Anunciante.nome).all()
        }

        por_dia = {}
        por_mes = {}
        por_ano = {}

        def acumular(dicionario: dict, chave: str, acao: str):
            if chave not in dicionario:
                dicionario[chave] = {"visualizado": 0, "acessado": 0}
            if acao in {"visualizado", "acessado"}:
                dicionario[chave][acao] += 1

        for item in interacoes:
            dia = item.data_referencia.strftime("%Y-%m-%d")
            mes = item.data_referencia.strftime("%Y-%m")
            ano = item.data_referencia.strftime("%Y")
            acao = (item.acao or "").strip().lower()
            acumular(por_dia, dia, acao)
            acumular(por_mes, mes, acao)
            acumular(por_ano, ano, acao)

        linhas_dia = "".join(
            [
                f"<tr><td>{d}</td><td>{dados['visualizado']}</td><td>{dados['acessado']}</td><td>{dados['visualizado'] + dados['acessado']}</td></tr>"
                for d, dados in sorted(por_dia.items(), reverse=True)
            ]
        ) or '<tr><td colspan="4">Sem dados</td></tr>'
        linhas_mes = "".join(
            [
                f"<tr><td>{m}</td><td>{dados['visualizado']}</td><td>{dados['acessado']}</td><td>{dados['visualizado'] + dados['acessado']}</td></tr>"
                for m, dados in sorted(por_mes.items(), reverse=True)
            ]
        ) or '<tr><td colspan="4">Sem dados</td></tr>'
        linhas_ano = "".join(
            [
                f"<tr><td>{a}</td><td>{dados['visualizado']}</td><td>{dados['acessado']}</td><td>{dados['visualizado'] + dados['acessado']}</td></tr>"
                for a, dados in sorted(por_ano.items(), reverse=True)
            ]
        ) or '<tr><td colspan="4">Sem dados</td></tr>'

        def nome_entidade(interacao: InteracaoClique) -> str:
            tipo = (interacao.entidade_tipo or "").strip().lower()
            if tipo == "local":
                nome = nomes_locais.get(interacao.entidade_id)
            elif tipo == "evento":
                nome = nomes_eventos.get(interacao.entidade_id)
            elif tipo == "anunciante":
                nome = nomes_anunciantes.get(interacao.entidade_id)
            else:
                nome = ""
            return nome or f"{tipo.capitalize()} #{interacao.entidade_id}"

        por_dia_entidade = {}
        for item in interacoes:
            dia = item.data_referencia.strftime("%Y-%m-%d")
            tipo = (item.entidade_tipo or "").strip().lower()
            nome = nome_entidade(item)
            chave = (dia, tipo, nome)
            if chave not in por_dia_entidade:
                por_dia_entidade[chave] = {"visualizado": 0, "acessado": 0}
            acao = (item.acao or "").strip().lower()
            if acao in {"visualizado", "acessado"}:
                por_dia_entidade[chave][acao] += 1

        linhas_interacoes = "".join(
            [
                f"<tr><td>{dia}</td><td>{escape(tipo.capitalize())}</td><td>{escape(nome)}</td><td>{dados['visualizado']}</td><td>{dados['acessado']}</td><td>{dados['visualizado'] + dados['acessado']}</td></tr>"
                for (dia, tipo, nome), dados in sorted(
                    por_dia_entidade.items(),
                    key=lambda item: (item[0][0], item[0][1], item[0][2]),
                    reverse=True,
                )
            ]
        ) or '<tr><td colspan="6">Sem dados</td></tr>'

        return f"""
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <style>
                @media (max-width: 768px) {{
                    html {{ font-size: 16px; }}
                    body {{ padding: 12px !important; }}
                    input, select, textarea, button, .btn, a.btn {{
                        font-size: 16px !important;
                        min-height: 44px;
                            }}
                    table {{
                        display: block;
                        width: 100%;
                        overflow-x: auto;
                        -webkit-overflow-scrolling: touch;
                        white-space: nowrap;
                            }}
                        }}
            </style>
            <style>
                 (max-width: 768px) {{
                    html {{ font-size: 16px; }}
                    body {{ padding: 12px !important; }}
                    input, select, textarea, button, .btn, a.btn {{
                        font-size: 16px !important;
                        min-height: 44px;
                            }}
                    table {{
                        display: block;
                        width: 100%;
                        overflow-x: auto;
                        -webkit-overflow-scrolling: touch;
                        white-space: nowrap;
                            }}
                        }}
            </style>
            <title>Board de Interações</title>
            <style>
                body {{ font-family: Arial, sans-serif; background: #f8f9fb; margin: 0; padding: 24px; }}
                .page {{ max-width: 980px; margin: 0 auto; background: #fff; border-radius: 12px; padding: 24px; box-shadow: 0 14px 36px rgba(0,0,0,.08); }}
                h1 {{ margin-top: 0; color: #1f2937; }}
                .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }}
                .card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px; }}
                .details-card {{ margin-top: 16px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px; }}
                .table-wrap {{ max-height: 360px; overflow: auto; }}
                table {{ width: 100%; border-collapse: collapse; }}
                th, td {{ border-bottom: 1px solid #e5e7eb; padding: 8px; text-align: left; font-size: 14px; }}
                th {{ color: #111827; background: #f3f4f6; }}
                a {{ color: #1f2937; text-decoration: none; font-weight: 700; }}
                @media (max-width: 960px) {{ .grid {{ grid-template-columns: 1fr; }} }}
            </style>
        </head>
        <body>
            <div class="page">
                {botao_voltar_portal_html()}
                <h1>Board de interações</h1>
                <div class="grid">
                    <div class="card">
                        <h3>Total por dia</h3>
                        <table>
                            <tr><th>Dia</th><th>Visualizado</th><th>Acessado</th><th>Total</th></tr>
                            {linhas_dia}
                        </table>
                    </div>
                    <div class="card">
                        <h3>Total por mês</h3>
                        <table>
                            <tr><th>Mês</th><th>Visualizado</th><th>Acessado</th><th>Total</th></tr>
                            {linhas_mes}
                        </table>
                    </div>
                    <div class="card">
                        <h3>Total por ano</h3>
                        <table>
                            <tr><th>Ano</th><th>Visualizado</th><th>Acessado</th><th>Total</th></tr>
                            {linhas_ano}
                        </table>
                    </div>
                </div>
                <div class="details-card">
                    <h3>Total diário por entidade e tipo de interação</h3>
                    <div class="table-wrap">
                        <table>
                            <tr><th>Data</th><th>Tipo</th><th>Nome</th><th>Visualizado</th><th>Acessado</th><th>Total</th></tr>
                            {linhas_interacoes}
                        </table>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
    finally:
        db.close()


@app.get("/configuracoes", response_class=HTMLResponse)
def pagina_configuracoes(request: Request, msg: Optional[str] = None):
    redirect = _redirect_se_nao_super_admin(request)
    if redirect:
        return redirect

    exibir_logo_checked = "checked" if EXIBIR_LOGO else ""
    exibir_contagem_locais_checked = "checked" if EXIBIR_CONTAGEM_LOCAIS_MAPA else ""
    exibir_contagem_eventos_checked = "checked" if EXIBIR_CONTAGEM_EVENTOS_MAPA else ""
    exibir_anunciantes_mapa_checked = "checked" if EXIBIR_ANUNCIANTES_MAPA else ""
    logo_url_valor = escape(LOGO_URL or "")
    msg_html = ""
    if msg == "ok":
        msg_html = '<div class="msg ok">Configurações salvas com sucesso.</div>'
    elif msg == "erro":
        msg_html = '<div class="msg erro">Não foi possível salvar as configurações.</div>'

    return f"""
    <html>
    <head>
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <style>
                @media (max-width: 768px) {{
                    html {{ font-size: 16px; }}
                    body {{ padding: 12px !important; }}
                    input, select, textarea, button, .btn, a.btn {{
                        font-size: 16px !important;
                        min-height: 44px;
                            }}
                    table {{
                        display: block;
                        width: 100%;
                        overflow-x: auto;
                        -webkit-overflow-scrolling: touch;
                        white-space: nowrap;
                            }}
                        }}
            </style>
            <style>
                 (max-width: 768px) {{
                    html {{ font-size: 16px; }}
                    body {{ padding: 12px !important; }}
                    input, select, textarea, button, .btn, a.btn {{
                        font-size: 16px !important;
                        min-height: 44px;
                            }}
                    table {{
                        display: block;
                        width: 100%;
                        overflow-x: auto;
                        -webkit-overflow-scrolling: touch;
                        white-space: nowrap;
                            }}
                        }}
            </style>
        <title>Configurações - Eventos</title>
        <style>
            body {{ font-family: Arial, sans-serif; background: #f8f9fb; margin: 0; padding: 24px; }}
            .page {{ max-width: 740px; margin: 0 auto; background: white; border-radius: 12px; padding: 24px; box-shadow: 0 14px 36px rgba(0,0,0,.08); }}
            h1 {{ margin-top: 0; color: #1f2937; }}
            .desc {{ color: #4b5563; margin-bottom: 20px; }}
            label {{ display: block; margin: 10px 0 6px; font-weight: 700; color: #111827; }}
            input[type='text'] {{ width: 100%; border: 1px solid #d1d5db; border-radius: 8px; padding: 10px 12px; box-sizing: border-box; }}
            .check {{ display: flex; align-items: center; gap: 8px; margin: 14px 0 6px; }}
            .check input {{ width: 16px; height: 16px; }}
            .actions {{ margin-top: 18px; display: flex; gap: 10px; }}
            .btn {{ border: none; border-radius: 8px; padding: 10px 14px; font-weight: 700; cursor: pointer; text-decoration: none; display: inline-block; }}
            .btn-primary {{ background: #1f2937; color: #fff; }}
            .btn-secondary {{ background: #e5e7eb; color: #111827; }}
            .msg {{ border-radius: 8px; padding: 10px 12px; margin-bottom: 14px; font-size: 14px; }}
            .ok {{ background: #dcfce7; color: #166534; }}
            .erro {{ background: #fee2e2; color: #991b1b; }}
        </style>
    </head>
    <body>
        <div class="page">
            <h1>Configurações Visuais</h1>
            <div class="desc">Altere os parâmetros globais de exibição do sistema.</div>
            {msg_html}
            <form method="post" action="/configuracoes">
                <label class="check">
                    <input type="checkbox" name="exibir_logo" value="1" {exibir_logo_checked} />
                    Exibir logo nas páginas que usam essa configuração
                </label>

                <label class="check">
                    <input type="checkbox" name="exibir_contagem_locais_mapa" value="1" {exibir_contagem_locais_checked} />
                    Exibir contagem por regional no mapa de locais
                </label>

                <label class="check">
                    <input type="checkbox" name="exibir_contagem_eventos_mapa" value="1" {exibir_contagem_eventos_checked} />
                    Exibir contagem por regional no mapa de eventos
                </label>

                <label class="check">
                    <input type="checkbox" name="exibir_anunciantes_mapa" value="1" {exibir_anunciantes_mapa_checked} />
                    Exibir anunciantes nos mapas
                </label>

                <label for="logo_url">URL do logo</label>
                <input id="logo_url" type="text" name="logo_url" value="{logo_url_valor}" placeholder="https://..." />

                <div class="actions">
                    <button class="btn btn-primary" type="submit">Salvar</button>
                    {botao_voltar_portal_html()}
                </div>
            </form>
        </div>
    </body>
    </html>
    """


@app.post("/configuracoes")
def salvar_configuracoes(
    request: Request,
    exibir_logo: Optional[str] = Form(None),
    exibir_contagem_locais_mapa: Optional[str] = Form(None),
    exibir_contagem_eventos_mapa: Optional[str] = Form(None),
    exibir_anunciantes_mapa: Optional[str] = Form(None),
    logo_url: str = Form(""),
):
    redirect = _redirect_se_nao_super_admin(request)
    if redirect:
        return redirect

    global EXIBIR_LOGO, LOGO_URL, EXIBIR_CONTAGEM_LOCAIS_MAPA, EXIBIR_CONTAGEM_EVENTOS_MAPA, EXIBIR_ANUNCIANTES_MAPA

    try:
        novo_exibir_logo = bool(exibir_logo)
        novo_exibir_contagem_locais_mapa = bool(exibir_contagem_locais_mapa)
        novo_exibir_contagem_eventos_mapa = bool(exibir_contagem_eventos_mapa)
        novo_exibir_anunciantes_mapa = bool(exibir_anunciantes_mapa)
        nova_logo_url = (logo_url or "").strip()

        _atualizar_variavel_env("EXIBIR_LOGO", "true" if novo_exibir_logo else "false")
        _atualizar_variavel_env(
            "EXIBIR_CONTAGEM_LOCAIS_MAPA",
            "true" if novo_exibir_contagem_locais_mapa else "false",
        )
        _atualizar_variavel_env(
            "EXIBIR_CONTAGEM_EVENTOS_MAPA",
            "true" if novo_exibir_contagem_eventos_mapa else "false",
        )
        _atualizar_variavel_env(
            "EXIBIR_ANUNCIANTES_MAPA",
            "true" if novo_exibir_anunciantes_mapa else "false",
        )
        _atualizar_variavel_env("LOGO_URL", nova_logo_url)

        EXIBIR_LOGO = novo_exibir_logo
        EXIBIR_CONTAGEM_LOCAIS_MAPA = novo_exibir_contagem_locais_mapa
        EXIBIR_CONTAGEM_EVENTOS_MAPA = novo_exibir_contagem_eventos_mapa
        EXIBIR_ANUNCIANTES_MAPA = novo_exibir_anunciantes_mapa
        LOGO_URL = nova_logo_url
        return RedirectResponse(url="/configuracoes?msg=ok", status_code=303)
    except Exception:
        return RedirectResponse(url="/configuracoes?msg=erro", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    next_path = _next_path_or_default(request.query_params.get("next"), PORTAL_PUBLICO_PATH)
    if not REQUIRE_LOGIN:
        return RedirectResponse(url=next_path, status_code=303)
    if request.session.get("user"):
        return RedirectResponse(url=next_path, status_code=303)

    auth_error = request.query_params.get("erro")
    msg = request.query_params.get("msg")
    provedores = _provedores_oauth_disponiveis()
    botoes_html = ""
    for provedor in provedores:
        rotulo = provedor.capitalize()
        cor = {
            "google": "#1a73e8",
            "facebook": "#1877f2",
            "apple": "#111827",
        }.get(provedor, "#2563eb")
        botoes_html += (
            f'<a class="btn" style="background:{cor};" href="/auth/{provedor}/login?next={quote_plus(next_path)}">'
            f'Entrar com {rotulo}</a>'
        )

    erro_html = ""
    if auth_error:
        erro_html = (
            '<div class="warn" style="background:#fee2e2;color:#991b1b;">'
            f'Falha ao autenticar com {escape(auth_error)}. '
            'Revise as credenciais e a URL de callback configurada.</div>'
        )

    if msg == "credenciais_invalidas":
        erro_html = '<div class="warn" style="background:#fee2e2;color:#991b1b;">Email/CPF ou senha inválidos.</div>'
    elif msg == "cadastro_ok":
        erro_html = '<div class="warn" style="background:#dcfce7;color:#166534;">Cadastro concluído. Faça login para continuar.</div>'
    elif msg == "email_ou_cpf_duplicado":
        erro_html = '<div class="warn" style="background:#fee2e2;color:#991b1b;">Já existe usuário com este email ou CPF.</div>'
    elif msg == "senha_redefinida":
        erro_html = '<div class="warn" style="background:#dcfce7;color:#166534;">Senha redefinida com sucesso. Faça login com a nova senha.</div>'

    if not botoes_html and USE_SOCIAL_LOGIN:
        botoes_html = (
            '<div class="warn">Nenhum provedor OAuth configurado. '
            'Defina variáveis GOOGLE_CLIENT_ID/SECRET, FACEBOOK_CLIENT_ID/SECRET '
            'ou APPLE_CLIENT_ID/SECRET.</div>'
        )

    google_config_html = ""
    if USE_SOCIAL_LOGIN and "google" not in provedores:
        google_config_html = (
            '<div class="setup">'
            '<strong>Google:</strong> configure no Google Cloud Console o redirect URI '
            f'<code>{escape(_oauth_redirect_uri(request, "google"))}</code> '
            'e preencha GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET no arquivo .env.'
            '</div>'
        )

    social_html = ""
    if USE_SOCIAL_LOGIN:
        social_html = f'<div class="divider"></div>{botoes_html}{google_config_html}'

    return f"""
    <html>
    <head>
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <style>
                @media (max-width: 768px) {{
                    html {{ font-size: 16px; }}
                    body {{ padding: 12px !important; }}
                    input, select, textarea, button, .btn, a.btn {{
                        font-size: 16px !important;
                        min-height: 44px;
                            }}
                    table {{
                        display: block;
                        width: 100%;
                        overflow-x: auto;
                        -webkit-overflow-scrolling: touch;
                        white-space: nowrap;
                            }}
                        }}
            </style>
            <style>
                 (max-width: 768px) {{
                    html {{ font-size: 16px; }}
                    body {{ padding: 12px !important; }}
                    input, select, textarea, button, .btn, a.btn {{
                        font-size: 16px !important;
                        min-height: 44px;
                            }}
                    table {{
                        display: block;
                        width: 100%;
                        overflow-x: auto;
                        -webkit-overflow-scrolling: touch;
                        white-space: nowrap;
                            }}
                        }}
            </style>
        <title>Login - Eventos</title>
        <style>
            body {{ font-family: Arial, sans-serif; background: #f3f4f6; margin: 0; }}
            .wrap {{ min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 24px; }}
            .card {{ width: 100%; max-width: 420px; background: white; border-radius: 12px; padding: 28px; box-shadow: 0 14px 32px rgba(0,0,0,.12); }}
            .home-link {{ display: inline-block; margin-bottom: 12px; text-decoration: none; color: #1f2937; font-weight: 700; }}
            h1 {{ margin: 0 0 8px; color: #111827; }}
            p {{ margin: 0 0 20px; color: #4b5563; }}
            .btn {{ display: block; color: white; text-decoration: none; font-weight: 700; text-align: center; padding: 11px 14px; border-radius: 8px; margin-bottom: 10px; }}
            .btn-alt {{ background: #111827; }}
            .btn-lite {{ background: #4b5563; }}
            .warn {{ background: #fef3c7; color: #92400e; border-radius: 8px; padding: 12px; font-size: 14px; }}
            .setup {{ margin-top: 14px; background: #eff6ff; color: #1e3a8a; border-radius: 8px; padding: 12px; font-size: 14px; line-height: 1.5; }}
            code {{ background: #dbeafe; padding: 2px 6px; border-radius: 6px; }}
            .divider {{ margin: 18px 0; border-top: 1px solid #e5e7eb; }}
            .label {{ display: block; font-weight: 700; margin: 10px 0 6px; color: #111827; }}
            .input {{ width: 100%; border: 1px solid #d1d5db; border-radius: 8px; padding: 10px 12px; margin-bottom: 8px; box-sizing: border-box; }}
            .help {{ color: #6b7280; font-size: 13px; margin-bottom: 8px; }}
            .link-action {{ display: inline-block; margin: 8px 0 14px; color: #0f766e; font-weight: 700; text-decoration: none; }}
            .link-action:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <div class="wrap">
            <div class="card">
                {botao_voltar_portal_html(extra_style='margin-bottom:12px;')}
                <h1>Entrar no Eventos</h1>
                <p>Use email ou CPF com senha. Se ainda não tiver cadastro, crie em poucos segundos.</p>
                {erro_html}
                <form method="post" action="/login/local">
                    <input type="hidden" name="next" value="{escape(next_path)}" />
                    <label class="label" for="identificador">Email ou CPF</label>
                    <input class="input" id="identificador" name="identificador" placeholder="email@dominio.com ou 00000000000" required />
                    <label class="label" for="senha">Senha</label>
                    <input class="input" id="senha" name="senha" type="password" required />
                    <button class="btn btn-alt" type="submit">Entrar</button>
                </form>
                <a class="link-action" href="/esqueci-senha">Esqueci minha senha</a>
                <a class="btn btn-lite" href="/cadastro-rapido">Não tem cadastro? Registre-se aqui!</a>
                {social_html}
            </div>
        </div>
    </body>
    </html>
    """


@app.post("/login/local")
def login_local(
    request: Request,
    identificador: str = Form(...),
    senha: str = Form(...),
    next: str = Form(PORTAL_PUBLICO_PATH),
):
    next_path = _next_path_or_default(next, PORTAL_PUBLICO_PATH)
    if not REQUIRE_LOGIN:
        return RedirectResponse(url=next_path, status_code=303)

    db: Session = SessionLocal()
    try:
        identificador_limpo = (identificador or "").strip().lower()
        cpf_limpo = _normalizar_cpf(identificador)

        usuario = db.query(Usuario).filter(Usuario.email.ilike(identificador_limpo)).first()
        if not usuario and cpf_limpo:
            usuario = db.query(Usuario).filter(Usuario.cpf == cpf_limpo).first()

        if not usuario or not _verificar_senha(senha, usuario.senha_hash):
            return RedirectResponse(
                url=f"/login?msg=credenciais_invalidas&next={quote_plus(next_path)}",
                status_code=303,
            )

        request.session["user"] = _usuario_para_sessao(usuario)
        return RedirectResponse(url=next_path, status_code=303)
    finally:
        db.close()


@app.get("/esqueci-senha", response_class=HTMLResponse)
def esqueci_senha_page(request: Request):
    if not REQUIRE_LOGIN:
        return RedirectResponse(url=PORTAL_PUBLICO_PATH, status_code=303)
    if request.session.get("user"):
        return RedirectResponse(url=PORTAL_PUBLICO_PATH, status_code=303)

    msg = request.query_params.get("msg")
    msg_html = ""
    if msg == "usuario_nao_encontrado":
        msg_html = '<div class="warn" style="background:#fee2e2;color:#991b1b;">Usuário não encontrado para o email/CPF informado.</div>'
    elif msg == "senha_curta":
        msg_html = '<div class="warn" style="background:#fee2e2;color:#991b1b;">A nova senha deve ter no mínimo 6 caracteres.</div>'
    elif msg == "confirmacao_invalida":
        msg_html = '<div class="warn" style="background:#fee2e2;color:#991b1b;">A confirmação da senha não confere.</div>'

    return f"""
    <html>
    <head>
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <style>
                @media (max-width: 768px) {{
                    html {{ font-size: 16px; }}
                    body {{ padding: 12px !important; }}
                    input, select, textarea, button, .btn, a.btn {{
                        font-size: 16px !important;
                        min-height: 44px;
                            }}
                    table {{
                        display: block;
                        width: 100%;
                        overflow-x: auto;
                        -webkit-overflow-scrolling: touch;
                        white-space: nowrap;
                            }}
                        }}
            </style>
            <style>
                 (max-width: 768px) {{
                    html {{ font-size: 16px; }}
                    body {{ padding: 12px !important; }}
                    input, select, textarea, button, .btn, a.btn {{
                        font-size: 16px !important;
                        min-height: 44px;
                            }}
                    table {{
                        display: block;
                        width: 100%;
                        overflow-x: auto;
                        -webkit-overflow-scrolling: touch;
                        white-space: nowrap;
                            }}
                        }}
            </style>
        <title>Redefinir senha - Eventos</title>
        <style>
            body {{ font-family: Arial, sans-serif; background: #f3f4f6; margin: 0; }}
            .wrap {{ min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 24px; }}
            .card {{ width: 100%; max-width: 460px; background: white; border-radius: 12px; padding: 28px; box-shadow: 0 14px 32px rgba(0,0,0,.12); }}
            h1 {{ margin: 0 0 8px; color: #111827; }}
            p {{ margin: 0 0 18px; color: #4b5563; }}
            .label {{ display: block; font-weight: 700; margin: 10px 0 6px; color: #111827; }}
            .input {{ width: 100%; border: 1px solid #d1d5db; border-radius: 8px; padding: 10px 12px; margin-bottom: 8px; box-sizing: border-box; }}
            .btn {{ width: 100%; border: none; border-radius: 8px; padding: 11px 14px; font-weight: 700; color: #fff; background: #111827; cursor: pointer; margin-top: 8px; }}
            .back {{ display: inline-block; margin-top: 12px; text-decoration: none; color: #1f2937; font-weight: 700; }}
            .warn {{ background: #fef3c7; color: #92400e; border-radius: 8px; padding: 12px; font-size: 14px; margin-bottom: 12px; }}
        </style>
    </head>
    <body>
        <div class="wrap">
            <div class="card">
                <h1>Redefinir senha</h1>
                <p>Informe seu email ou CPF e defina uma nova senha.</p>
                {msg_html}
                <form method="post" action="/esqueci-senha">
                    <label class="label" for="identificador">Email ou CPF</label>
                    <input class="input" id="identificador" name="identificador" required />
                    <label class="label" for="nova_senha">Nova senha</label>
                    <input class="input" id="nova_senha" name="nova_senha" type="password" minlength="6" required />
                    <label class="label" for="confirmar_senha">Confirmar nova senha</label>
                    <input class="input" id="confirmar_senha" name="confirmar_senha" type="password" minlength="6" required />
                    <button class="btn" type="submit">Redefinir senha</button>
                </form>
                <a class="back" href="/login">Voltar para login</a>
            </div>
        </div>
    </body>
    </html>
    """


@app.post("/esqueci-senha")
def esqueci_senha(
    request: Request,
    identificador: str = Form(...),
    nova_senha: str = Form(...),
    confirmar_senha: str = Form(...),
):
    if not REQUIRE_LOGIN:
        return RedirectResponse(url=PORTAL_PUBLICO_PATH, status_code=303)

    if len((nova_senha or "")) < 6:
        return RedirectResponse(url="/esqueci-senha?msg=senha_curta", status_code=303)
    if nova_senha != confirmar_senha:
        return RedirectResponse(url="/esqueci-senha?msg=confirmacao_invalida", status_code=303)

    identificador_limpo = (identificador or "").strip().lower()
    cpf_limpo = _normalizar_cpf(identificador)

    db: Session = SessionLocal()
    try:
        usuario = db.query(Usuario).filter(Usuario.email.ilike(identificador_limpo)).first()
        if not usuario and cpf_limpo:
            usuario = db.query(Usuario).filter(Usuario.cpf == cpf_limpo).first()
        if not usuario:
            return RedirectResponse(url="/esqueci-senha?msg=usuario_nao_encontrado", status_code=303)

        usuario.senha_hash = _hash_senha(nova_senha)
        db.commit()
        return RedirectResponse(url="/login?msg=senha_redefinida", status_code=303)
    finally:
        db.close()


@app.get("/cadastro-rapido", response_class=HTMLResponse)
def cadastro_rapido_page(request: Request):
    if not REQUIRE_LOGIN:
        return RedirectResponse(url=PORTAL_PUBLICO_PATH, status_code=303)

    if request.session.get("user"):
        return RedirectResponse(url=PORTAL_PUBLICO_PATH, status_code=303)

    return """
    <html>
    <head>
            <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Cadastro rápido - Eventos</title>
        <style>
            body { font-family: Arial, sans-serif; background: #f3f4f6; margin: 0; }
            .wrap { min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 24px; }
            .card { width: 100%; max-width: 460px; background: #fff; border-radius: 12px; padding: 26px; box-shadow: 0 14px 32px rgba(0,0,0,.12); }
            h1 { margin: 0 0 8px; color: #111827; }
            p { margin: 0 0 18px; color: #4b5563; }
            .label { display: block; font-weight: 700; margin: 8px 0 6px; color: #111827; }
            .input { width: 100%; border: 1px solid #d1d5db; border-radius: 8px; padding: 10px 12px; margin-bottom: 8px; box-sizing: border-box; }
            .btn { width: 100%; border: none; border-radius: 8px; padding: 11px 14px; font-weight: 700; color: #fff; background: #111827; cursor: pointer; }
            .back { display: inline-block; margin-top: 12px; text-decoration: none; color: #1f2937; font-weight: 700; }
        </style>
    </head>
    <body>
        <div class="wrap">
            <div class="card">
                <h1>Cadastro rápido</h1>
                <p>Cadastre-se com dados mínimos para acessar mapas, calendário e cadastros.</p>
                <form method="post" action="/cadastro-rapido">
                    <label class="label" for="nome">Nome</label>
                    <input class="input" id="nome" name="nome" required />
                    <label class="label" for="email">Email</label>
                    <input class="input" id="email" name="email" type="email" required />
                    <label class="label" for="cpf">CPF</label>
                    <input class="input" id="cpf" name="cpf" required />
                    <label class="label" for="senha">Senha</label>
                    <input class="input" id="senha" name="senha" type="password" minlength="6" required />
                    <button class="btn" type="submit">Criar conta</button>
                </form>
                <a class="back" href="/login">Voltar para login</a>
            </div>
        </div>
    </body>
    </html>
    """


@app.post("/cadastro-rapido")
def cadastro_rapido(nome: str = Form(...), email: str = Form(...), cpf: str = Form(...), senha: str = Form(...)):
    if not REQUIRE_LOGIN:
        return RedirectResponse(url=PORTAL_PUBLICO_PATH, status_code=303)

    nome_limpo = (nome or "").strip()
    email_limpo = (email or "").strip().lower()
    cpf_limpo = _normalizar_cpf(cpf)

    if not nome_limpo or not email_limpo or len(cpf_limpo) != 11 or len((senha or "")) < 6:
        return RedirectResponse(url="/login?msg=email_ou_cpf_duplicado", status_code=303)

    db: Session = SessionLocal()
    try:
        existe = db.query(Usuario).filter((Usuario.email == email_limpo) | (Usuario.cpf == cpf_limpo)).first()
        if existe:
            return RedirectResponse(url="/login?msg=email_ou_cpf_duplicado", status_code=303)

        usuario = Usuario(
            nome=nome_limpo,
            email=email_limpo,
            cpf=cpf_limpo,
            senha_hash=_hash_senha(senha),
            role="admin",
        )
        db.add(usuario)
        db.commit()
        return RedirectResponse(url="/login?msg=cadastro_ok", status_code=303)
    finally:
        db.close()


@app.get("/logout")
def logout(request: Request):
    next_path = _next_path_or_default(request.query_params.get("next"), PORTAL_PUBLICO_PATH)
    request.session.clear()
    return RedirectResponse(url=next_path, status_code=303)


@app.get("/auth/{provider}/login")
async def oauth_login(provider: str, request: Request):
    next_path = _next_path_or_default(request.query_params.get("next"), PORTAL_PUBLICO_PATH)
    if not USE_SOCIAL_LOGIN:
        return RedirectResponse(url=f"/login?next={quote_plus(next_path)}", status_code=303)

    client = oauth.create_client(provider)
    if not client:
        return RedirectResponse(url=f"/login?next={quote_plus(next_path)}", status_code=303)

    request.session["oauth_next"] = next_path
    redirect_uri = _oauth_redirect_uri(request, provider)
    kwargs = {}
    if provider == "google":
        kwargs["prompt"] = "select_account"
    return await client.authorize_redirect(request, redirect_uri, **kwargs)


@app.get("/auth/{provider}/callback")
async def oauth_callback(provider: str, request: Request):
    client = oauth.create_client(provider)
    if not client:
        return RedirectResponse(url="/login", status_code=303)

    next_path = _next_path_or_default(
        request.session.pop("oauth_next", PORTAL_PUBLICO_PATH),
        PORTAL_PUBLICO_PATH,
    )

    try:
        token = await client.authorize_access_token(request)
    except OAuthError:
        return RedirectResponse(
            url=f"/login?erro={provider}&next={quote_plus(next_path)}",
            status_code=303,
        )

    profile = {}
    if provider == "google":
        profile = token.get("userinfo") or {}
        if not profile:
            try:
                profile = await client.parse_id_token(request, token)
            except Exception:
                profile = {}
    elif provider == "facebook":
        response = await client.get("me?fields=id,name,email,picture", token=token)
        profile = response.json()
    elif provider == "apple":
        profile = token.get("userinfo") or {}
        if not profile:
            try:
                profile = await client.parse_id_token(request, token)
            except Exception:
                profile = {}

    email = (profile.get("email") or "").lower()
    role = "super_admin" if email in {e.lower() for e in EMAILS_ADMIN} else "user"

    request.session["user"] = {
        "provider": provider,
        "id": profile.get("sub") or profile.get("id") or "",
        "name": profile.get("name") or profile.get("email") or "Usuário",
        "email": profile.get("email") or "",
        "role": role,
    }
    return RedirectResponse(url=next_path, status_code=303)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    redirect = _redirect_se_nao_autenticado(request)
    if redirect:
        return redirect

    redirect_localidade = _redirect_se_localidade_nao_definida(request, _publico=False)
    if redirect_localidade:
        return redirect_localidade

    user = _usuario_atual(request)
    user_name = escape(user.get("name") or "Usuário")
    acesso_negado = request.query_params.get("acesso") == "negado"
    aviso_acesso_html = (
        '<div style="background:#fee2e2;color:#991b1b;padding:10px 16px;border-radius:8px;margin-bottom:16px;">'
        'Acesso restrito. Você não tem permissão para acessar essa área.</div>'
    ) if acesso_negado else ""
    is_admin = _eh_admin_ou_super_admin(user)
    is_super_admin = _eh_super_admin(user)

    db: Session = SessionLocal()
    try:
        estados = db.query(Estado).order_by(Estado.nome).all()
        municipios = db.query(Municipio).join(Estado).order_by(Estado.nome, Municipio.nome).all()
    finally:
        db.close()

    estado_sel, municipio_sel = _obter_localidade_sessao(request, _publico=False)
    label_loc = _label_localidade(estados, municipios, estado_sel, municipio_sel)
    estados_options = "".join(
        [
            f'<option value="{e.id}" {"selected" if e.id == estado_sel else ""}>{escape(_rotulo_estado(e))}</option>'
            for e in estados
        ]
    )
    municipios_options = "".join(
        [
            f'<option value="{m.id}" data-estado-id="{m.estado_id}" {"selected" if m.id == municipio_sel else ""}>{escape(m.nome)}</option>'
            for m in municipios
        ]
    )

    return f"""
    <html>
    <head>
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <style>
                @media (max-width: 768px) {{
                    html {{ font-size: 16px; }}
                    body {{ padding: 12px !important; }}
                    input, select, textarea, button, .btn, a.btn {{
                        font-size: 16px !important;
                        min-height: 44px;
                            }}
                    table {{
                        display: block;
                        width: 100%;
                        overflow-x: auto;
                        -webkit-overflow-scrolling: touch;
                        white-space: nowrap;
                            }}
                        }}
            </style>
        <title>Eventos - {escape(label_loc)}</title>
        <style>
            body {{ font-family: Arial, sans-serif; background: #f8f9fb; margin: 0; padding: 0; }}
            .page {{ max-width: 900px; margin: 40px auto; padding: 30px; background: white; border-radius: 12px; box-shadow: 0 16px 48px rgba(0,0,0,0.08); }}
            .top {{ display: flex; align-items: center; justify-content: space-between; gap: 10px; }}
            .logout {{ text-decoration: none; background: #1f2937; color: #fff; padding: 8px 12px; border-radius: 8px; font-weight: 700; }}
            .user {{ color: #374151; font-size: 14px; margin-right: auto; margin-left: 12px; }}
            h1 {{ margin-top: 0; color: #1f2937; }}
            p {{ color: #4b5563; font-size: 16px; line-height: 1.6; }}
            .menu {{ display: flex; flex-wrap: wrap; gap: 16px; margin-top: 30px; }}
            .card {{ flex: 1 1 250px; min-width: 220px; padding: 24px; border-radius: 14px; background: #eef2ff; color: #1f2937; text-decoration: none; box-shadow: 0 8px 24px rgba(15,23,42,0.08); transition: transform 0.2s ease, box-shadow 0.2s ease; }}
            .card:hover {{ transform: translateY(-3px); box-shadow: 0 16px 32px rgba(15,23,42,0.16); }}
            .card h2 {{ margin: 0 0 10px; font-size: 22px; }}
            .card p {{ margin: 0; color: #374151; }}
            .footer {{ margin-top: 32px; font-size: 14px; color: #6b7280; }}
            .localidade-form {{ margin-top: 14px; display: grid; grid-template-columns: 1fr 1fr auto; gap: 10px; align-items: end; }}
            .localidade-form label {{ display: block; font-size: 12px; color: #374151; margin-bottom: 4px; font-weight: 700; }}
            .localidade-form select {{ width: 100%; padding: 8px; border: 1px solid #d1d5db; border-radius: 8px; }}
            .localidade-form button {{ border: none; border-radius: 8px; background: #0f766e; color: #fff; padding: 9px 12px; font-weight: 700; cursor: pointer; }}
        </style>
    </head>
    <body>
        <div class="page">
            <div class="top">
                <h1>Eventos - {escape(label_loc)}</h1>
                <span class="user">Conectado como: {user_name}</span>
                <a class="logout" href="/logout">Sair</a>
            </div>
            <form class="localidade-form" method="post" action="/localidade">
                <input type="hidden" name="next" value="/" />
                <div>
                    <label for="estado_id">Estado atual</label>
                    <select id="estado_id" name="estado_id" onchange="filtrarMunicipios('estado_id','municipio_id')" required>
                        {estados_options}
                    </select>
                </div>
                <div>
                    <label for="municipio_id">Município atual</label>
                    <select id="municipio_id" name="municipio_id" required>
                        {municipios_options}
                    </select>
                </div>
                <button type="submit">Mudar localidade</button>
            </form>
            <p>Bem-vindo ao painel de eventos de {escape(label_loc)}. Use os menus abaixo para visualizar o mapa interativo dos eventos ou o calendário de programação.</p>
            {aviso_acesso_html}
            <div class="menu">
                <a class="card" href="/mapa">
                    <h2>Mapa de Eventos</h2>
                    <p>Visualize a localização de cada evento no mapa de {escape(label_loc)} com cores por região.</p>
                </a>
                <a class="card" href="/mapa-locais">
                    <h2>Mapa de Locais</h2>
                    <p>Veja no mapa todos os locais de evento cadastrados, organizados por região.</p>
                </a>
                <a class="card" href="/calendario">
                    <h2>Calendário de Eventos</h2>
                    <p>Veja os eventos organizados por local e mês em um calendário compacto e colorido.</p>
                </a>
                {'<a class="card" href="/usuarios"><h2>Usuários</h2><p>Atualize seu cadastro completo e gerencie os usuários da plataforma.</p></a>' if is_admin else ''}
                {'<a class="card" href="/board-interacoes"><h2>Board de Interações</h2><p>Acompanhe cliques de visualização e acesso por dia, mês e ano.</p></a>' if is_admin else ''}
                {'<a class="card" href="/anunciantes"><h2>Anunciantes</h2><p>Gerencie os anunciantes cadastrados com suas informações de localização e imagens.</p></a>' if is_super_admin else ''}
                {'<a class="card" href="/configuracoes"><h2>Configurações</h2><p>Altere parâmetros globais de exibição, como logo e URL.</p></a>' if is_super_admin else ''}
                {'<a class="card" href="/estados"><h2>Cadastro de Estados</h2><p>Cadastre estados para habilitar novas localidades de visualização.</p></a>' if is_admin else ''}
                {'<a class="card" href="/municipios"><h2>Cadastro de Municípios</h2><p>Cadastre municípios vinculados aos estados disponíveis.</p></a>' if is_admin else ''}
                {'<a class="card" href="/cadastro"><h2>Cadastrar Evento/Local</h2><p>Inclua novos locais de execução e novos eventos diretamente pela tela.</p></a>' if is_admin else ''}
                {'<a class="card" href="/manutencao"><h2>Manutenção</h2><p>Edite ou exclua locais e eventos já cadastrados em uma tela dedicada.</p></a>' if is_admin else ''}
            </div>
            <div class="footer">Acesse o mapa ou o calendário para explorar os eventos cadastrados. Versão atual: {APP_VERSION}</div>
        </div>
        <script>
            function filtrarMunicipios(estadoSelectId, municipioSelectId) {{
                const estado = document.getElementById(estadoSelectId);
                const municipio = document.getElementById(municipioSelectId);
                if (!municipio) return;

                if (!municipio._allOptions) {{
                    municipio._allOptions = Array.from(municipio.options).map((opt) => ({{
                        value: opt.value,
                        text: opt.text,
                        dono: opt.getAttribute('data-estado-id') || ''
                    }}));
                }}

                const estadoId = estado ? estado.value : '';
                const valorAtual = municipio.value;
                const opcoesFiltradas = municipio._allOptions.filter((opt) => !estadoId || !opt.dono || opt.dono === estadoId);

                municipio.innerHTML = '';
                opcoesFiltradas.forEach((opt) => {{
                    const optionEl = document.createElement('option');
                    optionEl.value = opt.value;
                    optionEl.text = opt.text;
                    if (opt.dono) {{
                        optionEl.setAttribute('data-estado-id', opt.dono);
                    }}
                    municipio.appendChild(optionEl);
                }});

                const aindaExiste = opcoesFiltradas.some((opt) => opt.value === valorAtual);
                if (aindaExiste) {{
                    municipio.value = valorAtual;
                }} else if (municipio.options.length) {{
                    municipio.selectedIndex = 0;
                }}
            }}
            filtrarMunicipios('estado_id','municipio_id');
        </script>
    </body>
    </html>
    """


@app.get("/version")
def version():
    return {"app": "mapaCalorEventos", "version": APP_VERSION}


def _rotulo_estado(estado: Estado) -> str:
    sigla = (estado.sigla or "").strip()
    if sigla:
        return f"{estado.nome} ({sigla})"
    return estado.nome


def _label_localidade(
    estados: list,
    municipios: list,
    estado_id: Optional[int],
    municipio_id: Optional[int],
) -> str:
    """Retorna 'Município - UF' (ou nome do estado) com base na localidade selecionada."""
    municipio_nome = None
    estado_sigla = None
    for m in municipios:
        if m.id == municipio_id:
            municipio_nome = m.nome
            break
    for e in estados:
        if e.id == estado_id:
            estado_sigla = (e.sigla or "").strip() or e.nome
            break
    if municipio_nome and estado_sigla:
        return f"{municipio_nome} - {estado_sigla}"
    if municipio_nome:
        return municipio_nome
    if estado_sigla:
        return estado_sigla
    return "localidade"


def _render_pagina_localidade(request: Request, _publico: bool = False, msg: str = "") -> str:
    db: Session = SessionLocal()
    try:
        estados = db.query(Estado).order_by(Estado.nome).all()
        municipios = db.query(Municipio).join(Estado).order_by(Estado.nome, Municipio.nome).all()
    finally:
        db.close()

    estado_sel, municipio_sel = _obter_localidade_sessao(request, _publico=_publico)

    estados_options = "".join(
        [
            f'<option value="{e.id}" {"selected" if e.id == estado_sel else ""}>{escape(_rotulo_estado(e))}</option>'
            for e in estados
        ]
    )
    municipios_options = "".join(
        [
            f'<option value="{m.id}" data-estado-id="{m.estado_id}" {"selected" if m.id == municipio_sel else ""}>{escape(m.nome)}</option>'
            for m in municipios
        ]
    )

    acao = "/public/localidade" if _publico else "/localidade"
    destino_padrao = "/public/visualizacao" if _publico else "/"
    titulo = "Selecionar Localidade (Usuário Final)" if _publico else "Selecionar Localidade"
    msg_html = f'<div class="msg">{escape(msg)}</div>' if msg else ""

    return f"""
    <html>
    <head>
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
        <title>{escape(titulo)}</title>
        <style>
            body {{ font-family: Arial, sans-serif; background: #f3f4f6; margin: 0; padding: 24px; }}
            .card {{ max-width: 680px; margin: 40px auto; background: #fff; border-radius: 12px; padding: 24px; box-shadow: 0 14px 32px rgba(0,0,0,0.08); }}
            h1 {{ margin-top: 0; color: #111827; }}
            p {{ color: #4b5563; }}
            label {{ display: block; font-weight: 700; margin: 12px 0 6px; }}
            select {{ width: 100%; padding: 10px; border-radius: 8px; border: 1px solid #d1d5db; }}
            button {{ margin-top: 16px; border: none; border-radius: 8px; padding: 10px 14px; background: #0f766e; color: #fff; font-weight: 700; cursor: pointer; }}
            .msg {{ background: #e0f2fe; color: #075985; border-radius: 8px; padding: 10px; margin: 10px 0; }}
        </style>
    </head>
    <body>
        <div class=\"card\">
            <h1>{escape(titulo)}</h1>
            <p>Escolha o estado e o município para visualizar os dados do mapa e do calendário.</p>
            {msg_html}
            <form method=\"post\" action=\"{acao}\">
                <input type=\"hidden\" name=\"next\" value=\"{destino_padrao}\" />
                <label for=\"estado_id\">Estado</label>
                <select id=\"estado_id\" name=\"estado_id\" onchange=\"filtrarMunicipios('estado_id','municipio_id')\" required>
                    <option value=\"\">Selecione...</option>
                    {estados_options}
                </select>

                <label for=\"municipio_id\">Município</label>
                <select id=\"municipio_id\" name=\"municipio_id\" required>
                    <option value=\"\">Selecione...</option>
                    {municipios_options}
                </select>

                <button type=\"submit\">Aplicar localidade</button>
            </form>
        </div>
        <script>
            function filtrarMunicipios(estadoSelectId, municipioSelectId) {{
                const estado = document.getElementById(estadoSelectId);
                const municipio = document.getElementById(municipioSelectId);
                if (!municipio) return;

                if (!municipio._allOptions) {{
                    municipio._allOptions = Array.from(municipio.options).map((opt) => ({{
                        value: opt.value,
                        text: opt.text,
                        dono: opt.getAttribute('data-estado-id') || ''
                    }}));
                }}

                const estadoId = estado ? estado.value : '';
                const valorAtual = municipio.value;
                const opcoesFiltradas = municipio._allOptions.filter((opt) => !estadoId || !opt.dono || opt.dono === estadoId);

                municipio.innerHTML = '';
                opcoesFiltradas.forEach((opt) => {{
                    const optionEl = document.createElement('option');
                    optionEl.value = opt.value;
                    optionEl.text = opt.text;
                    if (opt.dono) {{
                        optionEl.setAttribute('data-estado-id', opt.dono);
                    }}
                    municipio.appendChild(optionEl);
                }});

                const aindaExiste = opcoesFiltradas.some((opt) => opt.value === valorAtual);
                if (aindaExiste) {{
                    municipio.value = valorAtual;
                }} else if (municipio.options.length) {{
                    municipio.selectedIndex = 0;
                }}
            }}
            filtrarMunicipios('estado_id', 'municipio_id');
        </script>
    </body>
    </html>
    """


@app.get("/localidade", response_class=HTMLResponse)
def selecionar_localidade(request: Request):
    redirect = _redirect_se_nao_autenticado(request)
    if redirect:
        return redirect
    return _render_pagina_localidade(request, _publico=False)


@app.post("/localidade")
def salvar_localidade(
    request: Request,
    estado_id: int = Form(...),
    municipio_id: int = Form(...),
    next: str = Form("/"),
):
    redirect = _redirect_se_nao_autenticado(request)
    if redirect:
        return redirect

    db: Session = SessionLocal()
    try:
        if not _localidade_valida(db, estado_id, municipio_id):
            return HTMLResponse(_render_pagina_localidade(request, _publico=False, msg="Seleção inválida."), status_code=400)
    finally:
        db.close()

    _definir_localidade_sessao(request, estado_id, municipio_id, _publico=False)
    return RedirectResponse(url=next or "/", status_code=303)


@app.get("/public/localidade", response_class=HTMLResponse)
def selecionar_localidade_publica(request: Request):
    return _render_pagina_localidade(request, _publico=True)


@app.post("/public/localidade")
def salvar_localidade_publica(
    request: Request,
    estado_id: int = Form(...),
    municipio_id: int = Form(...),
    next: str = Form("/public/visualizacao"),
):
    db: Session = SessionLocal()
    try:
        if not _localidade_valida(db, estado_id, municipio_id):
            return HTMLResponse(_render_pagina_localidade(request, _publico=True, msg="Seleção inválida."), status_code=400)
    finally:
        db.close()

    _definir_localidade_sessao(request, estado_id, municipio_id, _publico=True)
    return RedirectResponse(url=next or "/public/visualizacao", status_code=303)


@app.get("/estados", response_class=HTMLResponse)
def pagina_estados(request: Request):
    redirect = _redirect_se_nao_admin(request)
    if redirect:
        return redirect

    db: Session = SessionLocal()
    try:
        estados = db.query(Estado).order_by(Estado.nome).all()
    finally:
        db.close()

    lista = "".join([f"<li>{escape(_rotulo_estado(e))}</li>" for e in estados]) or "<li>Nenhum estado cadastrado.</li>"

    return f"""
    <html><head><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" /><title>Cadastro de Estados</title>
    <style>body{{font-family:Arial,sans-serif;background:#f3f4f6;padding:24px}}.card{{max-width:760px;margin:20px auto;background:#fff;padding:20px;border-radius:12px}}input{{width:100%;padding:10px;margin-bottom:10px}}button{{padding:10px 14px;background:#0f766e;color:#fff;border:none;border-radius:8px}}a{{color:#2563eb}}</style>
    </head><body><div class=\"card\"><h1>Cadastro de Estados</h1><p>{botao_voltar_portal_html()}</p>
    <form method=\"post\" action=\"/estados\"><label>Nome do estado</label><input name=\"nome\" required />
    <label>Sigla</label><input name=\"sigla\" maxlength=\"2\" /><button type=\"submit\">Cadastrar estado</button></form>
    <h2>Estados cadastrados</h2><ul>{lista}</ul></div></body></html>
    """


@app.post("/estados")
def cadastrar_estado(request: Request, nome: str = Form(...), sigla: str = Form("")):
    redirect = _redirect_se_nao_admin(request)
    if redirect:
        return redirect

    nome_limpo = (nome or "").strip()
    if not nome_limpo:
        return RedirectResponse(url="/estados", status_code=303)

    db: Session = SessionLocal()
    try:
        existe = db.query(Estado).filter(Estado.nome == nome_limpo).first()
        if not existe:
            db.add(Estado(nome=nome_limpo, sigla=(sigla or "").strip().upper()))
            db.commit()
    finally:
        db.close()

    return RedirectResponse(url="/estados", status_code=303)


@app.get("/municipios", response_class=HTMLResponse)
def pagina_municipios(request: Request):
    redirect = _redirect_se_nao_admin(request)
    if redirect:
        return redirect

    db: Session = SessionLocal()
    try:
        estados = db.query(Estado).order_by(Estado.nome).all()
        municipios = (
            db.query(Municipio, Estado)
            .join(Estado, Municipio.estado_id == Estado.id)
            .order_by(Estado.nome, Municipio.nome)
            .all()
        )

        estados_opts = "".join(
            [f'<option value="{e.id}">{escape(_rotulo_estado(e))}</option>' for e in estados]
        )
        lista = (
            "".join(
                [
                    f"<li>{escape(municipio.nome)} - {escape(_rotulo_estado(estado))}</li>"
                    for municipio, estado in municipios
                ]
            )
            or "<li>Nenhum município cadastrado.</li>"
        )
    finally:
        db.close()

    return f"""
    <html><head><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" /><title>Cadastro de Municípios</title>
    <style>body{{font-family:Arial,sans-serif;background:#f3f4f6;padding:24px}}.card{{max-width:760px;margin:20px auto;background:#fff;padding:20px;border-radius:12px}}input,select{{width:100%;padding:10px;margin-bottom:10px}}button{{padding:10px 14px;background:#0f766e;color:#fff;border:none;border-radius:8px}}a{{color:#2563eb}}</style>
    </head><body><div class=\"card\"><h1>Cadastro de Municípios</h1><p>{botao_voltar_portal_html()}</p>
    <form method=\"post\" action=\"/municipios\"><label>Estado</label><select name=\"estado_id\" required>{estados_opts}</select>
    <label>Município</label><input name=\"nome\" required /><button type=\"submit\">Cadastrar município</button></form>
    <h2>Municípios cadastrados</h2><ul>{lista}</ul></div></body></html>
    """


@app.post("/municipios")
def cadastrar_municipio(request: Request, estado_id: int = Form(...), nome: str = Form(...)):
    redirect = _redirect_se_nao_admin(request)
    if redirect:
        return redirect

    nome_limpo = (nome or "").strip()
    if not nome_limpo:
        return RedirectResponse(url="/municipios", status_code=303)

    db: Session = SessionLocal()
    try:
        estado = db.query(Estado).filter(Estado.id == estado_id).first()
        if not estado:
            return RedirectResponse(url="/municipios", status_code=303)

        existe = db.query(Municipio).filter(Municipio.nome == nome_limpo, Municipio.estado_id == estado_id).first()
        if not existe:
            db.add(Municipio(nome=nome_limpo, estado_id=estado_id))
            db.commit()
    finally:
        db.close()

    return RedirectResponse(url="/municipios", status_code=303)


@app.get("/usuarios", response_class=HTMLResponse)
def usuarios_page(request: Request, msg: Optional[str] = None):
    redirect = _redirect_se_nao_admin(request)
    if redirect:
        return redirect

    user = _usuario_atual(request)
    user_role = (user.get("role") or "").lower()

    db: Session = SessionLocal()
    try:
        usuario_local = None
        usuario_id = user.get("id") or ""
        if str(usuario_id).isdigit() and (user.get("provider") == "local"):
            usuario_local = db.query(Usuario).filter(Usuario.id == int(usuario_id)).first()

        msg_html = ""
        if msg == "ok":
            msg_html = '<div class="msg ok">Perfil atualizado com sucesso.</div>'
        elif msg == "erro":
            msg_html = '<div class="msg erro">Não foi possível atualizar o perfil.</div>'
        elif msg == "somente_local":
            msg_html = '<div class="msg erro">Este perfil social não pode ser editado aqui. Use um login local para atualizar os dados.</div>'
        elif msg == "email_ou_cpf_duplicado":
            msg_html = '<div class="msg erro">Email ou CPF já cadastrado para outro usuário.</div>'

        nome_valor = escape((usuario_local.nome if usuario_local else user.get("name") or ""))
        email_valor = escape((usuario_local.email if usuario_local else user.get("email") or ""))
        cpf_valor = escape((usuario_local.cpf if usuario_local else user.get("cpf") or ""))
        telefone_valor = escape((usuario_local.telefone if usuario_local else "") or "")
        endereco_valor = escape((usuario_local.endereco if usuario_local else "") or "")
        foto_url_valor = escape((usuario_local.foto_url if usuario_local else "") or "")

        usuarios_html = ""
        if _eh_super_admin(user):
            usuarios = db.query(Usuario).order_by(Usuario.nome).all()
            for u in usuarios:
                usuarios_html += (
                    f"<tr><td>{u.id}</td><td>{escape(u.nome or '')}</td><td>{escape(u.email or '')}</td>"
                    f"<td>{escape(u.cpf or '')}</td><td>{escape(u.role or '')}</td></tr>"
                )

        bloco_lista = ""
        if usuarios_html:
            bloco_lista = f"""
            <h2>Usuários cadastrados</h2>
            <table>
                <tr><th>ID</th><th>Nome</th><th>Email</th><th>CPF</th><th>Perfil</th></tr>
                {usuarios_html}
            </table>
            """

        return f"""
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <style>
                @media (max-width: 768px) {{
                    html {{ font-size: 16px; }}
                    body {{ padding: 12px !important; }}
                    input, select, textarea, button, .btn, a.btn {{
                        font-size: 16px !important;
                        min-height: 44px;
                            }}
                    table {{
                        display: block;
                        width: 100%;
                        overflow-x: auto;
                        -webkit-overflow-scrolling: touch;
                        white-space: nowrap;
                            }}
                        }}
            </style>
            <title>Usuários - Eventos</title>
            <style>
                body {{ font-family: Arial, sans-serif; background: #f8f9fb; margin: 0; padding: 24px; }}
                .page {{ max-width: 980px; margin: 0 auto; background: #fff; border-radius: 12px; padding: 24px; box-shadow: 0 14px 36px rgba(0,0,0,.08); }}
                h1 {{ margin-top: 0; color: #1f2937; }}
                .desc {{ color: #4b5563; margin-bottom: 16px; }}
                .role {{ display: inline-block; background: #e0f2fe; color: #0c4a6e; font-weight: 700; border-radius: 999px; padding: 4px 10px; font-size: 12px; }}
                .msg {{ border-radius: 8px; padding: 10px 12px; margin-bottom: 14px; font-size: 14px; }}
                .ok {{ background: #dcfce7; color: #166534; }}
                .erro {{ background: #fee2e2; color: #991b1b; }}
                .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
                label {{ display: block; margin: 10px 0 6px; font-weight: 700; color: #111827; }}
                input {{ width: 100%; border: 1px solid #d1d5db; border-radius: 8px; padding: 10px 12px; box-sizing: border-box; }}
                .actions {{ margin-top: 16px; display: flex; gap: 10px; }}
                .btn {{ border: none; border-radius: 8px; padding: 10px 14px; font-weight: 700; cursor: pointer; text-decoration: none; display: inline-block; }}
                .btn-primary {{ background: #1f2937; color: #fff; }}
                .btn-secondary {{ background: #e5e7eb; color: #111827; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 18px; }}
                th, td {{ border: 1px solid #e5e7eb; padding: 8px; text-align: left; font-size: 14px; }}
                th {{ background: #f3f4f6; }}
                @media (max-width: 760px) {{ .grid {{ grid-template-columns: 1fr; }} }}
            </style>
        </head>
        <body>
            <div class="page">
                <h1>Usuários</h1>
                <div class="desc">Atualize seu cadastro completo. Perfis criados no cadastro rápido entram como administrador.</div>
                <div class="role">Perfil atual: {escape(user_role or 'user')}</div>
                {msg_html}
                <form method="post" action="/usuarios/perfil">
                    <div class="grid">
                        <div>
                            <label for="nome">Nome</label>
                            <input id="nome" name="nome" value="{nome_valor}" required />
                        </div>
                        <div>
                            <label for="email">Email</label>
                            <input id="email" name="email" type="email" value="{email_valor}" required />
                        </div>
                        <div>
                            <label for="cpf">CPF</label>
                            <input id="cpf" name="cpf" value="{cpf_valor}" required />
                        </div>
                        <div>
                            <label for="telefone">Telefone</label>
                            <input id="telefone" name="telefone" value="{telefone_valor}" />
                        </div>
                        <div>
                            <label for="endereco">Endereço</label>
                            <input id="endereco" name="endereco" value="{endereco_valor}" />
                        </div>
                        <div>
                            <label for="foto_url">URL da foto</label>
                            <input id="foto_url" name="foto_url" value="{foto_url_valor}" />
                        </div>
                        <div>
                            <label for="senha">Nova senha (opcional)</label>
                            <input id="senha" name="senha" type="password" minlength="6" />
                        </div>
                    </div>
                    <div class="actions">
                        <button class="btn btn-primary" type="submit">Salvar perfil</button>
                        {botao_voltar_portal_html()}
                    </div>
                </form>
                {bloco_lista}
            </div>
        </body>
        </html>
        """
    finally:
        db.close()


@app.post("/usuarios/perfil")
def salvar_perfil_usuario(
    request: Request,
    nome: str = Form(...),
    email: str = Form(...),
    cpf: str = Form(...),
    telefone: str = Form(""),
    endereco: str = Form(""),
    foto_url: str = Form(""),
    senha: str = Form(""),
):
    redirect = _redirect_se_nao_admin(request)
    if redirect:
        return redirect

    user = _usuario_atual(request)
    if user.get("provider") != "local" or not str(user.get("id") or "").isdigit():
        return RedirectResponse(url="/usuarios?msg=somente_local", status_code=303)

    nome_limpo = (nome or "").strip()
    email_limpo = (email or "").strip().lower()
    cpf_limpo = _normalizar_cpf(cpf)

    if not nome_limpo or not email_limpo or len(cpf_limpo) != 11:
        return RedirectResponse(url="/usuarios?msg=erro", status_code=303)

    db: Session = SessionLocal()
    try:
        usuario = db.query(Usuario).filter(Usuario.id == int(user["id"])).first()
        if not usuario:
            return RedirectResponse(url="/usuarios?msg=erro", status_code=303)

        duplicado = db.query(Usuario).filter(
            ((Usuario.email == email_limpo) | (Usuario.cpf == cpf_limpo)) & (Usuario.id != usuario.id)
        ).first()
        if duplicado:
            return RedirectResponse(url="/usuarios?msg=email_ou_cpf_duplicado", status_code=303)

        usuario.nome = nome_limpo
        usuario.email = email_limpo
        usuario.cpf = cpf_limpo
        usuario.telefone = (telefone or "").strip()
        usuario.endereco = (endereco or "").strip()
        usuario.foto_url = (foto_url or "").strip()
        if (senha or "").strip():
            usuario.senha_hash = _hash_senha(senha)

        db.commit()
        request.session["user"] = _usuario_para_sessao(usuario)
        return RedirectResponse(url="/usuarios?msg=ok", status_code=303)
    except Exception:
        db.rollback()
        return RedirectResponse(url="/usuarios?msg=erro", status_code=303)
    finally:
        db.close()


def render_tela_cadastro_manutencao(
    msg: Optional[str],
    modo: str,
    busca_local: str = "",
    busca_evento: str = "",
    pagina_local: int = 1,
    pagina_evento: int = 1,
    por_pagina: int = 5,
):
    db: Session = SessionLocal()
    try:
        locais_todos = db.query(Local).order_by(Local.nome).all()
        regionais = db.query(Regional).order_by(Regional.nome).all()
        estados = db.query(Estado).order_by(Estado.nome).all()
        municipios = db.query(Municipio).join(Estado).order_by(Estado.nome, Municipio.nome).all()

        is_cadastro = modo == "cadastro"

        if pagina_local < 1:
            pagina_local = 1
        if pagina_evento < 1:
            pagina_evento = 1
        if por_pagina < 1:
            por_pagina = 5

        busca_local = (busca_local or "").strip()
        busca_evento = (busca_evento or "").strip()

        query_locais = db.query(Local)
        if busca_local:
            termo_local = f"%{busca_local}%"
            query_locais = query_locais.filter(
                (Local.nome.ilike(termo_local))
                | (Local.endereco.ilike(termo_local))
                | (Local.regiao.ilike(termo_local))
                | (Local.tipo_evento.ilike(termo_local))
            )
        total_locais = query_locais.count()
        total_paginas_local = max(1, (total_locais + por_pagina - 1) // por_pagina)
        if pagina_local > total_paginas_local:
            pagina_local = total_paginas_local
        locais = (
            query_locais.order_by(Local.nome)
            .offset((pagina_local - 1) * por_pagina)
            .limit(por_pagina)
            .all()
        )

        query_eventos = db.query(Evento).join(Local)
        if busca_evento:
            termo_evento = f"%{busca_evento}%"
            query_eventos = query_eventos.filter(
                (Evento.nome.ilike(termo_evento))
                | (Evento.descricao.ilike(termo_evento))
                | (Evento.porte.ilike(termo_evento))
                | (Evento.tipo_evento.ilike(termo_evento))
                | (Local.nome.ilike(termo_evento))
            )
        total_eventos = query_eventos.count()
        total_paginas_evento = max(1, (total_eventos + por_pagina - 1) // por_pagina)
        if pagina_evento > total_paginas_evento:
            pagina_evento = total_paginas_evento
        eventos = (
            query_eventos.order_by(Evento.data_inicio.desc())
            .offset((pagina_evento - 1) * por_pagina)
            .limit(por_pagina)
            .all()
        )

        msg_html = ""
        if msg == "local_ok":
            msg_html = '<div class="msg ok">Local cadastrado com sucesso.</div>'
        elif msg == "local_ok_sem_coordenadas":
            msg_html = '<div class="msg aviso">Local cadastrado, mas o endereço não foi localizado. Coordenadas pendentes.</div>'
        elif msg == "evento_ok":
            msg_html = '<div class="msg ok">Evento cadastrado com sucesso.</div>'
        elif msg == "local_edit_ok":
            msg_html = '<div class="msg ok">Local atualizado com sucesso.</div>'
        elif msg == "local_edit_ok_sem_coordenadas":
            msg_html = '<div class="msg aviso">Local atualizado, mas o endereço não foi localizado. Coordenadas pendentes.</div>'
        elif msg == "evento_edit_ok":
            msg_html = '<div class="msg ok">Evento atualizado com sucesso.</div>'
        elif msg == "local_delete_ok":
            msg_html = '<div class="msg ok">Local excluído com sucesso.</div>'
        elif msg == "evento_delete_ok":
            msg_html = '<div class="msg ok">Evento excluído com sucesso.</div>'
        elif msg == "data_invalida":
            msg_html = '<div class="msg erro">Data inválida. Use o formato correto da tela.</div>'
        elif msg == "periodo_invalido":
            msg_html = '<div class="msg erro">A data final não pode ser menor que a data inicial.</div>'
        elif msg == "local_invalido":
            msg_html = '<div class="msg erro">Selecione um local válido para o evento.</div>'
        elif msg == "endereco_nao_localizado":
            msg_html = '<div class="msg erro">Não foi possível localizar o endereço informado para preencher latitude e longitude.</div>'
        elif msg == "registro_nao_encontrado":
            msg_html = '<div class="msg erro">Registro não encontrado.</div>'

        locais_options = "".join(
            [f'<option value="{local.id}">{local.nome} ({local.regiao})</option>' for local in locais_todos]
        )
        estados_options_base = "".join(
            [f'<option value="{estado.id}">{escape(_rotulo_estado(estado))}</option>' for estado in estados]
        )
        municipios_options_base = "".join(
            [f'<option value="{municipio.id}" data-estado-id="{municipio.estado_id}">{escape(municipio.nome)} - {escape(_rotulo_estado(municipio.estado))}</option>' for municipio in municipios]
        )

        locais_existentes_html = ""
        for local in locais:
            local_nome = escape(local.nome or "")
            local_endereco = escape(local.endereco or "")
            local_regiao = escape(local.regiao or "")
            local_sem_coordenadas = not coordenadas_validas(local.latitude, local.longitude)
            local_estado_id = local.municipio.estado_id if local.municipio else None
            local_municipio_id = local.municipio_id
            local_telefone = escape(local.contato_telefone or "")
            local_site = escape(local.site_url or "")
            local_tipo_evento = normalizar_tipo_evento(local.tipo_evento)
            local_acessibilidade_checked = "checked" if bool(local.acessibilidade) else ""
            local_proximo_metro_checked = "checked" if bool(local.proximo_metro) else ""
            local_restaurantes_checked = "checked" if bool(local.restaurantes) else ""
            local_warning_class = " warning-coords" if local_sem_coordenadas else ""
            local_warning_html = '<small class="coord-warning">Coordenadas pendentes</small>' if local_sem_coordenadas else ""
            locais_existentes_html += f"""
            <div class="item-row{local_warning_class}">
                <div class="item-name">{local_nome} <small>({escape(local_tipo_evento)})</small> {local_warning_html}</div>
                <div class="item-actions">
                    <button class="btn-secondary" type="button" onclick="openModal('local-modal-{local.id}')">Editar</button>
                    <form method="post" action="/cadastro/local/{local.id}/excluir" onsubmit="return confirm('Excluir local e eventos vinculados?');">
                        <button class="btn-danger" type="submit">Excluir</button>
                    </form>
                </div>
            </div>
            <div id="local-modal-{local.id}" class="modal-overlay" onclick="closeModalOnOverlay(event, 'local-modal-{local.id}')">
                <div class="modal-card">
                    <h3>Editar Local</h3>
                    <form method="post" action="/cadastro/local/{local.id}/editar">
                        <label>Nome</label>
                        <input name="nome" value="{local_nome}" required />

                        <label>Endereço</label>
                        <input name="endereco" value="{local_endereco}" required />

                        <label>Região</label>
                        <select name="regiao" required>
                            {"".join([f'<option value="{r.nome}" {"selected" if r.nome == local_regiao else ""}>{r.nome}</option>' for r in regionais])}
                        </select>

                        <label>Estado</label>
                        <select id="edit_estado_{local.id}" name="estado_id" onchange="filtrarMunicipios('edit_estado_{local.id}','edit_municipio_{local.id}')" required>
                            {"".join([f'<option value="{estado.id}" {"selected" if estado.id == local_estado_id else ""}>{escape(_rotulo_estado(estado))}</option>' for estado in estados])}
                        </select>

                        <label>Município</label>
                        <select id="edit_municipio_{local.id}" name="municipio_id" required>
                            {"".join([f'<option value="{municipio.id}" data-estado-id="{municipio.estado_id}" {"selected" if municipio.id == local_municipio_id else ""}>{escape(municipio.nome)} - {escape(_rotulo_estado(municipio.estado))}</option>' for municipio in municipios])}
                        </select>

                        <label>Tipo de evento</label>
                        <select name="tipo_evento" required>
                            {"".join([f'<option value="{tipo}" {"selected" if tipo == local_tipo_evento else ""}>{tipo}</option>' for tipo in TIPOS_EVENTO])}
                        </select>

                        <label>Latitude</label>
                        <input type="number" step="any" name="latitude" value="{local.latitude}" readonly />

                        <label>Longitude</label>
                        <input type="number" step="any" name="longitude" value="{local.longitude}" readonly />

                        <label>Telefone de contato</label>
                        <input name="contato_telefone" value="{local_telefone}" />

                        <label>Site</label>
                        <input name="site_url" value="{local_site}" placeholder="https://..." />

                        <div class="check-row">
                            <label class="check-label">
                                <input type="checkbox" name="acessibilidade" value="1" {local_acessibilidade_checked} />
                                Possui acessibilidade
                            </label>
                            <label class="check-label">
                                <input type="checkbox" name="proximo_metro" value="1" {local_proximo_metro_checked} />
                                Próximo do metrô
                            </label>
                            <label class="check-label">
                                <input type="checkbox" name="restaurantes" value="1" {local_restaurantes_checked} />
                                Possui restaurantes
                            </label>
                        </div>

                        <div class="modal-actions">
                            <button type="submit">Salvar</button>
                            <button class="btn-secondary" type="button" onclick="closeModal('local-modal-{local.id}')">Cancelar</button>
                        </div>
                    </form>
                </div>
            </div>
            """

        eventos_existentes_html = ""
        for evento in eventos:
            evento_nome = escape(evento.nome or "")
            evento_descricao = escape(evento.descricao or "")
            evento_porte = escape(evento.porte or "")
            evento_telefone = escape(evento.contato_telefone or "")
            evento_site = escape(evento.site_url or "")
            evento_tipo_evento = normalizar_tipo_evento(evento.tipo_evento)
            evento_options = "".join(
                [
                    f'<option value="{local.id}" {"selected" if local.id == evento.local_id else ""}>{local.nome} ({local.regiao})</option>'
                    for local in locais_todos
                ]
            )
            eventos_existentes_html += f"""
            <div class="item-row">
                <div class="item-name">{evento_nome} <small>({escape(evento_tipo_evento)})</small></div>
                <div class="item-actions">
                    <button class="btn-secondary" type="button" onclick="openModal('evento-modal-{evento.id}')">Editar</button>
                    <form method="post" action="/cadastro/evento/{evento.id}/excluir" onsubmit="return confirm('Excluir evento?');">
                        <button class="btn-danger" type="submit">Excluir</button>
                    </form>
                </div>
            </div>
            <div id="evento-modal-{evento.id}" class="modal-overlay" onclick="closeModalOnOverlay(event, 'evento-modal-{evento.id}')">
                <div class="modal-card">
                    <h3>Editar Evento</h3>
                    <form method="post" action="/cadastro/evento/{evento.id}/editar">
                        <label>Nome</label>
                        <input name="nome" value="{evento_nome}" required />

                        <label>Descrição</label>
                        <textarea name="descricao" required>{evento_descricao}</textarea>

                        <label>Data de início</label>
                        <input type="date" name="data_inicio" value="{evento.data_inicio}" required />

                        <label>Data de fim</label>
                        <input type="date" name="data_fim" value="{evento.data_fim}" required />

                        <label>Público estimado</label>
                        <input type="number" name="publico_estimado" min="0" value="{evento.publico_estimado}" required />

                        <label>Porte</label>
                        <input name="porte" value="{evento_porte}" required />

                        <label>Telefone de contato</label>
                        <input name="contato_telefone" value="{evento_telefone}" />

                        <label>Site</label>
                        <input name="site_url" value="{evento_site}" placeholder="https://..." />

                        <label>Tipo de evento</label>
                        <select name="tipo_evento" required>
                            {"".join([f'<option value="{tipo}" {"selected" if tipo == evento_tipo_evento else ""}>{tipo}</option>' for tipo in TIPOS_EVENTO])}
                        </select>

                        <label>Local de execução</label>
                        <select name="local_id" required>
                            {evento_options}
                        </select>

                        <div class="modal-actions">
                            <button type="submit">Salvar</button>
                            <button class="btn-secondary" type="button" onclick="closeModal('evento-modal-{evento.id}')">Cancelar</button>
                        </div>
                    </form>
                </div>
            </div>
            """

        if not locais_existentes_html:
            locais_existentes_html = '<p class="vazio">Nenhum local cadastrado.</p>'

        if not eventos_existentes_html:
            eventos_existentes_html = '<p class="vazio">Nenhum evento cadastrado.</p>'

        paginacao_locais_html = ""
        if total_locais > 0:
            link_prev_local = ""
            link_next_local = ""
            if pagina_local > 1:
                link_prev_local = (
                    f'<a class="page-link" href="/manutencao?busca_local={busca_local}&busca_evento={busca_evento}'
                    f'&pagina_local={pagina_local - 1}&pagina_evento={pagina_evento}">Anterior</a>'
                )
            if pagina_local < total_paginas_local:
                link_next_local = (
                    f'<a class="page-link" href="/manutencao?busca_local={busca_local}&busca_evento={busca_evento}'
                    f'&pagina_local={pagina_local + 1}&pagina_evento={pagina_evento}">Próxima</a>'
                )
            paginacao_locais_html = f'''
                <div class="pagination">
                    <span>Página {pagina_local} de {total_paginas_local}</span>
                    {link_prev_local}
                    {link_next_local}
                </div>
            '''

        paginacao_eventos_html = ""
        if total_eventos > 0:
            link_prev_evento = ""
            link_next_evento = ""
            if pagina_evento > 1:
                link_prev_evento = (
                    f'<a class="page-link" href="/manutencao?busca_local={busca_local}&busca_evento={busca_evento}'
                    f'&pagina_local={pagina_local}&pagina_evento={pagina_evento - 1}">Anterior</a>'
                )
            if pagina_evento < total_paginas_evento:
                link_next_evento = (
                    f'<a class="page-link" href="/manutencao?busca_local={busca_local}&busca_evento={busca_evento}'
                    f'&pagina_local={pagina_local}&pagina_evento={pagina_evento + 1}">Próxima</a>'
                )
            paginacao_eventos_html = f'''
                <div class="pagination">
                    <span>Página {pagina_evento} de {total_paginas_evento}</span>
                    {link_prev_evento}
                    {link_next_evento}
                </div>
            '''

        busca_manutencao_html = f'''
            <div class="card list-card">
                <h2>Filtros de manutenção</h2>
                <form method="get" action="/manutencao" class="grid">
                    <div>
                        <label>Buscar locais</label>
                        <input name="busca_local" value="{busca_local}" placeholder="Nome, endereço, região ou tipo" />
                    </div>
                    <div>
                        <label>Buscar eventos</label>
                        <input name="busca_evento" value="{busca_evento}" placeholder="Nome, descrição, porte, tipo ou local" />
                    </div>
                    <div>
                        <button type="submit">Aplicar filtros</button>
                        <a class="nav-link" href="/manutencao">Limpar</a>
                    </div>
                </form>
            </div>
        '''

        titulo_pagina = "Cadastro de Eventos e Locais" if is_cadastro else "Manutenção de Eventos e Locais"
        subtitulo = (
            "Cadastre primeiro o local de execução e depois associe eventos a ele."
            if is_cadastro
            else "Edite ou exclua registros já existentes."
        )
        nav_cadastro_class = "nav-link active" if is_cadastro else "nav-link"
        nav_manutencao_class = "nav-link" if is_cadastro else "nav-link active"
        secoes_cadastro_html = ""
        secoes_manutencao_html = ""

        if is_cadastro:
            secoes_cadastro_html = f"""
                <div class="grid">
                    <div class="card">
                        <h2>Novo Local</h2>
                        <form method="post" action="/cadastro/local">
                            <label>Nome do local</label>
                            <input name="nome" required />

                            <label>Endereço</label>
                            <input name="endereco" required />

                            <label>Região</label>
                            <select name="regiao" required>
                                {"".join([f'<option value="{r.nome}">{r.nome}</option>' for r in regionais])}
                            </select>

                            <label>Estado</label>
                            <select id="cadastro_estado_id" name="estado_id" onchange="filtrarMunicipios('cadastro_estado_id','cadastro_municipio_id')" required>
                                {estados_options_base}
                            </select>

                            <label>Município</label>
                            <select id="cadastro_municipio_id" name="municipio_id" required>
                                {municipios_options_base}
                            </select>

                            <label>Tipo de evento</label>
                            <select name="tipo_evento" required>
                                {"".join([f'<option value="{tipo}" {"selected" if tipo == "Negócios" else ""}>{tipo}</option>' for tipo in TIPOS_EVENTO])}
                            </select>

                            <label>Latitude</label>
                            <input type="number" step="any" name="latitude" value="0.0" readonly />

                            <label>Longitude</label>
                            <input type="number" step="any" name="longitude" value="0.0" readonly />

                            <label>Telefone de contato</label>
                            <input name="contato_telefone" placeholder="(31) 99999-9999" />

                            <label>Site</label>
                            <input name="site_url" placeholder="https://..." />

                            <div class="check-row">
                                <label class="check-label">
                                    <input type="checkbox" name="acessibilidade" value="1" />
                                    Possui acessibilidade
                                </label>
                                <label class="check-label">
                                    <input type="checkbox" name="proximo_metro" value="1" />
                                    Próximo do metrô
                                </label>
                                <label class="check-label">
                                    <input type="checkbox" name="restaurantes" value="1" checked />
                                    Possui restaurantes
                                </label>
                            </div>

                            <button type="submit">Salvar local</button>
                        </form>
                    </div>

                    <div class="card">
                        <h2>Novo Evento</h2>
                        <form method="post" action="/cadastro/evento">
                            <label>Nome do evento</label>
                            <input name="nome" required />

                            <label>Descrição</label>
                            <textarea name="descricao" required></textarea>

                            <label>Data de início</label>
                            <input type="date" name="data_inicio" required />

                            <label>Data de fim</label>
                            <input type="date" name="data_fim" required />

                            <label>Público estimado</label>
                            <input type="number" name="publico_estimado" min="0" required />

                            <label>Porte do evento</label>
                            <input name="porte" placeholder="Pequeno, Médio, Grande..." required />

                            <label>Telefone de contato</label>
                            <input name="contato_telefone" placeholder="(31) 99999-9999" />

                            <label>Site</label>
                            <input name="site_url" placeholder="https://..." />

                            <label>Tipo de evento</label>
                            <select name="tipo_evento" required>
                                {"".join([f'<option value="{tipo}" {"selected" if tipo == "Negócios" else ""}>{tipo}</option>' for tipo in TIPOS_EVENTO])}
                            </select>

                            <label>Local de execução</label>
                            <select name="local_id" required>
                                {locais_options}
                            </select>

                            <button type="submit">Salvar evento</button>
                        </form>
                    </div>
                </div>
            """
        else:
            secoes_manutencao_html = f"""
                {busca_manutencao_html}
                <div class="card list-card">
                    <h2>Locais cadastrados (editar/excluir)</h2>
                    {locais_existentes_html}
                    {paginacao_locais_html}
                </div>

                <div class="card list-card">
                    <h2>Eventos cadastrados (editar/excluir)</h2>
                    {eventos_existentes_html}
                    {paginacao_eventos_html}
                </div>
            """

        return f"""
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <style>
                @media (max-width: 768px) {{
                    html {{ font-size: 16px; }}
                    body {{ padding: 12px !important; }}
                    input, select, textarea, button, .btn, a.btn {{
                        font-size: 16px !important;
                        min-height: 44px;
                            }}
                    table {{
                        display: block;
                        width: 100%;
                        overflow-x: auto;
                        -webkit-overflow-scrolling: touch;
                        white-space: nowrap;
                            }}
                        }}
            </style>
            <title>{titulo_pagina}</title>
            <style>
                body {{ font-family: Arial, sans-serif; background: #f7fafc; margin: 0; padding: 24px; }}
                .container {{ max-width: 1100px; margin: 0 auto; }}
                h1 {{ color: #1f2937; margin-bottom: 8px; }}
                .subtitle {{ color: #4b5563; margin-top: 0; margin-bottom: 24px; }}
                .top-bar {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; gap: 12px; }}
                .top-nav {{ display: flex; gap: 8px; }}
                .nav-link {{ text-decoration: none; background: #e5e7eb; color: #1f2937; padding: 8px 12px; border-radius: 8px; font-weight: 700; }}
                .nav-link.active {{ background: #0f766e; color: white; }}
                .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
                .card {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 10px 24px rgba(0,0,0,0.08); }}
                .list-card {{ margin-top: 20px; }}
                .item-card {{ border: 1px solid #e5e7eb; border-radius: 10px; padding: 14px; margin-bottom: 12px; background: #fafafa; }}
                .item-card h3 {{ margin-top: 0; color: #111827; }}
                .item-row {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; border: 1px solid #e5e7eb; border-radius: 10px; padding: 12px; margin-bottom: 10px; background: #fafafa; }}
                .item-row.warning-coords {{ background: #fef3c7; border-color: #f59e0b; }}
                .item-name {{ font-weight: 700; color: #1f2937; }}
                .coord-warning {{ color: #92400e; font-weight: 700; }}
                .item-actions {{ display: flex; gap: 8px; align-items: center; }}
                .item-actions form {{ margin: 0; }}
                label {{ display: block; font-weight: 600; margin-bottom: 6px; color: #111827; }}
                input, select, textarea {{ width: 100%; padding: 10px; border: 1px solid #d1d5db; border-radius: 8px; margin-bottom: 14px; box-sizing: border-box; }}
                input[type="checkbox"] {{ width: auto; margin: 0; }}
                textarea {{ min-height: 90px; resize: vertical; }}
                button {{ background: #0f766e; color: white; border: none; border-radius: 8px; padding: 10px 16px; cursor: pointer; font-weight: 700; }}
                button:hover {{ background: #115e59; }}
                .actions {{ display: flex; gap: 10px; flex-wrap: wrap; }}
                .check-row {{ display: flex; flex-direction: column; gap: 8px; margin-bottom: 14px; }}
                .check-label {{ display: flex; align-items: center; gap: 8px; margin-bottom: 0; font-weight: 600; }}
                .btn-secondary {{ background: #374151; }}
                .btn-secondary:hover {{ background: #1f2937; }}
                .btn-danger {{ background: #b91c1c; }}
                .btn-danger:hover {{ background: #991b1b; }}
                .pagination {{ display: flex; gap: 10px; align-items: center; margin-top: 10px; flex-wrap: wrap; }}
                .page-link {{ text-decoration: none; background: #e5e7eb; color: #1f2937; padding: 6px 10px; border-radius: 6px; font-weight: 700; }}
                .modal-overlay {{ display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.45); z-index: 9998; padding: 24px; overflow: auto; }}
                .modal-card {{ max-width: 560px; margin: 40px auto; background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 14px 40px rgba(0,0,0,0.25); }}
                .modal-actions {{ display: flex; gap: 8px; justify-content: flex-end; }}
                .back {{ display: inline-block; color: #2563eb; text-decoration: none; font-weight: 600; }}
                .msg {{ padding: 12px; border-radius: 8px; margin-bottom: 16px; font-weight: 600; }}
                .ok {{ background: #dcfce7; color: #166534; }}
                .aviso {{ background: #fef3c7; color: #92400e; }}
                .erro {{ background: #fee2e2; color: #991b1b; }}
                .vazio {{ color: #6b7280; font-style: italic; }}
                @media (max-width: 900px) {{
                    .grid {{ grid-template-columns: 1fr; }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>{titulo_pagina}</h1>
                <p class="subtitle">{subtitulo}</p>
                <div class="top-bar">
                    <div class="top-nav">
                        <a class="{nav_cadastro_class}" href="/cadastro">Tela de Cadastro</a>
                        <a class="{nav_manutencao_class}" href="/manutencao">Tela de Manutenção</a>
                    </div>
                    {botao_voltar_portal_html()}
                </div>
                {msg_html}
                {secoes_cadastro_html}
                {secoes_manutencao_html}
            </div>
            <script>
                function filtrarMunicipios(estadoSelectId, municipioSelectId) {{
                    const estado = document.getElementById(estadoSelectId);
                    const municipio = document.getElementById(municipioSelectId);
                    if (!municipio) return;

                    if (!municipio._allOptions) {{
                        municipio._allOptions = Array.from(municipio.options).map((opt) => ({{
                            value: opt.value,
                            text: opt.text,
                            dono: opt.getAttribute('data-estado-id') || ''
                        }}));
                    }}

                    const estadoId = estado ? estado.value : '';
                    const valorAtual = municipio.value;
                    const opcoesFiltradas = municipio._allOptions.filter((opt) => !estadoId || !opt.dono || opt.dono === estadoId);

                    municipio.innerHTML = '';
                    opcoesFiltradas.forEach((opt) => {{
                        const optionEl = document.createElement('option');
                        optionEl.value = opt.value;
                        optionEl.text = opt.text;
                        if (opt.dono) {{
                            optionEl.setAttribute('data-estado-id', opt.dono);
                        }}
                        municipio.appendChild(optionEl);
                    }});

                    const aindaExiste = opcoesFiltradas.some((opt) => opt.value === valorAtual);
                    if (aindaExiste) {{
                        municipio.value = valorAtual;
                    }} else if (municipio.options.length) {{
                        municipio.selectedIndex = 0;
                    }}
                }}

                function openModal(id) {{
                    var el = document.getElementById(id);
                    if (el) el.style.display = 'block';
                    if (id.startsWith('local-modal-')) {{
                        var localId = id.replace('local-modal-', '');
                        filtrarMunicipios('edit_estado_' + localId, 'edit_municipio_' + localId);
                    }}
                }}

                function closeModal(id) {{
                    var el = document.getElementById(id);
                    if (el) el.style.display = 'none';
                }}

                function closeModalOnOverlay(event, id) {{
                    if (event.target && event.target.id === id) {{
                        closeModal(id);
                    }}
                }}

                filtrarMunicipios('cadastro_estado_id', 'cadastro_municipio_id');
            </script>
        </body>
        </html>
        """
    finally:
        db.close()


@app.get("/cadastro", response_class=HTMLResponse)
def tela_cadastro(request: Request, msg: Optional[str] = None):
    redirect = _redirect_se_nao_admin(request)
    if redirect:
        return redirect

    return render_tela_cadastro_manutencao(msg=msg, modo="cadastro")


@app.get("/manutencao", response_class=HTMLResponse)
def tela_manutencao(
    request: Request,
    msg: Optional[str] = None,
    busca_local: str = "",
    busca_evento: str = "",
    pagina_local: int = 1,
    pagina_evento: int = 1,
):
    redirect = _redirect_se_nao_admin(request)
    if redirect:
        return redirect

    return render_tela_cadastro_manutencao(
        msg=msg,
        modo="manutencao",
        busca_local=busca_local,
        busca_evento=busca_evento,
        pagina_local=pagina_local,
        pagina_evento=pagina_evento,
    )


@app.post("/cadastro/local")
def cadastrar_local(
    request: Request,
    nome: str = Form(...),
    endereco: str = Form(...),
    regiao: str = Form(...),
    estado_id: int = Form(...),
    municipio_id: int = Form(...),
    tipo_evento: str = Form(...),
    contato_telefone: str = Form(""),
    site_url: str = Form(""),
    acessibilidade: Optional[str] = Form(None),
    proximo_metro: Optional[str] = Form(None),
    restaurantes: Optional[str] = Form("1"),
):
    redirect = _redirect_se_nao_admin(request)
    if redirect:
        return redirect

    db: Session = SessionLocal()
    try:
        if not _localidade_valida(db, estado_id, municipio_id):
            return RedirectResponse(url="/cadastro?msg=local_invalido", status_code=303)

        latitude_geo, longitude_geo = geocodificar_endereco(endereco)
        sem_coordenadas = latitude_geo is None or longitude_geo is None

        local = Local(
            nome=nome,
            endereco=endereco,
            regiao=regiao,
            municipio_id=municipio_id,
            tipo_evento=normalizar_tipo_evento(tipo_evento),
            latitude=None if sem_coordenadas else latitude_geo,
            longitude=None if sem_coordenadas else longitude_geo,
            contato_telefone=(contato_telefone or "").strip(),
            site_url=(site_url or "").strip(),
            acessibilidade=bool(acessibilidade),
            proximo_metro=bool(proximo_metro),
            restaurantes=bool(restaurantes),
        )
        db.add(local)
        db.commit()
        msg = "local_ok_sem_coordenadas" if sem_coordenadas else "local_ok"
        return RedirectResponse(url=f"/cadastro?msg={msg}", status_code=303)
    finally:
        db.close()


@app.post("/cadastro/evento")
def cadastrar_evento(
    request: Request,
    nome: str = Form(...),
    descricao: str = Form(...),
    data_inicio: str = Form(...),
    data_fim: str = Form(...),
    publico_estimado: int = Form(...),
    porte: str = Form(...),
    contato_telefone: str = Form(""),
    site_url: str = Form(""),
    tipo_evento: str = Form(...),
    local_id: int = Form(...),
):
    redirect = _redirect_se_nao_admin(request)
    if redirect:
        return redirect

    db: Session = SessionLocal()
    try:
        local = db.query(Local).filter(Local.id == local_id).first()
        if not local:
            return RedirectResponse(url="/cadastro?msg=local_invalido", status_code=303)

        try:
            data_inicio_dt = datetime.strptime(data_inicio, "%Y-%m-%d").date()
            data_fim_dt = datetime.strptime(data_fim, "%Y-%m-%d").date()
        except ValueError:
            return RedirectResponse(url="/cadastro?msg=data_invalida", status_code=303)

        if data_fim_dt < data_inicio_dt:
            return RedirectResponse(url="/cadastro?msg=periodo_invalido", status_code=303)

        evento = Evento(
            nome=nome,
            descricao=descricao,
            data_inicio=data_inicio_dt,
            data_fim=data_fim_dt,
            publico_estimado=publico_estimado,
            porte=porte,
            contato_telefone=(contato_telefone or "").strip(),
            site_url=(site_url or "").strip(),
            tipo_evento=normalizar_tipo_evento(tipo_evento),
            local_id=local_id,
        )
        db.add(evento)
        db.commit()
        return RedirectResponse(url="/cadastro?msg=evento_ok", status_code=303)
    finally:
        db.close()


@app.post("/cadastro/local/{local_id}/editar")
def editar_local(
    request: Request,
    local_id: int,
    nome: str = Form(...),
    endereco: str = Form(...),
    regiao: str = Form(...),
    estado_id: int = Form(...),
    municipio_id: int = Form(...),
    tipo_evento: str = Form(...),
    contato_telefone: str = Form(""),
    site_url: str = Form(""),
    acessibilidade: Optional[str] = Form(None),
    proximo_metro: Optional[str] = Form(None),
    restaurantes: Optional[str] = Form(None),
):
    redirect = _redirect_se_nao_admin(request)
    if redirect:
        return redirect

    db: Session = SessionLocal()
    try:
        local = db.query(Local).filter(Local.id == local_id).first()
        if not local:
            return RedirectResponse(url="/manutencao?msg=registro_nao_encontrado", status_code=303)

        if not _localidade_valida(db, estado_id, municipio_id):
            return RedirectResponse(url="/manutencao?msg=local_invalido", status_code=303)

        latitude_geo, longitude_geo = geocodificar_endereco(endereco)
        sem_coordenadas = latitude_geo is None or longitude_geo is None

        local.nome = nome
        local.endereco = endereco
        local.regiao = regiao
        local.municipio_id = municipio_id
        local.tipo_evento = normalizar_tipo_evento(tipo_evento)
        local.latitude = None if sem_coordenadas else latitude_geo
        local.longitude = None if sem_coordenadas else longitude_geo
        local.contato_telefone = (contato_telefone or "").strip()
        local.site_url = (site_url or "").strip()
        local.acessibilidade = bool(acessibilidade)
        local.proximo_metro = bool(proximo_metro)
        local.restaurantes = bool(restaurantes)
        db.commit()
        msg = "local_edit_ok_sem_coordenadas" if sem_coordenadas else "local_edit_ok"
        return RedirectResponse(url=f"/manutencao?msg={msg}", status_code=303)
    finally:
        db.close()


@app.post("/cadastro/local/{local_id}/excluir")
def excluir_local(request: Request, local_id: int):
    redirect = _redirect_se_nao_admin(request)
    if redirect:
        return redirect

    db: Session = SessionLocal()
    try:
        local = db.query(Local).filter(Local.id == local_id).first()
        if not local:
            return RedirectResponse(url="/manutencao?msg=registro_nao_encontrado", status_code=303)

        db.query(Evento).filter(Evento.local_id == local_id).delete(synchronize_session=False)
        db.delete(local)
        db.commit()
        return RedirectResponse(url="/manutencao?msg=local_delete_ok", status_code=303)
    finally:
        db.close()


@app.post("/cadastro/evento/{evento_id}/editar")
def editar_evento(
    request: Request,
    evento_id: int,
    nome: str = Form(...),
    descricao: str = Form(...),
    data_inicio: str = Form(...),
    data_fim: str = Form(...),
    publico_estimado: int = Form(...),
    porte: str = Form(...),
    contato_telefone: str = Form(""),
    site_url: str = Form(""),
    tipo_evento: str = Form(...),
    local_id: int = Form(...),
):
    redirect = _redirect_se_nao_admin(request)
    if redirect:
        return redirect

    db: Session = SessionLocal()
    try:
        evento = db.query(Evento).filter(Evento.id == evento_id).first()
        if not evento:
            return RedirectResponse(url="/manutencao?msg=registro_nao_encontrado", status_code=303)

        local = db.query(Local).filter(Local.id == local_id).first()
        if not local:
            return RedirectResponse(url="/manutencao?msg=local_invalido", status_code=303)

        try:
            data_inicio_dt = datetime.strptime(data_inicio, "%Y-%m-%d").date()
            data_fim_dt = datetime.strptime(data_fim, "%Y-%m-%d").date()
        except ValueError:
            return RedirectResponse(url="/manutencao?msg=data_invalida", status_code=303)

        if data_fim_dt < data_inicio_dt:
            return RedirectResponse(url="/manutencao?msg=periodo_invalido", status_code=303)

        evento.nome = nome
        evento.descricao = descricao
        evento.data_inicio = data_inicio_dt
        evento.data_fim = data_fim_dt
        evento.publico_estimado = publico_estimado
        evento.porte = porte
        evento.contato_telefone = (contato_telefone or "").strip()
        evento.site_url = (site_url or "").strip()
        evento.tipo_evento = normalizar_tipo_evento(tipo_evento)
        evento.local_id = local_id
        db.commit()
        return RedirectResponse(url="/manutencao?msg=evento_edit_ok", status_code=303)
    finally:
        db.close()


@app.post("/cadastro/evento/{evento_id}/excluir")
def excluir_evento(request: Request, evento_id: int):
    redirect = _redirect_se_nao_admin(request)
    if redirect:
        return redirect

    db: Session = SessionLocal()
    try:
        evento = db.query(Evento).filter(Evento.id == evento_id).first()
        if not evento:
            return RedirectResponse(url="/manutencao?msg=registro_nao_encontrado", status_code=303)

        db.delete(evento)
        db.commit()
        return RedirectResponse(url="/manutencao?msg=evento_delete_ok", status_code=303)
    finally:
        db.close()


@app.post("/cadastro/anunciante")
def cadastrar_anunciante(
    request: Request,
    nome: str = Form(...),
    tipo: str = Form(""),
    endereco: str = Form(""),
    latitude: float = Form(0.0),
    longitude: float = Form(0.0),
    contato_telefone: str = Form(""),
    site_url: str = Form(""),
    urlimagem: str = Form(""),
    datainicio: str = Form(""),
    datafim: str = Form(""),
):
    redirect = _redirect_se_nao_super_admin(request)
    if redirect:
        return redirect

    db: Session = SessionLocal()
    try:
        data_inicio_dt = None
        data_fim_dt = None
        if datainicio:
            try:
                data_inicio_dt = datetime.strptime(datainicio, "%Y-%m-%d").date()
            except ValueError:
                return RedirectResponse(url="/anunciantes?msg=data_invalida", status_code=303)
        if datafim:
            try:
                data_fim_dt = datetime.strptime(datafim, "%Y-%m-%d").date()
            except ValueError:
                return RedirectResponse(url="/anunciantes?msg=data_invalida", status_code=303)

        if data_inicio_dt and data_fim_dt and data_fim_dt < data_inicio_dt:
            return RedirectResponse(url="/anunciantes?msg=periodo_invalido", status_code=303)

        latitude_geo, longitude_geo = geocodificar_endereco(endereco)
        sem_coordenadas = latitude_geo is None or longitude_geo is None

        anunciante = Anunciante(
            nome=nome,
            tipo=(tipo or "").strip(),
            endereco=endereco,
            latitude=None if sem_coordenadas else latitude_geo,
            longitude=None if sem_coordenadas else longitude_geo,
            contato_telefone=(contato_telefone or "").strip(),
            site_url=(site_url or "").strip(),
            urlimagem=urlimagem,
            datainicio=data_inicio_dt,
            datafim=data_fim_dt,
        )
        db.add(anunciante)
        db.commit()
        msg = "ok_sem_coordenadas" if sem_coordenadas else "ok"
        return RedirectResponse(url=f"/anunciantes?msg={msg}", status_code=303)
    finally:
        db.close()


@app.post("/cadastro/anunciante/{anunciante_id}/editar")
def editar_anunciante(
    request: Request,
    anunciante_id: int,
    nome: str = Form(...),
    tipo: str = Form(""),
    endereco: str = Form(""),
    latitude: float = Form(0.0),
    longitude: float = Form(0.0),
    contato_telefone: str = Form(""),
    site_url: str = Form(""),
    urlimagem: str = Form(""),
    datainicio: str = Form(""),
    datafim: str = Form(""),
):
    redirect = _redirect_se_nao_super_admin(request)
    if redirect:
        return redirect

    db: Session = SessionLocal()
    try:
        anunciante = db.query(Anunciante).filter(Anunciante.id == anunciante_id).first()
        if not anunciante:
            return RedirectResponse(url="/anunciantes?msg=nao_encontrado", status_code=303)

        data_inicio_dt = None
        data_fim_dt = None
        if datainicio:
            try:
                data_inicio_dt = datetime.strptime(datainicio, "%Y-%m-%d").date()
            except ValueError:
                return RedirectResponse(url="/anunciantes?msg=data_invalida", status_code=303)
        if datafim:
            try:
                data_fim_dt = datetime.strptime(datafim, "%Y-%m-%d").date()
            except ValueError:
                return RedirectResponse(url="/anunciantes?msg=data_invalida", status_code=303)

        if data_inicio_dt and data_fim_dt and data_fim_dt < data_inicio_dt:
            return RedirectResponse(url="/anunciantes?msg=periodo_invalido", status_code=303)

        latitude_geo, longitude_geo = geocodificar_endereco(endereco)
        sem_coordenadas = latitude_geo is None or longitude_geo is None

        anunciante.nome = nome
        anunciante.tipo = (tipo or "").strip()
        anunciante.endereco = endereco
        anunciante.latitude = None if sem_coordenadas else latitude_geo
        anunciante.longitude = None if sem_coordenadas else longitude_geo
        anunciante.contato_telefone = (contato_telefone or "").strip()
        anunciante.site_url = (site_url or "").strip()
        anunciante.urlimagem = urlimagem
        anunciante.datainicio = data_inicio_dt
        anunciante.datafim = data_fim_dt
        db.commit()
        msg = "edit_ok_sem_coordenadas" if sem_coordenadas else "edit_ok"
        return RedirectResponse(url=f"/anunciantes?msg={msg}", status_code=303)
    finally:
        db.close()


@app.post("/cadastro/anunciante/{anunciante_id}/excluir")
def excluir_anunciante(request: Request, anunciante_id: int):
    redirect = _redirect_se_nao_super_admin(request)
    if redirect:
        return redirect

    db: Session = SessionLocal()
    try:
        anunciante = db.query(Anunciante).filter(Anunciante.id == anunciante_id).first()
        if not anunciante:
            return RedirectResponse(url="/anunciantes?msg=nao_encontrado", status_code=303)

        db.delete(anunciante)
        db.commit()
        return RedirectResponse(url="/anunciantes?msg=delete_ok", status_code=303)
    finally:
        db.close()


@app.get("/anunciantes", response_class=HTMLResponse)
def gerenciar_anunciantes(request: Request, msg: Optional[str] = None):
    redirect = _redirect_se_nao_super_admin(request)
    if redirect:
        return redirect

    db: Session = SessionLocal()
    try:
        anunciantes = db.query(Anunciante).order_by(Anunciante.nome).all()

        msg_html = ""
        if msg == "ok":
            msg_html = '<div class="msg ok">Anunciante cadastrado com sucesso.</div>'
        elif msg == "ok_sem_coordenadas":
            msg_html = '<div class="msg aviso">Anunciante cadastrado, mas o endereço não foi localizado. Coordenadas pendentes.</div>'
        elif msg == "edit_ok":
            msg_html = '<div class="msg ok">Anunciante atualizado com sucesso.</div>'
        elif msg == "edit_ok_sem_coordenadas":
            msg_html = '<div class="msg aviso">Anunciante atualizado, mas o endereço não foi localizado. Coordenadas pendentes.</div>'
        elif msg == "delete_ok":
            msg_html = '<div class="msg ok">Anunciante excluído com sucesso.</div>'
        elif msg == "nao_encontrado":
            msg_html = '<div class="msg erro">Anunciante não encontrado.</div>'
        elif msg == "data_invalida":
            msg_html = '<div class="msg erro">Data inválida. Use o formato correto da tela.</div>'
        elif msg == "periodo_invalido":
            msg_html = '<div class="msg erro">A data fim não pode ser menor que a data início.</div>'
        elif msg == "endereco_nao_localizado":
            msg_html = '<div class="msg erro">Não foi possível localizar o endereço informado para preencher latitude e longitude.</div>'

        anunciantes_html = ""
        for anunciante in anunciantes:
            anunciante_id = anunciante.id
            anunciante_nome = escape(anunciante.nome or "")
            anunciante_tipo = escape(anunciante.tipo or "")
            anunciante_endereco = escape(anunciante.endereco or "")
            anunciante_sem_coordenadas = not coordenadas_validas(anunciante.latitude, anunciante.longitude)
            anunciante_latitude = "-" if anunciante.latitude is None else anunciante.latitude
            anunciante_longitude = "-" if anunciante.longitude is None else anunciante.longitude
            anunciante_latitude_modal = "" if anunciante.latitude is None else anunciante.latitude
            anunciante_longitude_modal = "" if anunciante.longitude is None else anunciante.longitude
            anunciante_warning_class = "warning-coords" if anunciante_sem_coordenadas else ""
            anunciante_telefone = escape(anunciante.contato_telefone or "")
            anunciante_site = _normalizar_site_url(anunciante.site_url or "")
            anunciante_urlimagem = escape(anunciante.urlimagem or "")
            anunciante_datainicio = anunciante.datainicio.isoformat() if anunciante.datainicio else ""
            anunciante_datafim = anunciante.datafim.isoformat() if anunciante.datafim else ""

            anunciantes_html += f"""
            <tr class="{anunciante_warning_class}">
                <td>{anunciante_id}</td>
                <td>{anunciante_nome}</td>
                <td>{anunciante_tipo}</td>
                <td>{anunciante_endereco}</td>
                <td>{anunciante_latitude}</td>
                <td>{anunciante_longitude}</td>
                <td>{anunciante_telefone}</td>
                <td>{f'<a href="{escape(anunciante_site)}" target="_blank">Site</a>' if anunciante_site else '-'}</td>
                <td>{anunciante_datainicio}</td>
                <td>{anunciante_datafim}</td>
                <td><a href="{anunciante_urlimagem}" target="_blank">Ver</a></td>
                <td>
                    <button onclick='openEditModal({anunciante_id}, {json.dumps(anunciante.nome or "")}, {json.dumps(anunciante.tipo or "")}, {json.dumps(anunciante.endereco or "")}, {json.dumps(anunciante_latitude_modal)}, {json.dumps(anunciante_longitude_modal)}, {json.dumps(anunciante.contato_telefone or "")}, {json.dumps(anunciante.site_url or "")}, {json.dumps(anunciante.urlimagem or "")}, {json.dumps(anunciante_datainicio)}, {json.dumps(anunciante_datafim)})'>Editar</button>
                    <form method="post" action="/cadastro/anunciante/{anunciante_id}/excluir" style="display:inline;">
                        <button type="submit" onclick="return confirm('Tem certeza?')">Excluir</button>
                    </form>
                </td>
            </tr>
            """

        return f"""
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <style>
                @media (max-width: 768px) {{
                    html {{ font-size: 16px; }}
                    body {{ padding: 12px !important; }}
                    input, select, textarea, button, .btn, a.btn {{
                        font-size: 16px !important;
                        min-height: 44px;
                            }}
                    table {{
                        display: block;
                        width: 100%;
                        overflow-x: auto;
                        -webkit-overflow-scrolling: touch;
                        white-space: nowrap;
                            }}
                        }}
            </style>
            <title>Gerenciar Anunciantes</title>
            <style>
                body {{ font-family: Arial, sans-serif; background: #f8f9fb; margin: 0; padding: 24px; }}
                .page {{ max-width: 1000px; margin: 0 auto; background: white; border-radius: 12px; padding: 24px; box-shadow: 0 14px 36px rgba(0,0,0,.08); }}
                h1 {{ margin-top: 0; color: #1f2937; }}
                .msg {{ border-radius: 8px; padding: 10px 12px; margin-bottom: 14px; font-size: 14px; }}
                .ok {{ background: #dcfce7; color: #166534; }}
                .aviso {{ background: #fef3c7; color: #92400e; }}
                .erro {{ background: #fee2e2; color: #991b1b; }}
                .btn {{ background: #1f2937; color: white; border: none; border-radius: 8px; padding: 10px 14px; cursor: pointer; font-weight: 700; }}
                .btn:hover {{ background: #111827; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #e5e7eb; }}
                th {{ background: #f3f4f6; font-weight: 700; color: #111827; }}
                tr:hover {{ background: #f9fafb; }}
                tr.warning-coords td {{ background: #fef3c7; }}
                .modal {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,.5); z-index: 9999; }}
                .modal.show {{ display: flex; align-items: center; justify-content: center; }}
                .modal-content {{ background: white; border-radius: 12px; padding: 24px; max-width: 500px; width: 100%; }}
                .modal-content h2 {{ margin-top: 0; color: #1f2937; }}
                .form-group {{ margin: 14px 0; }}
                .form-group label {{ display: block; margin-bottom: 6px; font-weight: 700; color: #111827; }}
                .form-group input {{ width: 100%; border: 1px solid #d1d5db; border-radius: 8px; padding: 10px 12px; box-sizing: border-box; }}
                .modal-buttons {{ margin-top: 20px; display: flex; gap: 10px; justify-content: flex-end; }}
                .btn-cancel {{ background: #e5e7eb; color: #111827; }}
                .btn-cancel:hover {{ background: #d1d5db; }}
                .actions {{ display: flex; gap: 10px; }}
                a {{ color: #1f2937; text-decoration: none; }}
                a:hover {{ text-decoration: underline; }}
            </style>
        </head>
        <body>
            <div class="page">
                {botao_voltar_portal_html()}
                <h1>Gerenciar Anunciantes</h1>
                {msg_html}
                <button class="btn" onclick="openCreateModal()">+ Novo Anunciante</button>

                <table>
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Nome</th>
                            <th>Tipo</th>
                            <th>Endereço</th>
                            <th>Latitude</th>
                            <th>Longitude</th>
                            <th>Telefone</th>
                            <th>Site</th>
                            <th>Data Início</th>
                            <th>Data Fim</th>
                            <th>Imagem</th>
                            <th>Ações</th>
                        </tr>
                    </thead>
                    <tbody>
                        {anunciantes_html}
                    </tbody>
                </table>
            </div>

            <div id="createModal" class="modal">
                <div class="modal-content">
                    <h2>Novo Anunciante</h2>
                    <form method="post" action="/cadastro/anunciante">
                        <div class="form-group">
                            <label for="nome">Nome *</label>
                            <input id="nome" type="text" name="nome" required />
                        </div>
                        <div class="form-group">
                            <label for="tipo">Tipo</label>
                            <input id="tipo" type="text" name="tipo" placeholder="Ex.: Restaurante, Hotel, Parceiro..." />
                        </div>
                        <div class="form-group">
                            <label for="endereco">Endereço</label>
                            <input id="endereco" type="text" name="endereco" />
                        </div>
                        <div class="form-group">
                            <label for="latitude">Latitude</label>
                            <input id="latitude" type="number" name="latitude" step="0.000001" value="0.0" readonly />
                        </div>
                        <div class="form-group">
                            <label for="longitude">Longitude</label>
                            <input id="longitude" type="number" name="longitude" step="0.000001" value="0.0" readonly />
                        </div>
                        <div class="form-group">
                            <label for="contato_telefone">Telefone de contato</label>
                            <input id="contato_telefone" type="text" name="contato_telefone" />
                        </div>
                        <div class="form-group">
                            <label for="site_url">Site</label>
                            <input id="site_url" type="text" name="site_url" placeholder="https://..." />
                        </div>
                        <div class="form-group">
                            <label for="urlimagem">URL da Imagem</label>
                            <input id="urlimagem" type="text" name="urlimagem" />
                        </div>
                        <div class="form-group">
                            <label for="datainicio">Data Início</label>
                            <input id="datainicio" type="date" name="datainicio" />
                        </div>
                        <div class="form-group">
                            <label for="datafim">Data Fim</label>
                            <input id="datafim" type="date" name="datafim" />
                        </div>
                        <div class="modal-buttons">
                            <button type="button" class="btn btn-cancel" onclick="closeCreateModal()">Cancelar</button>
                            <button type="submit" class="btn">Salvar</button>
                        </div>
                    </form>
                </div>
            </div>

            <div id="editModal" class="modal">
                <div class="modal-content">
                    <h2>Editar Anunciante</h2>
                    <form id="editForm" method="post">
                        <div class="form-group">
                            <label for="edit_nome">Nome *</label>
                            <input id="edit_nome" type="text" name="nome" required />
                        </div>
                        <div class="form-group">
                            <label for="edit_tipo">Tipo</label>
                            <input id="edit_tipo" type="text" name="tipo" placeholder="Ex.: Restaurante, Hotel, Parceiro..." />
                        </div>
                        <div class="form-group">
                            <label for="edit_endereco">Endereço</label>
                            <input id="edit_endereco" type="text" name="endereco" />
                        </div>
                        <div class="form-group">
                            <label for="edit_latitude">Latitude</label>
                            <input id="edit_latitude" type="number" name="latitude" step="0.000001" readonly />
                        </div>
                        <div class="form-group">
                            <label for="edit_longitude">Longitude</label>
                            <input id="edit_longitude" type="number" name="longitude" step="0.000001" readonly />
                        </div>
                        <div class="form-group">
                            <label for="edit_contato_telefone">Telefone de contato</label>
                            <input id="edit_contato_telefone" type="text" name="contato_telefone" />
                        </div>
                        <div class="form-group">
                            <label for="edit_site_url">Site</label>
                            <input id="edit_site_url" type="text" name="site_url" placeholder="https://..." />
                        </div>
                        <div class="form-group">
                            <label for="edit_urlimagem">URL da Imagem</label>
                            <input id="edit_urlimagem" type="text" name="urlimagem" />
                        </div>
                        <div class="form-group">
                            <label for="edit_datainicio">Data Início</label>
                            <input id="edit_datainicio" type="date" name="datainicio" />
                        </div>
                        <div class="form-group">
                            <label for="edit_datafim">Data Fim</label>
                            <input id="edit_datafim" type="date" name="datafim" />
                        </div>
                        <div class="modal-buttons">
                            <button type="button" class="btn btn-cancel" onclick="closeEditModal()">Cancelar</button>
                            <button type="submit" class="btn">Salvar</button>
                        </div>
                    </form>
                </div>
            </div>

            <script>
                function openCreateModal() {{
                    document.getElementById('createModal').classList.add('show');
                }}

                function closeCreateModal() {{
                    document.getElementById('createModal').classList.remove('show');
                    document.getElementById('nome').value = '';
                    document.getElementById('tipo').value = '';
                    document.getElementById('endereco').value = '';
                    document.getElementById('latitude').value = '0.0';
                    document.getElementById('longitude').value = '0.0';
                    document.getElementById('contato_telefone').value = '';
                    document.getElementById('site_url').value = '';
                    document.getElementById('urlimagem').value = '';
                    document.getElementById('datainicio').value = '';
                    document.getElementById('datafim').value = '';
                }}

                function openEditModal(id, nome, tipo, endereco, latitude, longitude, contatoTelefone, siteUrl, urlimagem, datainicio, datafim) {{
                    document.getElementById('edit_nome').value = nome;
                    document.getElementById('edit_tipo').value = tipo;
                    document.getElementById('edit_endereco').value = endereco;
                    document.getElementById('edit_latitude').value = latitude;
                    document.getElementById('edit_longitude').value = longitude;
                    document.getElementById('edit_contato_telefone').value = contatoTelefone || '';
                    document.getElementById('edit_site_url').value = siteUrl || '';
                    document.getElementById('edit_urlimagem').value = urlimagem;
                    document.getElementById('edit_datainicio').value = datainicio || '';
                    document.getElementById('edit_datafim').value = datafim || '';
                    document.getElementById('editForm').action = `/cadastro/anunciante/${{id}}/editar`;
                    document.getElementById('editModal').classList.add('show');
                }}

                function closeEditModal() {{
                    document.getElementById('editModal').classList.remove('show');
                }}

                document.getElementById('createModal').addEventListener('click', function(e) {{
                    if (e.target === this) closeCreateModal();
                }});

                document.getElementById('editModal').addEventListener('click', function(e) {{
                    if (e.target === this) closeEditModal();
                }});
            </script>
        </body>
        </html>
        """
    finally:
        db.close()


@app.get("/mapa-locais", response_class=HTMLResponse)
def mapa_locais(request: Request, _publico: bool = False):
    if not _publico:
        redirect = _redirect_se_nao_autenticado(request)
        if redirect:
            return redirect

    redirect_localidade = _redirect_se_localidade_nao_definida(request, _publico=_publico)
    if redirect_localidade:
        return redirect_localidade

    estado_id, municipio_id = _obter_localidade_sessao(request, _publico=_publico)

    db: Session = SessionLocal()
    try:
        locais = db.query(Local).filter(Local.municipio_id == municipio_id).all()
        anunciantes = db.query(Anunciante).all()
        regionais = [r.nome for r in db.query(Regional).order_by(Regional.nome).all()]
        data_referencia = datetime.now().date()

        centro_lat, centro_lon, zoom_estado = _centro_mapa_por_estado(db, estado_id)
        bounds_estado = _bounds_mapa_por_estado(db, estado_id)
        mapa = folium.Map(location=[centro_lat, centro_lon], zoom_start=zoom_estado)
        if bounds_estado:
            mapa.fit_bounds(bounds_estado, padding=(24, 24))
        map_name = mapa.get_name()
        mapa.get_root().header.add_child(folium.Element(recursos_rota_mapa_html(map_name)))
        mapa.get_root().html.add_child(folium.Element(atalho_inicio_mapa_html()))

        locais_mostrados = 0
        contagem_por_regional = {}
        for local in locais:
            if not coordenadas_validas(local.latitude, local.longitude):
                continue
            lat = float(local.latitude)
            lon = float(local.longitude)
            regional = local.regiao or "Sem regional"

            # Contar locais por regional
            if regional not in contagem_por_regional:
                contagem_por_regional[regional] = 0
            contagem_por_regional[regional] += 1

            cor = cor_regional(local.regiao)
            tooltip_text = f"{local.nome} — {local.regiao}"
            popup_text = f"""
            <div data-track-entidade="local" data-track-id="{local.id}">
            <b>{local.nome}</b><br>
            Endereço: {local.endereco}<br>
            Região: {local.regiao}<br>
            {_telefone_html(local.contato_telefone)}
            {_site_html_rastreado(local.site_url, 'local', local.id)}
            Lat: {lat}, Lon: {lon}
            {link_rota_html(lat, lon, map_name, local.nome)}
            </div>
            """
            folium.Marker(
                location=[lat, lon],
                popup=popup_text,
                tooltip=tooltip_text,
                icon=folium.Icon(color=cor)
            ).add_to(mapa)
            locais_mostrados += 1

        if EXIBIR_ANUNCIANTES_MAPA:
            total_anunciantes_ativos = 0
            for anunciante in anunciantes:
                if not anunciante_ativo_em_data(anunciante, data_referencia):
                    continue
                if not coordenadas_validas(anunciante.latitude, anunciante.longitude):
                    continue

                adicionar_marcador_anunciante(mapa, anunciante, map_name)
                total_anunciantes_ativos += 1

            mapa.get_root().html.add_child(
                folium.Element(painel_anunciantes_ativos_html(total_anunciantes_ativos))
            )

        # Adicionar "Sem regional" à lista se houver locais sem regional
        if "Sem regional" in contagem_por_regional and "Sem regional" not in regionais:
            regionais.append("Sem regional")

        # Filtrar apenas regionais que têm locais e incluir regionais presentes
        # nos dados mas ausentes na tabela de regionais.
        regionais_com_locais = [r for r in regionais if r in contagem_por_regional]
        for regional in sorted(contagem_por_regional.keys()):
            if regional not in regionais_com_locais:
                regionais_com_locais.append(regional)

        cabecalho_legenda = f"Legenda - Regional ({locais_mostrados} locais)"
        mapa.get_root().html.add_child(
            folium.Element(
                legenda_mapa_html(
                    regionais_com_locais,
                    cabecalho_legenda,
                    contagem_por_regional,
                    exibir_contagem=EXIBIR_CONTAGEM_LOCAIS_MAPA,
                )
            )
        )
        return mapa.get_root().render()
    finally:
        db.close()


@app.get("/public/mapa-locais", response_class=HTMLResponse)
def mapa_locais_publico(request: Request):
    return mapa_locais(request, _publico=True)


@app.get("/eventos")
def listar_eventos(request: Request):
    redirect = _redirect_se_nao_autenticado(request)
    if redirect:
        return redirect

    db: Session = SessionLocal()
    eventos = db.query(Evento).all()
    return eventos


@app.get("/eventos/porte/{porte}")
def eventos_por_porte(request: Request, porte: str):
    redirect = _redirect_se_nao_autenticado(request)
    if redirect:
        return redirect

    db: Session = SessionLocal()
    eventos = db.query(Evento).filter(Evento.porte == porte).all()
    return eventos


@app.get("/mapa", response_class=HTMLResponse)
def mapa_eventos(request: Request, _publico: bool = False):
    if not _publico:
        redirect = _redirect_se_nao_autenticado(request)
        if redirect:
            return redirect

    redirect_localidade = _redirect_se_localidade_nao_definida(request, _publico=_publico)
    if redirect_localidade:
        return redirect_localidade

    estado_id, municipio_id = _obter_localidade_sessao(request, _publico=_publico)

    db: Session = SessionLocal()
    try:
        eventos = db.query(Evento).join(Local).filter(Local.municipio_id == municipio_id).all()
        anunciantes = db.query(Anunciante).all()
        regionais = [r.nome for r in db.query(Regional).order_by(Regional.nome).all()]
        data_referencia = datetime.now().date()

        centro_lat, centro_lon, zoom_estado = _centro_mapa_por_estado(db, estado_id)
        bounds_estado = _bounds_mapa_por_estado(db, estado_id)
        mapa = folium.Map(location=[centro_lat, centro_lon], zoom_start=zoom_estado)
        if bounds_estado:
            mapa.fit_bounds(bounds_estado, padding=(24, 24))
        map_name = mapa.get_name()
        mapa.get_root().header.add_child(folium.Element(recursos_rota_mapa_html(map_name)))
        mapa.get_root().html.add_child(folium.Element(atalho_inicio_mapa_html()))
        cluster_eventos = MarkerCluster(name="Eventos").add_to(mapa)
        bounds_por_regional: dict[str, dict[str, float]] = {}

        eventos_mostrados = 0
        contagem_por_regional = {}
        for evento in eventos:
            if not coordenadas_validas(evento.local.latitude, evento.local.longitude):
                continue
            lat = float(evento.local.latitude)
            lon = float(evento.local.longitude)
            regional = evento.local.regiao or "Sem regional"

            # Contar eventos por regional
            if regional not in contagem_por_regional:
                contagem_por_regional[regional] = 0
            contagem_por_regional[regional] += 1

            limites = bounds_por_regional.get(regional)
            if not limites:
                bounds_por_regional[regional] = {
                    "min_lat": lat,
                    "max_lat": lat,
                    "min_lon": lon,
                    "max_lon": lon,
                }
            else:
                limites["min_lat"] = min(limites["min_lat"], lat)
                limites["max_lat"] = max(limites["max_lat"], lat)
                limites["min_lon"] = min(limites["min_lon"], lon)
                limites["max_lon"] = max(limites["max_lon"], lon)

            cor = cor_regional(evento.local.regiao)
            tooltip_text = f"{evento.nome} - {evento.local.nome} - Público estimado: {evento.publico_estimado}"
            popup_text = f"""
            <div data-track-entidade="evento" data-track-id="{evento.id}">
            <b>{evento.nome}</b><br>
            Descrição: {evento.descricao}<br>
            Data: {evento.data_inicio} a {evento.data_fim}<br>
            Público: {evento.publico_estimado}<br>
            Porte: {evento.porte}<br>
            Tipo: {evento.tipo_evento}<br>
            Local: {evento.local.nome}<br>
            {_telefone_html(evento.contato_telefone)}
            {_site_html_rastreado(evento.site_url, 'evento', evento.id)}
            {link_rota_html(lat, lon, map_name, evento.local.nome)}
            </div>
            """
            folium.Marker(
                location=[lat, lon],
                popup=popup_text,
                tooltip=tooltip_text,
                icon=folium.Icon(color=cor)
            ).add_to(cluster_eventos)
            eventos_mostrados += 1

        if EXIBIR_ANUNCIANTES_MAPA:
            total_anunciantes_ativos = 0
            for anunciante in anunciantes:
                if not anunciante_ativo_em_data(anunciante, data_referencia):
                    continue
                if not coordenadas_validas(anunciante.latitude, anunciante.longitude):
                    continue

                adicionar_marcador_anunciante(mapa, anunciante, map_name)
                total_anunciantes_ativos += 1

            mapa.get_root().html.add_child(
                folium.Element(painel_anunciantes_ativos_html(total_anunciantes_ativos))
            )

        # Adicionar "Sem regional" à lista se houver eventos sem regional
        if "Sem regional" in contagem_por_regional and "Sem regional" not in regionais:
            regionais.append("Sem regional")

        # Filtrar apenas regionais que têm eventos e incluir regionais presentes
        # nos dados mas ausentes na tabela de regionais.
        regionais_com_eventos = [r for r in regionais if r in contagem_por_regional]
        for regional in sorted(contagem_por_regional.keys()):
            if regional not in regionais_com_eventos:
                regionais_com_eventos.append(regional)

        cabecalho_legenda = f"Legenda - Regional ({eventos_mostrados} eventos)"
        mapa.get_root().html.add_child(
            folium.Element(
                legenda_mapa_html_interativa(
                    regionais=regionais_com_eventos,
                    cabecalho=cabecalho_legenda,
                    map_name=map_name,
                    bounds_por_regional=bounds_por_regional,
                    contagem_por_regional=contagem_por_regional,
                    exibir_contagem=EXIBIR_CONTAGEM_EVENTOS_MAPA,
                )
            )
        )
        return mapa.get_root().render()
    finally:
        db.close()


@app.get("/public/mapa", response_class=HTMLResponse)
def mapa_eventos_publico(request: Request):
    return mapa_eventos(request, _publico=True)


@app.get("/calendario", response_class=HTMLResponse)
def calendario_eventos(request: Request, tipo_evento: str = "Todos", _publico: bool = False):
    if not _publico:
        redirect = _redirect_se_nao_autenticado(request)
        if redirect:
            return redirect

    redirect_localidade = _redirect_se_localidade_nao_definida(request, _publico=_publico)
    if redirect_localidade:
        return redirect_localidade

    _, municipio_id = _obter_localidade_sessao(request, _publico=_publico)
    estado_id, _ = _obter_localidade_sessao(request, _publico=_publico)

    link_inicio = ""
    acao_filtro = "/calendario"
    if not _publico:
        link_inicio = botao_voltar_portal_html(extra_style='margin-right:auto;')
    else:
        acao_filtro = "/public/calendario"
        link_inicio = botao_voltar_portal_html(extra_style='margin-right:auto;')

    db: Session = SessionLocal()
    estados_db = db.query(Estado).order_by(Estado.nome).all()
    municipios_db = db.query(Municipio).order_by(Municipio.nome).all()
    label_loc = _label_localidade(estados_db, municipios_db, estado_id, municipio_id)
    locais = db.query(Local).filter(Local.municipio_id == municipio_id).all()
    tipo_evento_selecionado = "Todos"
    if tipo_evento in TIPOS_EVENTO:
        tipo_evento_selecionado = tipo_evento

    query_eventos = db.query(Evento).join(Local).filter(Local.municipio_id == municipio_id)
    if tipo_evento_selecionado != "Todos":
        query_eventos = query_eventos.filter(Evento.tipo_evento == tipo_evento_selecionado)
    eventos = query_eventos.all()
    regionais = [r.nome for r in db.query(Regional).order_by(Regional.nome).all()]

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
    cores = {regional: cor_regional(regional) for regional in regionais}
    legendas_html = "".join(
        [
            f'<div class="regiao-box" style="background-color: {cor_regional(regional)};">Regional {escape(regional)}</div>'
            for regional in regionais
        ]
    )

    logo_html = ""
    if EXIBIR_LOGO and LOGO_URL:
        logo_html = f'<img class="logo" src="{escape(LOGO_URL)}" alt="Logo">'

    label_loc_escaped = escape(label_loc)

    html = """
    <html>
    <head>
            <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Calendário de Eventos - {LABEL_LOC}</title>
        <script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"></script>
        <style>
            body { font-family: Arial, sans-serif; }
            .toolbar { margin: 10px 20px; display: flex; justify-content: flex-end; align-items: center; gap: 10px; }
            .toolbar label { font-weight: 700; color: #111827; }
            .toolbar select { padding: 8px 10px; border-radius: 8px; border: 1px solid #d1d5db; }
            .btn-exportar { padding: 10px 14px; border-radius: 8px; border: none; background: #166534; color: #fff; font-weight: 700; cursor: pointer; }
            .btn-exportar:hover { background: #14532d; }
            .header { display: flex; align-items: center; gap: 20px; margin: 20px; position: relative; }
            .logo { width: 150px; height: 150px; }
            .header h1 { margin: 0 auto 0 10px; flex: 1; text-align: left; }
            .filtro-wrap { margin: 10px 20px 0 20px; display: flex; align-items: center; gap: 10px; }
            .filtro-wrap label { font-weight: bold; }
            .filtro-wrap select { padding: 8px 10px; border-radius: 6px; border: 1px solid #ccc; min-width: 170px; }
            .filtro-wrap button { padding: 8px 14px; border-radius: 6px; border: none; background: #1f2937; color: #fff; font-weight: 600; cursor: pointer; }
            .filtro-wrap button:hover { background: #111827; }
            .legenda { display: flex; gap: 10px; justify-content: center; margin: 20px 0; }
            .regiao-box { padding: 10px 20px; border-radius: 5px; color: white; font-weight: bold; }
            .infra-icons { margin-top: 8px; display: flex; flex-direction: column; gap: 4px; }
            .infra-tag { display: inline-flex; align-items: center; gap: 6px; background: rgba(255,255,255,0.2); border-radius: 4px; padding: 2px 6px; font-size: 12px; }
            table { border-collapse: collapse; width: 100%; margin: 20px; font-size: 14px; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; vertical-align: top; }
            th { background-color: #f2f2f2; font-size: 16px; }
            .evento { margin: 2px 0; padding: 2px; border-radius: 3px; }
        </style>
    </head>
    <body>
        <div class="toolbar">
            {link_inicio}
            <label for="formato_exportacao">Formato:</label>
            <select id="formato_exportacao">
                <option value="16x9" selected>16:9 paisagem</option>
                <option value="a4">A4 paisagem</option>
            </select>
            <button type="button" class="btn-exportar" onclick="exportarCalendarioJPG()">Salvar calendário como JPG</button>
        </div>
        <div id="calendario-exportavel">
        <div class="header">
            {logo_html}
            <h1>Calendário de Eventos de {LABEL_LOC}</h1>
        </div>
        <form class="filtro-wrap" method="get" action="{acao_filtro}">
            <label for="tipo_evento">Tipo de evento:</label>
            <select name="tipo_evento" id="tipo_evento">
                {opcoes_tipo_evento_html}
            </select>
            <button type="submit">Filtrar</button>
        </form>
        <div class="legenda">
            {legendas_html}
        </div>
        <table>
            <tr>
                <th>Local</th>
    """
    html = html.replace("{legendas_html}", legendas_html)
    html = html.replace("{logo_html}", logo_html)
    html = html.replace("{link_inicio}", link_inicio)
    html = html.replace("{acao_filtro}", acao_filtro)
    html = html.replace("{LABEL_LOC}", label_loc_escaped)

    opcoes_tipo_evento_html = '<option value="Todos">Todos</option>'
    for tipo in TIPOS_EVENTO:
        selected = " selected" if tipo == tipo_evento_selecionado else ""
        opcoes_tipo_evento_html += f'<option value="{tipo}"{selected}>{tipo}</option>'
    html = html.replace("{opcoes_tipo_evento_html}", opcoes_tipo_evento_html)

    # Cabeçalhos dos meses
    for ano_mes, mes in meses_ordenados:
        nome_mes = meses_pt[mes]
        html += f"<th style='text-align: center;'>{nome_mes} {ano_mes}</th>"
    html += "</tr>"

    # Linhas dos locais
    for local in locais:
        cor_regiao = cores.get(local.regiao, "gray")
        tipo_local_html = f'<div class="infra-icons"><span class="infra-tag" title="Tipo principal do local">🏷️ {escape(normalizar_tipo_evento(local.tipo_evento))}</span></div>'
        acessibilidade_html = ""
        proximo_metro_html = ""
        restaurantes_html = ""
        if bool(local.acessibilidade):
            acessibilidade_html = '<span class="infra-tag" title="Acessibilidade disponível">♿ Acessível</span>'
        if bool(local.proximo_metro):
            proximo_metro_html = '<span class="infra-tag" title="Próximo ao metrô">🚇 Metrô próximo</span>'
        if bool(local.restaurantes):
            restaurantes_html = '<span class="infra-tag" title="Possui restaurantes no local">🍽️ Restaurantes</span>'

        infra_local_html = ""
        if acessibilidade_html or proximo_metro_html or restaurantes_html:
            infra_local_html = f'<div class="infra-icons">{acessibilidade_html}{proximo_metro_html}{restaurantes_html}</div>'

        html += f"<tr><td style='background-color: {cor_regiao}; color: white; vertical-align: top;'><b>{local.nome}</b><br><small>({local.regiao})</small>{tipo_local_html}{infra_local_html}</td>"
        
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

    html += "</table></div>"
    html += """
    <script>
        async function exportarCalendarioJPG() {
            const area = document.getElementById('calendario-exportavel');
            if (!area || typeof html2canvas === 'undefined') {
                alert('Não foi possível gerar a imagem agora.');
                return;
            }

            const canvas = await html2canvas(area, {
                scale: 2,
                useCORS: true,
                backgroundColor: '#ffffff'
            });

            // Força saída em paisagem no formato escolhido.
            const formato = (document.getElementById('formato_exportacao') || {}).value || '16x9';
            const proporcao = formato === 'a4' ? (1.4142) : (16 / 9);

            const origemLargura = canvas.width;
            const origemAltura = canvas.height;
            let saidaLargura = origemLargura;
            let saidaAltura = Math.round(saidaLargura / proporcao);

            if (saidaAltura < origemAltura) {
                saidaAltura = origemAltura;
                saidaLargura = Math.round(saidaAltura * proporcao);
            }

            const canvasPaisagem = document.createElement('canvas');
            canvasPaisagem.width = saidaLargura;
            canvasPaisagem.height = saidaAltura;
            const ctx = canvasPaisagem.getContext('2d');
            ctx.fillStyle = '#ffffff';
            ctx.fillRect(0, 0, saidaLargura, saidaAltura);

            const escala = Math.min(saidaLargura / origemLargura, saidaAltura / origemAltura);
            const larguraRender = origemLargura * escala;
            const alturaRender = origemAltura * escala;
            const offsetX = (saidaLargura - larguraRender) / 2;
            const offsetY = (saidaAltura - alturaRender) / 2;
            ctx.drawImage(canvas, offsetX, offsetY, larguraRender, alturaRender);

            const link = document.createElement('a');
            const dataAtual = new Date().toISOString().slice(0, 10);
            link.download = `calendario-eventos-${dataAtual}.jpg`;
            link.href = canvasPaisagem.toDataURL('image/jpeg', 0.95);
            link.click();
        }
    </script>
    </body>
    </html>
    """
    return html


@app.get("/public/calendario", response_class=HTMLResponse)
def calendario_eventos_publico(request: Request, tipo_evento: str = "Todos"):
    return calendario_eventos(request, tipo_evento=tipo_evento, _publico=True)


@app.get("/public/visualizacao", response_class=HTMLResponse)
def visualizacao_publica(request: Request):
    redirect_localidade = _redirect_se_localidade_nao_definida(request, _publico=True)
    if redirect_localidade:
        return redirect_localidade

    db: Session = SessionLocal()
    try:
        estados = db.query(Estado).order_by(Estado.nome).all()
        municipios = db.query(Municipio).join(Estado).order_by(Estado.nome, Municipio.nome).all()
    finally:
        db.close()

    estado_sel, municipio_sel = _obter_localidade_sessao(request, _publico=True)
    label_loc = _label_localidade(estados, municipios, estado_sel, municipio_sel)
    label_loc_escaped = escape(label_loc)
    estados_options = "".join(
        [
            f'<option value="{e.id}" {"selected" if e.id == estado_sel else ""}>{escape(_rotulo_estado(e))}</option>'
            for e in estados
        ]
    )
    municipios_options = "".join(
        [
            f'<option value="{m.id}" data-estado-id="{m.estado_id}" {"selected" if m.id == municipio_sel else ""}>{escape(m.nome)}</option>'
            for m in municipios
        ]
    )

    html = """
    <html>
    <head>
        <title>Visualização de Eventos - __LABEL_LOC__</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <style>
            :root {
                --bg: #eef2f5;
                --card: #ffffff;
                --line: #d7dee5;
                --text: #0e2233;
                --muted: #5c6f7f;
                --accent: #0b4d68;
                --accent-2: #0a7e88;
                --accent-soft: #e8f4f6;
                --shadow: 0 14px 34px rgba(12, 42, 58, 0.15);
            }

            * { box-sizing: border-box; }

            html, body {
                margin: 0;
                padding: 0;
                width: 100%;
                height: 100%;
                font-family: "Avenir Next", "Trebuchet MS", "Gill Sans", sans-serif;
                background: radial-gradient(circle at 9% 12%, #ffffff 0, #f1f5f7 42%, #e4ebf1 100%);
                color: var(--text);
            }

            .layout {
                display: grid;
                grid-template-columns: 290px 1fr;
                min-height: 100vh;
                transition: grid-template-columns 0.35s ease;
                position: relative;
            }

            .layout.retracted {
                grid-template-columns: 0 1fr;
            }

            .sidebar {
                background: linear-gradient(180deg, #103a52 0%, #0c546f 65%, #117a8b 100%);
                color: #fff;
                padding: 22px 16px;
                border-right: 1px solid rgba(255, 255, 255, 0.16);
                box-shadow: var(--shadow);
                overflow: hidden;
                transition: transform 0.35s ease, opacity 0.35s ease, padding 0.35s ease;
                z-index: 30;
                backdrop-filter: blur(2px);
            }

            .layout.retracted .sidebar {
                opacity: 0;
                padding-left: 0;
                padding-right: 0;
                transform: translateX(-18px);
                pointer-events: none;
            }

            .brand {
                font-size: 1.2rem;
                font-weight: 800;
                letter-spacing: 0.35px;
                text-transform: uppercase;
            }

            .menu-btn {
                width: 100%;
                margin-bottom: 10px;
                border: 1px solid rgba(255, 255, 255, 0.22);
                border-radius: 12px;
                padding: 12px 14px;
                text-align: left;
                color: #fff;
                background: rgba(255, 255, 255, 0.11);
                font-size: 0.95rem;
                font-weight: 700;
                cursor: pointer;
                transition: transform 0.15s ease, background-color 0.2s ease, border-color 0.2s ease;
            }

            .menu-btn:hover {
                background: rgba(255, 255, 255, 0.2);
                transform: translateX(2px);
                border-color: rgba(255, 255, 255, 0.45);
            }

            .menu-btn.active {
                background: #fff;
                color: #0b455d;
                border-color: #fff;
                box-shadow: 0 6px 18px rgba(10, 30, 42, 0.18);
            }

            .content {
                display: grid;
                grid-template-rows: auto 1fr;
                min-width: 0;
                padding: 18px;
                gap: 12px;
            }

            .topbar {
                display: flex;
                align-items: center;
                gap: 10px;
                padding: 10px 12px;
                border: 1px solid var(--line);
                border-radius: 14px;
                background: rgba(255, 255, 255, 0.72);
                backdrop-filter: blur(4px);
            }

            .localidade-switch { display: flex; gap: 8px; margin-left: auto; align-items: center; }
            .localidade-switch select { padding: 7px; border-radius: 8px; border: 1px solid #cbd5e1; min-width: 140px; }
            .localidade-switch button { border: none; border-radius: 8px; padding: 8px 10px; background: #0f766e; color: #fff; font-weight: 700; cursor: pointer; }

            .back-btn {
                border: 1px solid #c7d4df;
                border-radius: 10px;
                background: linear-gradient(180deg, #ffffff 0%, #f4f7f9 100%);
                color: #17374b;
                font-weight: 700;
                padding: 9px 14px;
                cursor: pointer;
                transition: transform 0.15s ease;
            }

            .back-btn:hover {
                transform: translateY(-1px);
            }

            .title {
                font-size: 1rem;
                font-weight: 700;
                color: #123448;
                letter-spacing: 0.2px;
            }

            .frame-wrap {
                min-height: 70vh;
                background: var(--card);
                border: 1px solid var(--line);
                border-radius: 16px;
                box-shadow: 0 10px 24px rgba(12, 42, 58, 0.09);
                overflow: hidden;
                position: relative;
                animation: frameIn 0.35s ease;
            }

            .intro {
                display: grid;
                place-items: center;
                min-height: 70vh;
                padding: 28px;
                text-align: center;
                color: var(--muted);
                font-weight: 700;
                font-size: 1.02rem;
                line-height: 1.5;
                background:
                    radial-gradient(circle at 78% 8%, rgba(17, 122, 139, 0.1) 0, transparent 52%),
                    radial-gradient(circle at 14% 84%, rgba(12, 84, 111, 0.1) 0, transparent 45%),
                    #fff;
            }

            @keyframes frameIn {
                from {
                    opacity: 0;
                    transform: translateY(4px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }

            #viewer {
                width: 100%;
                height: 100%;
                min-height: 70vh;
                border: 0;
                display: block;
            }

            @media (max-width: 900px) {
                .layout {
                    display: block;
                    position: relative;
                    min-height: 100vh;
                }

                .sidebar {
                    position: fixed;
                    top: 0;
                    left: 0;
                    width: 82vw;
                    max-width: 320px;
                    height: 100vh;
                    border-right: 1px solid rgba(255, 255, 255, 0.2);
                }

                .layout:not(.retracted)::after {
                    content: "";
                    position: fixed;
                    inset: 0;
                    background: rgba(5, 22, 31, 0.28);
                    z-index: 20;
                }

                .layout.retracted .sidebar {
                    transform: translateX(-105%);
                    opacity: 1;
                    pointer-events: none;
                }

                .content {
                    padding: 10px;
                    position: relative;
                    z-index: 10;
                }

                .frame-wrap,
                .intro,
                #viewer {
                    min-height: calc(100vh - 94px);
                }

                .title {
                    font-size: 0.95rem;
                }

                .localidade-switch { flex-wrap: wrap; width: 100%; margin-left: 0; }
            }
        </style>
    </head>
    <body>
        <div id="layout" class="layout">
            <aside id="sidebar" class="sidebar">
                <div class="brand">Visualização Eventos - __LABEL_LOC__</div>
                <button class="menu-btn" data-menu-item onclick="abrirConteudo('/public/mapa', 'Mapa de eventos', this)">Mapa de Eventos</button>
                <button class="menu-btn" data-menu-item onclick="abrirConteudo('/public/mapa-locais', 'Mapa de locais', this)">Mapa de locais</button>
                <button class="menu-btn" data-menu-item onclick="abrirConteudo('/public/calendario', 'Calendário de eventos', this)">Calendário de Eventos</button>
            </aside>

            <main class="content">
                <div class="topbar">
                    <button class="back-btn" id="btnVoltar" onclick="mostrarMenu()" style="display:none;">Voltar</button>
                    <div class="title" id="tituloAtual">Selecione um item no menu lateral</div>
                    <form class="localidade-switch" method="post" action="/public/localidade">
                        <input type="hidden" name="next" value="/public/visualizacao" />
                        <select id="public_estado_id" name="estado_id" onchange="filtrarMunicipios('public_estado_id','public_municipio_id')" required>
                            __ESTADOS_OPTIONS__
                        </select>
                        <select id="public_municipio_id" name="municipio_id" required>
                            __MUNICIPIOS_OPTIONS__
                        </select>
                        <button type="submit">Mudar</button>
                    </form>
                </div>
                <div class="frame-wrap" id="frameWrap">
                    <div class="intro" id="intro">Escolha Mapa ou Calendário no menu lateral.</div>
                    <iframe id="viewer" src="about:blank" title="Visualização pública" style="display:none;"></iframe>
                </div>
            </main>
        </div>

        <script>
            const layout = document.getElementById('layout');
            const viewer = document.getElementById('viewer');
            const intro = document.getElementById('intro');
            const btnVoltar = document.getElementById('btnVoltar');
            const tituloAtual = document.getElementById('tituloAtual');
            const menuItems = Array.from(document.querySelectorAll('[data-menu-item]'));

            function abrirConteudo(url, titulo, el) {
                viewer.src = url;
                viewer.style.display = 'block';
                intro.style.display = 'none';
                layout.classList.add('retracted');
                btnVoltar.style.display = 'inline-block';
                tituloAtual.textContent = titulo;
                menuItems.forEach((item) => item.classList.remove('active'));
                if (el) {
                    el.classList.add('active');
                }
            }

            function mostrarMenu() {
                layout.classList.remove('retracted');
                btnVoltar.style.display = 'none';
                tituloAtual.textContent = 'Selecione um item no menu lateral';
            }

            function filtrarMunicipios(estadoSelectId, municipioSelectId) {
                const estado = document.getElementById(estadoSelectId);
                const municipio = document.getElementById(municipioSelectId);
                if (!municipio) return;

                if (!municipio._allOptions) {
                    municipio._allOptions = Array.from(municipio.options).map((opt) => ({
                        value: opt.value,
                        text: opt.text,
                        dono: opt.getAttribute('data-estado-id') || ''
                    }));
                }

                const estadoId = estado ? estado.value : '';
                const valorAtual = municipio.value;
                const opcoesFiltradas = municipio._allOptions.filter((opt) => !estadoId || !opt.dono || opt.dono === estadoId);

                municipio.innerHTML = '';
                opcoesFiltradas.forEach((opt) => {
                    const optionEl = document.createElement('option');
                    optionEl.value = opt.value;
                    optionEl.text = opt.text;
                    if (opt.dono) {
                        optionEl.setAttribute('data-estado-id', opt.dono);
                    }
                    municipio.appendChild(optionEl);
                });

                const aindaExiste = opcoesFiltradas.some((opt) => opt.value === valorAtual);
                if (aindaExiste) {
                    municipio.value = valorAtual;
                } else if (municipio.options.length) {
                    municipio.selectedIndex = 0;
                }
            }

            filtrarMunicipios('public_estado_id', 'public_municipio_id');
        </script>
    </body>
    </html>
    """

    html = html.replace("__ESTADOS_OPTIONS__", estados_options)
    html = html.replace("__MUNICIPIOS_OPTIONS__", municipios_options)
    html = html.replace("__LABEL_LOC__", label_loc_escaped)
    return html


@app.get("/public/portal", response_class=HTMLResponse)
def portal_publico(request: Request):
    db: Session = SessionLocal()
    try:
        estados = db.query(Estado).order_by(Estado.nome).all()
        municipios = db.query(Municipio).join(Estado).order_by(Estado.nome, Municipio.nome).all()
    finally:
        db.close()

    estado_sel, municipio_sel = _obter_localidade_sessao(request, _publico=True)
    label_loc = _label_localidade(estados, municipios, estado_sel, municipio_sel)
    label_loc_escaped = escape(label_loc)

    estados_options = "".join(
        [
            f'<option value="{e.id}" {"selected" if e.id == estado_sel else ""}>{escape(_rotulo_estado(e))}</option>'
            for e in estados
        ]
    )
    municipios_options = "".join(
        [
            f'<option value="{m.id}" data-estado-id="{m.estado_id}" {"selected" if m.id == municipio_sel else ""}>{escape(m.nome)}</option>'
            for m in municipios
        ]
    )

    hoje = datetime.now().date()
    inicio_mes = date(hoje.year, hoje.month, 1)
    fim_mes = date(hoje.year, hoje.month, calendar.monthrange(hoje.year, hoje.month)[1])

    eventos_mes = []
    if municipio_sel:
        db = SessionLocal()
        try:
            eventos_mes = (
                db.query(
                    Evento.nome,
                    Evento.descricao,
                    Evento.data_inicio,
                    Evento.data_fim,
                    Evento.tipo_evento,
                    Evento.publico_estimado,
                    Local.nome.label("local_nome"),
                )
                .join(Local)
                .filter(
                    Local.municipio_id == municipio_sel,
                    Evento.data_inicio <= fim_mes,
                    Evento.data_fim >= inicio_mes,
                )
                .order_by(Evento.data_inicio.asc(), Evento.nome.asc())
                .all()
            )
        finally:
            db.close()

    slides_html = ""
    if eventos_mes:
        for evento in eventos_mes:
            nome = escape(evento.nome or "Sem nome")
            descricao = escape((evento.descricao or "").strip())
            descricao_curta = (descricao[:140] + "...") if len(descricao) > 140 else descricao
            periodo = f"{evento.data_inicio.strftime('%d/%m')} a {evento.data_fim.strftime('%d/%m')}"
            local_nome = escape(evento.local_nome or "Local não informado")
            tipo = escape(normalizar_tipo_evento(evento.tipo_evento))
            publico = evento.publico_estimado or 0
            slides_html += f"""
            <article class="carousel-item">
                <div class="chip">{tipo}</div>
                <h3>{nome}</h3>
                <p class="meta">{periodo} · {local_nome}</p>
                <p>{descricao_curta or 'Programação em atualização.'}</p>
                <p class="meta">Público estimado: {publico}</p>
            </article>
            """
    else:
        slides_html = """
        <article class="carousel-item">
            <div class="chip">Agenda</div>
            <h3>Nenhum evento previsto neste mês</h3>
            <p class="meta">Ajuste a localidade para explorar outra cidade.</p>
            <p>Quando houver novos eventos no mês corrente, eles aparecerão aqui automaticamente.</p>
        </article>
        """

    user = _usuario_atual(request)
    auth_portal = request.query_params.get("auth") == "1"
    if auth_portal and user:
        request.session["portal_admin_autenticado"] = True
    if not user:
        request.session.pop("portal_admin_autenticado", None)

    is_logado = bool(user) and bool(request.session.get("portal_admin_autenticado"))
    is_admin = _eh_admin_ou_super_admin(user) if is_logado else False
    is_super_admin = _eh_super_admin(user) if is_logado else False
    user_name = escape(user.get("name") or "") if is_logado else ""

    itens_menu = [
        '<a class="menu-link" href="/public/mapa">Mapa de Eventos</a>',
        '<a class="menu-link" href="/public/mapa-locais">Mapa de Locais</a>',
        '<a class="menu-link" href="/public/calendario">Calendário</a>',
    ]

    if is_admin:
        itens_menu.extend(
            [
                '<div class="menu-sep"></div>',
                '<a class="menu-link" href="/usuarios">Usuários</a>',
                '<a class="menu-link" href="/board-interacoes">Board de Interações</a>',
                '<a class="menu-link" href="/cadastro">Cadastro</a>',
                '<a class="menu-link" href="/manutencao">Manutenção</a>',
                '<a class="menu-link" href="/estados">Estados</a>',
                '<a class="menu-link" href="/municipios">Municípios</a>',
            ]
        )
        if is_super_admin:
            itens_menu.extend(
                [
                    '<a class="menu-link" href="/anunciantes">Anunciantes</a>',
                    '<a class="menu-link" href="/configuracoes">Configurações</a>',
                ]
            )
        itens_menu.append('<a class="menu-link logout" href="/logout?next=/public/portal">Sair</a>')
    else:
        itens_menu.extend(
            [
                '<div class="menu-sep"></div>',
                '<a class="menu-link login" href="/login?next=/public/portal?auth=1">Login administrativo</a>',
            ]
        )

    menu_html = "".join(itens_menu)
    saudacao = f"Conectado como: {user_name}" if is_logado else "Acesso público"

    return f"""
    <html>
    <head>
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
        <title>Portal Público de Eventos - {label_loc_escaped}</title>
        <style>
            :root {{
                --bg: #f3f7fb;
                --ink: #0f172a;
                --muted: #475569;
                --line: #d7e2ee;
                --brand: #0f766e;
                --brand-strong: #0b5f58;
                --sun: #f59e0b;
            }}
            * {{ box-sizing: border-box; }}
            body {{
                margin: 0;
                font-family: "Avenir Next", "Trebuchet MS", "Gill Sans", sans-serif;
                color: var(--ink);
                background: radial-gradient(circle at 9% 8%, #ffffff 0, #eef4f9 48%, #e5eef7 100%);
            }}
            .page {{ max-width: 1100px; margin: 0 auto; padding: 22px 18px 90px; }}
            .hero {{
                background: linear-gradient(120deg, #0f766e 0%, #0b4d68 100%);
                color: #fff;
                border-radius: 18px;
                padding: 20px;
                box-shadow: 0 14px 34px rgba(11, 77, 104, 0.24);
            }}
            .hero h1 {{ margin: 0 0 8px; font-size: 1.6rem; }}
            .hero p {{ margin: 0; opacity: 0.95; }}
            .status {{ margin-top: 8px; font-size: 0.92rem; opacity: 0.95; }}

            .contexto {{
                margin-top: 16px;
                display: grid;
                grid-template-columns: 1fr 1fr auto;
                gap: 10px;
                align-items: end;
                background: #fff;
                border: 1px solid var(--line);
                border-radius: 14px;
                padding: 14px;
            }}
            .contexto label {{ display: block; font-size: 0.82rem; font-weight: 700; color: #334155; margin-bottom: 4px; }}
            .contexto select {{ width: 100%; padding: 9px; border-radius: 8px; border: 1px solid #cbd5e1; }}
            .contexto button {{ border: 0; border-radius: 10px; padding: 10px 12px; color: #fff; background: var(--brand); font-weight: 700; cursor: pointer; }}
            .contexto button:hover {{ background: var(--brand-strong); }}

            .section-title {{ margin: 24px 0 12px; font-size: 1.2rem; color: #0f172a; }}
            .carousel-shell {{
                position: relative;
                border: 1px solid var(--line);
                background: #fff;
                border-radius: 16px;
                overflow: hidden;
                box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
            }}
            .carousel-track {{
                display: flex;
                transition: transform 0.35s ease;
                width: 100%;
            }}
            .carousel-item {{
                flex: 0 0 100%;
                padding: 18px;
                min-height: 220px;
                background:
                    radial-gradient(circle at 90% 12%, rgba(15,118,110,0.08) 0, transparent 40%),
                    radial-gradient(circle at 10% 86%, rgba(245,158,11,0.10) 0, transparent 44%),
                    #fff;
            }}
            .carousel-item h3 {{ margin: 8px 0; font-size: 1.25rem; }}
            .carousel-item p {{ margin: 6px 0; color: var(--muted); }}
            .chip {{
                display: inline-block;
                padding: 4px 10px;
                border-radius: 999px;
                font-size: 0.75rem;
                font-weight: 800;
                letter-spacing: 0.3px;
                background: #e2f3f1;
                color: #0b5f58;
                border: 1px solid #b7e3df;
            }}
            .meta {{ font-size: 0.9rem; color: #334155; }}

            .carousel-nav {{
                position: absolute;
                inset: auto 0 12px 0;
                display: flex;
                justify-content: center;
                gap: 10px;
            }}
            .carousel-btn {{
                border: 0;
                border-radius: 999px;
                width: 34px;
                height: 34px;
                font-weight: 900;
                cursor: pointer;
                color: #fff;
                background: rgba(15, 23, 42, 0.7);
            }}

            .fab {{
                position: fixed;
                left: 16px;
                top: 16px;
                z-index: 99;
                border: 0;
                border-radius: 999px;
                width: 58px;
                height: 58px;
                background: linear-gradient(140deg, #0f766e, #0b4d68);
                color: #fff;
                font-size: 1.4rem;
                font-weight: 900;
                cursor: pointer;
                box-shadow: 0 14px 26px rgba(11, 77, 104, 0.32);
            }}
            .floating-menu {{
                position: fixed;
                left: 16px;
                top: 84px;
                width: min(340px, calc(100vw - 32px));
                max-height: 70vh;
                overflow: auto;
                border-radius: 16px;
                border: 1px solid #c7d8e6;
                background: #fff;
                padding: 12px;
                box-shadow: 0 20px 40px rgba(15, 23, 42, 0.22);
                z-index: 98;
                opacity: 0;
                transform: translateY(10px) scale(0.98);
                pointer-events: none;
                transition: opacity 0.2s ease, transform 0.2s ease;
            }}
            .floating-menu.open {{
                opacity: 1;
                transform: translateY(0) scale(1);
                pointer-events: auto;
            }}
            .floating-menu h2 {{ margin: 0 0 10px; font-size: 1rem; color: #0f172a; }}
            .menu-link {{
                display: block;
                text-decoration: none;
                color: #0f172a;
                background: #f8fbff;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                padding: 9px 10px;
                font-weight: 700;
                margin-bottom: 8px;
            }}
            .menu-link:hover {{ background: #eef6ff; }}
            .menu-link.login {{ background: #ecfeff; border-color: #b9ecf1; color: #0f766e; }}
            .menu-link.logout {{ background: #fff1f2; border-color: #fecdd3; color: #9f1239; }}
            .menu-sep {{ height: 1px; background: #dbe5ef; margin: 10px 0; }}

            @media (max-width: 860px) {{
                .contexto {{ grid-template-columns: 1fr; }}
            }}
        </style>
    </head>
    <body>
        <div class="page">
            <section class="hero">
                <h1>Portal Público de Eventos</h1>
                <p>Explore agenda, mapas e calendário de forma rápida para a localidade selecionada.</p>
                <div class="status">{saudacao} · Contexto atual: <b>{label_loc_escaped}</b></div>
            </section>

            <form class="contexto" method="post" action="/public/localidade">
                <input type="hidden" name="next" value="/public/portal" />
                <div>
                    <label for="portal_estado_id">Estado</label>
                    <select id="portal_estado_id" name="estado_id" onchange="filtrarMunicipios('portal_estado_id','portal_municipio_id')" required>
                        {estados_options}
                    </select>
                </div>
                <div>
                    <label for="portal_municipio_id">Município</label>
                    <select id="portal_municipio_id" name="municipio_id" required>
                        {municipios_options}
                    </select>
                </div>
                <button type="submit">Aplicar contexto</button>
            </form>

            <h2 class="section-title">Eventos do mês corrente em {label_loc_escaped}</h2>
            <section class="carousel-shell" aria-label="Carrossel de eventos do mês">
                <div class="carousel-track" id="carouselTrack">
                    {slides_html}
                </div>
                <div class="carousel-nav">
                    <button class="carousel-btn" type="button" onclick="mudarSlide(-1)" aria-label="Slide anterior">‹</button>
                    <button class="carousel-btn" type="button" onclick="mudarSlide(1)" aria-label="Próximo slide">›</button>
                </div>
            </section>
        </div>

        <button id="fabMenu" class="fab" type="button" aria-label="Abrir menu">☰</button>
        <nav id="floatingMenu" class="floating-menu" aria-label="Menu flutuante">
            <h2>Navegação</h2>
            {menu_html}
        </nav>

        <script>
            const fabMenu = document.getElementById('fabMenu');
            const floatingMenu = document.getElementById('floatingMenu');
            fabMenu.addEventListener('click', function() {{
                floatingMenu.classList.toggle('open');
            }});
            document.addEventListener('click', function(event) {{
                if (!floatingMenu.contains(event.target) && event.target !== fabMenu) {{
                    floatingMenu.classList.remove('open');
                }}
            }});

            function filtrarMunicipios(estadoSelectId, municipioSelectId) {{
                const estado = document.getElementById(estadoSelectId);
                const municipio = document.getElementById(municipioSelectId);
                if (!municipio) return;

                if (!municipio._allOptions) {{
                    municipio._allOptions = Array.from(municipio.options).map((opt) => ({{
                        value: opt.value,
                        text: opt.text,
                        dono: opt.getAttribute('data-estado-id') || ''
                    }}));
                }}

                const estadoId = estado ? estado.value : '';
                const valorAtual = municipio.value;
                const opcoesFiltradas = municipio._allOptions.filter((opt) => !estadoId || !opt.dono || opt.dono === estadoId);

                municipio.innerHTML = '';
                opcoesFiltradas.forEach((opt) => {{
                    const optionEl = document.createElement('option');
                    optionEl.value = opt.value;
                    optionEl.text = opt.text;
                    if (opt.dono) {{
                        optionEl.setAttribute('data-estado-id', opt.dono);
                    }}
                    municipio.appendChild(optionEl);
                }});

                const aindaExiste = opcoesFiltradas.some((opt) => opt.value === valorAtual);
                if (aindaExiste) {{
                    municipio.value = valorAtual;
                }} else if (municipio.options.length) {{
                    municipio.selectedIndex = 0;
                }}
            }}

            filtrarMunicipios('portal_estado_id', 'portal_municipio_id');

            const track = document.getElementById('carouselTrack');
            const totalSlides = track ? track.children.length : 0;
            let slideAtual = 0;
            let timerCarousel = null;

            function atualizarCarousel() {{
                if (!track || totalSlides <= 0) return;
                track.style.transform = `translateX(${{-slideAtual * 100}}%)`;
            }}

            function mudarSlide(delta) {{
                if (totalSlides <= 1) return;
                slideAtual = (slideAtual + delta + totalSlides) % totalSlides;
                atualizarCarousel();
                reiniciarAutoCarousel();
            }}

            function reiniciarAutoCarousel() {{
                if (timerCarousel) clearInterval(timerCarousel);
                if (totalSlides <= 1) return;
                timerCarousel = setInterval(function() {{
                    slideAtual = (slideAtual + 1) % totalSlides;
                    atualizarCarousel();
                }}, 5000);
            }}

            atualizarCarousel();
            reiniciarAutoCarousel();
        </script>
    </body>
    </html>
    """