from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from .database import SessionLocal, engine, Base
from .models import Evento, Local, Regional
from authlib.integrations.starlette_client import OAuth, OAuthError
from dotenv import load_dotenv
from starlette.middleware.sessions import SessionMiddleware
import folium
from folium.plugins import MarkerCluster
import calendar
from datetime import datetime
from html import escape
from typing import Optional
import math
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")
ENV_FILE_PATH = BASE_DIR / ".env"

# Meses em português
meses_pt = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", 
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

Base.metadata.create_all(bind=engine)

TIPOS_EVENTO = ["Carnaval", "Negócios", "Turismo"]


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
        conn.execute(
            text(
                "UPDATE eventos SET tipo_evento = 'Negócios' WHERE tipo_evento IS NULL OR TRIM(tipo_evento) = ''"
            )
        )


garantir_colunas_locais()
garantir_colunas_eventos()

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


def legenda_mapa_html(regionais: list[str], cabecalho: str = "Legenda - Regional") -> str:
    itens = "".join(
        [
            f'<i style="background: {cor_regional(regional)}; width: 10px; height: 10px; display: inline-block;"></i> {escape(regional)}<br>'
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
    </style>
    <script>
        window.routeLayer_{map_name} = null;
        window.routeOriginMarker_{map_name} = null;
        window.routeDestinationMarker_{map_name} = null;
        window.selectedOrigin_{map_name} = null;

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

                window.routeLayer_{map_name} = L.polyline(coordinates, {{
                    color: '#2563eb',
                    weight: 5,
                    opacity: 0.85
                }}).addTo(mapa);

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

        setTimeout(adicionarControleLimparRota_{map_name}, 0);
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
) -> str:
    map_name_json = json.dumps(map_name)
    itens = []
    for regional in regionais:
        estilo_ponto = (
            f'background: {cor_regional(regional)}; width: 10px; height: 10px; '
            'display: inline-block; margin-right: 6px;'
        )
        if regional in bounds_por_regional:
            itens.append(
                f'<button type="button" class="legend-link" '
                f'onclick="zoomParaRegional_{map_name}({json.dumps(regional)})">'
                f'<i style="{estilo_ponto}"></i>{escape(regional)}</button>'
            )
        else:
            itens.append(
                f'<span class="legend-disabled"><i style="{estilo_ponto}"></i>{escape(regional)}</span>'
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


USUARIO_MESTRE = {
    "provider": "sistema",
    "id": "mestre",
    "name": "Administrador",
    "email": "admin@sistema.local",
    "admin": True,
}

EMAILS_ADMIN = {
    "vanderlucio.evaristo@gmail.com",
    "vanderlucioevaristo@gmail.com",
}

REQUIRE_LOGIN = os.getenv("REQUIRE_LOGIN", "true").lower() not in ("false", "0", "no")
EXIBIR_LOGO = os.getenv("EXIBIR_LOGO", "true").lower() not in ("false", "0", "no")
LOGO_URL = os.getenv(
    "LOGO_URL",
    "https://visitebelohorizonte.com/wp-content/uploads/2025/07/LOGO-1.svg",
).strip()


def _usuario_atual(request: Request) -> dict:
    """Retorna o usuário da sessão ou o mestre quando login não é exigido."""
    if not REQUIRE_LOGIN:
        return request.session.get("user") or USUARIO_MESTRE
    return request.session.get("user") or {}


def _eh_admin(user: dict) -> bool:
    if user.get("admin"):
        return True
    email = (user.get("email") or "").lower()
    return email in {e.lower() for e in EMAILS_ADMIN}


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
    if not _eh_admin(user):
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


@app.get("/configuracoes", response_class=HTMLResponse)
def pagina_configuracoes(request: Request, msg: Optional[str] = None):
    redirect = _redirect_se_nao_admin(request)
    if redirect:
        return redirect

    exibir_logo_checked = "checked" if EXIBIR_LOGO else ""
    logo_url_valor = escape(LOGO_URL or "")
    msg_html = ""
    if msg == "ok":
        msg_html = '<div class="msg ok">Configurações salvas com sucesso.</div>'
    elif msg == "erro":
        msg_html = '<div class="msg erro">Não foi possível salvar as configurações.</div>'

    return f"""
    <html>
    <head>
        <title>Configurações - Eventos BH</title>
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
            <div class="desc">Altere os parâmetros globais de exibição de logo do sistema.</div>
            {msg_html}
            <form method="post" action="/configuracoes">
                <label class="check">
                    <input type="checkbox" name="exibir_logo" value="1" {exibir_logo_checked} />
                    Exibir logo nas páginas que usam essa configuração
                </label>

                <label for="logo_url">URL do logo</label>
                <input id="logo_url" type="text" name="logo_url" value="{logo_url_valor}" placeholder="https://..." />

                <div class="actions">
                    <button class="btn btn-primary" type="submit">Salvar</button>
                    <a class="btn btn-secondary" href="/">Voltar</a>
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
    logo_url: str = Form(""),
):
    redirect = _redirect_se_nao_admin(request)
    if redirect:
        return redirect

    global EXIBIR_LOGO, LOGO_URL

    try:
        novo_exibir_logo = bool(exibir_logo)
        nova_logo_url = (logo_url or "").strip()

        _atualizar_variavel_env("EXIBIR_LOGO", "true" if novo_exibir_logo else "false")
        _atualizar_variavel_env("LOGO_URL", nova_logo_url)

        EXIBIR_LOGO = novo_exibir_logo
        LOGO_URL = nova_logo_url
        return RedirectResponse(url="/configuracoes?msg=ok", status_code=303)
    except Exception:
        return RedirectResponse(url="/configuracoes?msg=erro", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if not REQUIRE_LOGIN:
        return RedirectResponse(url="/", status_code=303)
    if request.session.get("user"):
        return RedirectResponse(url="/", status_code=303)

    auth_error = request.query_params.get("erro")
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
            f'<a class="btn" style="background:{cor};" href="/auth/{provedor}/login">'
            f'Entrar com {rotulo}</a>'
        )

    erro_html = ""
    if auth_error:
        erro_html = (
            '<div class="warn" style="background:#fee2e2;color:#991b1b;">'
            f'Falha ao autenticar com {escape(auth_error)}. '
            'Revise as credenciais e a URL de callback configurada.</div>'
        )

    if not botoes_html:
        botoes_html = (
            '<div class="warn">Nenhum provedor OAuth configurado. '
            'Defina variáveis GOOGLE_CLIENT_ID/SECRET, FACEBOOK_CLIENT_ID/SECRET '
            'ou APPLE_CLIENT_ID/SECRET.</div>'
        )

    google_config_html = ""
    if "google" not in provedores:
        google_config_html = (
            '<div class="setup">'
            '<strong>Google:</strong> configure no Google Cloud Console o redirect URI '
            f'<code>{escape(_oauth_redirect_uri(request, "google"))}</code> '
            'e preencha GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET no arquivo .env.'
            '</div>'
        )

    return f"""
    <html>
    <head>
        <title>Login - Eventos BH</title>
        <style>
            body {{ font-family: Arial, sans-serif; background: #f3f4f6; margin: 0; }}
            .wrap {{ min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 24px; }}
            .card {{ width: 100%; max-width: 420px; background: white; border-radius: 12px; padding: 28px; box-shadow: 0 14px 32px rgba(0,0,0,.12); }}
            h1 {{ margin: 0 0 8px; color: #111827; }}
            p {{ margin: 0 0 20px; color: #4b5563; }}
            .btn {{ display: block; color: white; text-decoration: none; font-weight: 700; text-align: center; padding: 11px 14px; border-radius: 8px; margin-bottom: 10px; }}
            .warn {{ background: #fef3c7; color: #92400e; border-radius: 8px; padding: 12px; font-size: 14px; }}
            .setup {{ margin-top: 14px; background: #eff6ff; color: #1e3a8a; border-radius: 8px; padding: 12px; font-size: 14px; line-height: 1.5; }}
            code {{ background: #dbeafe; padding: 2px 6px; border-radius: 6px; }}
        </style>
    </head>
    <body>
        <div class="wrap">
            <div class="card">
                <h1>Entrar no Eventos BH</h1>
                <p>Use uma conta social para acessar o sistema.</p>
                {erro_html}
                {botoes_html}
                {google_config_html}
            </div>
        </div>
    </body>
    </html>
    """


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@app.get("/auth/{provider}/login")
async def oauth_login(provider: str, request: Request):
    client = oauth.create_client(provider)
    if not client:
        return RedirectResponse(url="/login", status_code=303)

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

    try:
        token = await client.authorize_access_token(request)
    except OAuthError:
        return RedirectResponse(url=f"/login?erro={provider}", status_code=303)

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

    request.session["user"] = {
        "provider": provider,
        "id": profile.get("sub") or profile.get("id") or "",
        "name": profile.get("name") or profile.get("email") or "Usuário",
        "email": profile.get("email") or "",
    }
    return RedirectResponse(url="/", status_code=303)

#para executar 
# cd /Users/vanderevaristo/ProjetosVander/mapacaloreventos source .venv/bin/activate uvicorn mapaCalorEventos.app.main:app --reload
# python3 mapaCalorEventos/app/main.py

# uvicorn mapaCalorEventos.app.main:app --reload --port 8001
# .venv/bin/python -m mapaCalorEventos.app.seed

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    redirect = _redirect_se_nao_autenticado(request)
    if redirect:
        return redirect

    user = _usuario_atual(request)
    user_name = escape(user.get("name") or "Usuário")
    acesso_negado = request.query_params.get("acesso") == "negado"
    aviso_acesso_html = (
        '<div style="background:#fee2e2;color:#991b1b;padding:10px 16px;border-radius:8px;margin-bottom:16px;">'
        'Acesso restrito. Você não tem permissão para acessar essa área.</div>'
    ) if acesso_negado else ""
    is_admin = _eh_admin(user)
    return f"""
    <html>
    <head>
        <title>Eventos BH</title>
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
        </style>
    </head>
    <body>
        <div class="page">
            <div class="top">
                <h1>Eventos BH</h1>
                <span class="user">Conectado como: {user_name}</span>
                <a class="logout" href="/logout">Sair</a>
            </div>
            <p>Bem-vindo ao painel de eventos de Belo Horizonte. Use os menus abaixo para visualizar o mapa interativo dos eventos ou o calendário de programação.</p>
            {aviso_acesso_html}
            <div class="menu">
                <a class="card" href="/mapa">
                    <h2>Mapa de Eventos</h2>
                    <p>Visualize a localização de cada evento no mapa de Belo Horizonte com cores por região.</p>
                </a>
                <a class="card" href="/mapa-locais">
                    <h2>Mapa de Locais</h2>
                    <p>Veja no mapa todos os locais de evento cadastrados, organizados por região.</p>
                </a>
                <a class="card" href="/calendario">
                    <h2>Calendário de Eventos</h2>
                    <p>Veja os eventos organizados por local e mês em um calendário compacto e colorido.</p>
                </a>
                {'<a class="card" href="/configuracoes"><h2>Configurações</h2><p>Altere parâmetros globais de exibição, como logo e URL.</p></a>' if is_admin else ''}
                {'<a class="card" href="/cadastro"><h2>Cadastrar Evento/Local</h2><p>Inclua novos locais de execução e novos eventos diretamente pela tela.</p></a>' if is_admin else ''}
                {'<a class="card" href="/manutencao"><h2>Manutenção</h2><p>Edite ou exclua locais e eventos já cadastrados em uma tela dedicada.</p></a>' if is_admin else ''}
            </div>
            <div class="footer">Acesse o mapa ou o calendário para explorar os eventos cadastrados.</div>
        </div>
    </body>
    </html>
    """


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
        elif msg == "evento_ok":
            msg_html = '<div class="msg ok">Evento cadastrado com sucesso.</div>'
        elif msg == "local_edit_ok":
            msg_html = '<div class="msg ok">Local atualizado com sucesso.</div>'
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
        elif msg == "registro_nao_encontrado":
            msg_html = '<div class="msg erro">Registro não encontrado.</div>'

        locais_options = "".join(
            [f'<option value="{local.id}">{local.nome} ({local.regiao})</option>' for local in locais_todos]
        )

        locais_existentes_html = ""
        for local in locais:
            local_nome = escape(local.nome or "")
            local_endereco = escape(local.endereco or "")
            local_regiao = escape(local.regiao or "")
            local_tipo_evento = normalizar_tipo_evento(local.tipo_evento)
            local_acessibilidade_checked = "checked" if bool(local.acessibilidade) else ""
            local_proximo_metro_checked = "checked" if bool(local.proximo_metro) else ""
            local_restaurantes_checked = "checked" if bool(local.restaurantes) else ""
            locais_existentes_html += f"""
            <div class="item-row">
                <div class="item-name">{local_nome} <small>({escape(local_tipo_evento)})</small></div>
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

                        <label>Tipo de evento</label>
                        <select name="tipo_evento" required>
                            {"".join([f'<option value="{tipo}" {"selected" if tipo == local_tipo_evento else ""}>{tipo}</option>' for tipo in TIPOS_EVENTO])}
                        </select>

                        <label>Latitude</label>
                        <input type="number" step="any" name="latitude" value="{local.latitude}" required />

                        <label>Longitude</label>
                        <input type="number" step="any" name="longitude" value="{local.longitude}" required />

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

                            <label>Tipo de evento</label>
                            <select name="tipo_evento" required>
                                {"".join([f'<option value="{tipo}" {"selected" if tipo == "Negócios" else ""}>{tipo}</option>' for tipo in TIPOS_EVENTO])}
                            </select>

                            <label>Latitude</label>
                            <input type="number" step="any" name="latitude" required />

                            <label>Longitude</label>
                            <input type="number" step="any" name="longitude" required />

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
                .item-name {{ font-weight: 700; color: #1f2937; }}
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
                    <a class="back" href="/">Voltar para a página inicial</a>
                </div>
                {msg_html}
                {secoes_cadastro_html}
                {secoes_manutencao_html}
            </div>
            <script>
                function openModal(id) {{
                    var el = document.getElementById(id);
                    if (el) el.style.display = 'block';
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
    tipo_evento: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    acessibilidade: Optional[str] = Form(None),
    proximo_metro: Optional[str] = Form(None),
    restaurantes: Optional[str] = Form("1"),
):
    redirect = _redirect_se_nao_admin(request)
    if redirect:
        return redirect

    db: Session = SessionLocal()
    try:
        local = Local(
            nome=nome,
            endereco=endereco,
            regiao=regiao,
            tipo_evento=normalizar_tipo_evento(tipo_evento),
            latitude=latitude,
            longitude=longitude,
            acessibilidade=bool(acessibilidade),
            proximo_metro=bool(proximo_metro),
            restaurantes=bool(restaurantes),
        )
        db.add(local)
        db.commit()
        return RedirectResponse(url="/cadastro?msg=local_ok", status_code=303)
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
    tipo_evento: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
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

        local.nome = nome
        local.endereco = endereco
        local.regiao = regiao
        local.tipo_evento = normalizar_tipo_evento(tipo_evento)
        local.latitude = latitude
        local.longitude = longitude
        local.acessibilidade = bool(acessibilidade)
        local.proximo_metro = bool(proximo_metro)
        local.restaurantes = bool(restaurantes)
        db.commit()
        return RedirectResponse(url="/manutencao?msg=local_edit_ok", status_code=303)
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


@app.get("/mapa-locais", response_class=HTMLResponse)
def mapa_locais(request: Request):
    redirect = _redirect_se_nao_autenticado(request)
    if redirect:
        return redirect

    db: Session = SessionLocal()
    try:
        locais = db.query(Local).all()
        regionais = [r.nome for r in db.query(Regional).order_by(Regional.nome).all()]

        mapa = folium.Map(location=[-19.9191, -43.9386], zoom_start=12)
        map_name = mapa.get_name()
        mapa.get_root().header.add_child(folium.Element(recursos_rota_mapa_html(map_name)))

        for local in locais:
            if not coordenadas_validas(local.latitude, local.longitude):
                continue
            lat = float(local.latitude)
            lon = float(local.longitude)
            cor = cor_regional(local.regiao)
            tooltip_text = f"{local.nome} — {local.regiao}"
            popup_text = f"""
            <b>{local.nome}</b><br>
            Endereço: {local.endereco}<br>
            Região: {local.regiao}<br>
            Lat: {lat}, Lon: {lon}
            {link_rota_html(lat, lon, map_name, local.nome)}
            """
            folium.Marker(
                location=[lat, lon],
                popup=popup_text,
                tooltip=tooltip_text,
                icon=folium.Icon(color=cor)
            ).add_to(mapa)

        cabecalho_legenda = f"Legenda - Regional ({len(locais)} locais)"
        mapa.get_root().html.add_child(
            folium.Element(legenda_mapa_html(regionais, cabecalho_legenda))
        )
        return mapa.get_root().render()
    finally:
        db.close()


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
def mapa_eventos(request: Request):
    redirect = _redirect_se_nao_autenticado(request)
    if redirect:
        return redirect

    db: Session = SessionLocal()
    try:
        eventos = db.query(Evento).join(Local).all()
        regionais = [r.nome for r in db.query(Regional).order_by(Regional.nome).all()]

        # Centro do mapa em Belo Horizonte
        mapa = folium.Map(location=[-19.9191, -43.9386], zoom_start=12)
        map_name = mapa.get_name()
        mapa.get_root().header.add_child(folium.Element(recursos_rota_mapa_html(map_name)))
        cluster_eventos = MarkerCluster(name="Eventos").add_to(mapa)
        bounds_por_regional: dict[str, dict[str, float]] = {}

        eventos_mostrados = 0
        for evento in eventos:
            if not coordenadas_validas(evento.local.latitude, evento.local.longitude):
                continue
            lat = float(evento.local.latitude)
            lon = float(evento.local.longitude)
            regional = evento.local.regiao or "Sem regional"

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
            <b>{evento.nome}</b><br>
            Descrição: {evento.descricao}<br>
            Data: {evento.data_inicio} a {evento.data_fim}<br>
            Público: {evento.publico_estimado}<br>
            Porte: {evento.porte}<br>
            Tipo: {evento.tipo_evento}<br>
            Local: {evento.local.nome}
            {link_rota_html(lat, lon, map_name, evento.local.nome)}
            """
            folium.Marker(
                location=[lat, lon],
                popup=popup_text,
                tooltip=tooltip_text,
                icon=folium.Icon(color=cor)
            ).add_to(cluster_eventos)
            eventos_mostrados += 1

        cabecalho_legenda = f"Legenda - Regional ({eventos_mostrados} eventos)"
        mapa.get_root().html.add_child(
            folium.Element(
                legenda_mapa_html_interativa(
                    regionais=regionais,
                    cabecalho=cabecalho_legenda,
                    map_name=map_name,
                    bounds_por_regional=bounds_por_regional,
                )
            )
        )
        return mapa.get_root().render()
    finally:
        db.close()


@app.get("/calendario", response_class=HTMLResponse)
def calendario_eventos(request: Request, tipo_evento: str = "Todos"):
    redirect = _redirect_se_nao_autenticado(request)
    if redirect:
        return redirect

    db: Session = SessionLocal()
    locais = db.query(Local).all()
    tipo_evento_selecionado = "Todos"
    if tipo_evento in TIPOS_EVENTO:
        tipo_evento_selecionado = tipo_evento

    query_eventos = db.query(Evento).join(Local)
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
        logo_html = f'<img class="logo" src="{escape(LOGO_URL)}" alt="Logo BH">'

    html = """
    <html>
    <head>
        <title>Calendário de Eventos BH</title>
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
            .header h1 { margin: 0; position: absolute; left: 50%; transform: translateX(-50%); }
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
            <h1>Calendário de Eventos de Belo Horizonte</h1>
        </div>
        <form class="filtro-wrap" method="get" action="/calendario">
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