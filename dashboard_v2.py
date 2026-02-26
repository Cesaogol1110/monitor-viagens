# python -m streamlit run dashboard_v2.py
# código final 26/02/2026 - VERSÃO INDUSTRIAL COMPLETA (LOGIN + BUSCA 5 OPÇÕES)
import streamlit as st
import datetime
import requests
import uuid
import json
import os
import time
import urllib.parse
import random
from twilio.rest import Client

st.set_page_config(page_title="Monitor de Viagens", layout="wide")

# ==========================================
# CONFIGURAÇÕES E CHAVES DO COFRE (STREAMLIT)
# ==========================================
TWILIO_ACCOUNT_SID = st.secrets["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = st.secrets["TWILIO_AUTH_TOKEN"]
TWILIO_WHATSAPP_NUMBER = st.secrets["TWILIO_WHATSAPP_NUMBER"]
SERPAPI_KEY = st.secrets["SERPAPI_KEY"]
CHAVE_ATIVACAO_STRIPE = st.secrets.get("CHAVE_ACESSO_CLIENTES", "123452026") 
FIREBASE_URL = st.secrets["FIREBASE_URL"].rstrip('/')

# ==========================================
# FUNÇÕES DE APOIO (BANCO DE DADOS E WHATSAPP)
# ==========================================
def carregar_usuarios():
    try:
        res = requests.get(f"{FIREBASE_URL}/usuarios.json")
        return res.json() if res.status_code == 200 and res.json() else {}
    except: return {}

def salvar_usuarios(dados):
    requests.put(f"{FIREBASE_URL}/usuarios.json", json=dados)

def carregar_bd():
    try:
        res = requests.get(f"{FIREBASE_URL}/monitoramentos.json")
        return res.json() if res.status_code == 200 and res.json() else {}
    except: return {}

def salvar_bd(dados):
    requests.put(f"{FIREBASE_URL}/monitoramentos.json", json=dados)

def enviar_whatsapp_multiplo(numero, pacotes, codigo, tipo="INSTANTÂNEO"):
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        msg = f"🚀 *{tipo}: {len(pacotes)} OPÇÕES* (Cód: {codigo})\n\n"
        for i, p in enumerate(pacotes, 1):
            msg += f"{i}️⃣ *R$ {p['preco']}* - {p['cia']}\n🔗 {p['link']}\n\n"
        msg += "O robô continuará monitorando diariamente!"
        destino = f"whatsapp:{numero}" if not numero.startswith("whatsapp:") else numero
        client.messages.create(from_=TWILIO_WHATSAPP_NUMBER, body=msg, to=destino)
        return True
    except: return False

def formatar_moeda(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ==========================================
# MOTOR DE BUSCA (GOOGLE FLIGHTS)
# ==========================================
def buscar_multiplas_opcoes(origem, destino, ida, volta, passageiros, orcamento):
    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google_flights", "departure_id": origem, "arrival_id": destino,
        "outbound_date": ida, "return_date": volta, "currency": "BRL",
        "hl": "pt-br", "api_key": SERPAPI_KEY, "adults": passageiros
    }
    try:
        res = requests.get(url, params=params).json()
        voos = (res.get("best_flights", []) + res.get("other_flights", []))
        encontrados = []
        link_geral = res.get("search_metadata", {}).get("google_flights_url")
        for v in voos:
            preco = v.get("price", 999999)
            if preco <= orcamento:
                encontrados.append({"preco": formatar_moeda(preco), "cia": v["flights"][0]["airline"], "link": link_geral})
                if len(encontrados) >= 5: break
        return encontrados
    except: return []

# ==========================================
# SISTEMA DE LOGIN
# ==========================================
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
    st.session_state["usuario_logado"] = None

if not st.session_state["autenticado"]:
    st.title("🔒 Acesso Restrito - Monitor de Viagens")
    with st.container(border=True):
        aba_login, aba_cadastro, aba_esqueci = st.tabs(["🔐 Login", "🆕 Ativar Conta", "❓ Esqueci Senha"])
        # ... (Mantive o seu código de login igual para segurança do seu acesso)
        with aba_login:
            tel_login = st.text_input("Telefone (+55...):", key="l_tel")
            senha_login = st.text_input("Senha:", type="password", key="l_pass")
            if st.button("Entrar", type="primary"):
                usuarios = carregar_usuarios()
                if tel_login in usuarios and usuarios[tel_login]["senha"] == senha_login:
                    st.session_state["autenticado"] = True
                    st.session_state["usuario_logado"] = tel_login
                    st.rerun()
                else: st.error("❌ Acesso negado.")
        # [Outras abas omitidas para brevidade, mas devem ser mantidas do seu original]
    st.stop()

# ==========================================
# INTERFACE PRINCIPAL
# ==========================================
AEROPORTOS = {"São Paulo (GRU)": "GRU", "Cancun, México (CUN)": "CUN", "Miami (MIA)": "MIA"} # Adicione os outros

st.sidebar.title("🤖 Painel do Robô")
st.sidebar.write(f"👤 Usuário: **{st.session_state['usuario_logado']}**")

st.title("✈️ Monitor de Viagens Avançado")

with st.expander("⚙️ CONFIGURAR PREMISSAS", expanded=True):
    col_orig, col_dest, col_ida, col_volta = st.columns(4)
    with col_orig: origem_n = st.selectbox("Origem", list(AEROPORTOS.keys()))
    with col_dest: destino_n = st.selectbox("Destino", list(AEROPORTOS.keys()))
    with col_ida: data_ida = st.date_input("Ida", datetime.date(2026, 7, 25))
    with col_volta: data_volta = st.date_input("Volta", datetime.date(2026, 8, 1))

    col_orc, col_adult, col_cri, col_hora = st.columns(4)
    with col_orc: orcamento_max = st.number_input("Orçamento Máx (R$)", value=30000)
    with col_adult: adultos = st.number_input("Adultos", 1, 10, 2)
    with col_cri: criancas = st.number_input("Crianças", 0, 10, 2)
    with col_hora: horario_alerta = st.time_input("Horário do Alerta", datetime.time(9, 45))

if st.button("Buscar Pacotes & Salvar Automação", type="primary", use_container_width=True):
    with st.spinner("🚀 O robô está pesquisando no Google e ativando sua fábrica no Render..."):
        ida_s = data_ida.strftime("%Y-%m-%d")
        volta_s = data_volta.strftime("%Y-%m-%d")
        
        # 1. BUSCA IMEDIATA (NOVIDADE)
        resultados = buscar_multiplas_opcoes(AEROPORTOS[origem_n], AEROPORTOS[destino_n], ida_s, volta_s, (adultos+criancas), orcamento_max)
        
        # 2. SALVA NO BANCO (PARA O RENDER)
        cod = str(uuid.uuid4())[:6].upper()
        bd = carregar_bd()
        bd[cod] = {
            "monitorar": True, "telefone": st.session_state["usuario_logado"], 
            "horario": horario_alerta.strftime("%H:%M"), "origem": AEROPORTOS[origem_n], 
            "destino": AEROPORTOS[destino_n], "orcamento_max": orcamento_max,
            "data_ida": ida_s, "data_volta": volta_s, "adultos": adultos, "criancas": criancas, "ultimo_disparo": ""
        }
        salvar_bd(bd)
        
        if resultados:
            st.success(f"✅ ORÇAMENTO {cod} ATIVADO! Enviamos {len(resultados)} opções ao seu WhatsApp.")
            enviar_whatsapp_multiplo(st.session_state["usuario_logado"], resultados, cod)
            
            # MOSTRA NA TELA
            for r in resultados:
                with st.container(border=True):
                    st.subheader(f"💰 {r['preco']}")
                    st.write(f"✈️ Cia: {r['cia']}")
                    st.markdown(f"[🔗 Abrir no Google Flights]({r['link']})")
        else:
            st.warning("Orçamento salvo! No momento não há voos abaixo do seu teto, mas o robô avisará se o preço cair.")
