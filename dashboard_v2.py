# python -m streamlit run dashboard_v2.py
# código final 26/02/2026 - VERSÃO PREMIUM (DESIGN COMPLETO + BUSCA 5 OPÇÕES)
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
# CONFIGURAÇÕES E CHAVES DO COFRE
# ==========================================
TWILIO_ACCOUNT_SID = st.secrets["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = st.secrets["TWILIO_AUTH_TOKEN"]
TWILIO_WHATSAPP_NUMBER = st.secrets["TWILIO_WHATSAPP_NUMBER"]
SERPAPI_KEY = st.secrets["SERPAPI_KEY"]
CHAVE_ATIVACAO_STRIPE = st.secrets.get("CHAVE_ACESSO_CLIENTES", "123452026") 
FIREBASE_URL = st.secrets["FIREBASE_URL"].rstrip('/')

# ==========================================
# DICIONÁRIOS E AUXILIARES
# ==========================================
AEROPORTOS = {
    "São Paulo (GRU) - Guarulhos": "GRU", "São Paulo (CGH) - Congonhas": "CGH",
    "Cancun, México (CUN)": "CUN", "Miami, EUA (MIA)": "MIA", 
    "Orlando, EUA (MCO)": "MCO", "Lisboa, Portugal (LIS)": "LIS",
    "Paris, França (CDG)": "CDG", "Londres, UK (LHR)": "LHR"
}

def formatar_moeda(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def carregar_bd():
    try:
        res = requests.get(f"{FIREBASE_URL}/monitoramentos.json")
        return res.json() if res.status_code == 200 and res.json() else {}
    except: return {}

def salvar_bd(dados):
    requests.put(f"{FIREBASE_URL}/monitoramentos.json", json=dados)

def carregar_usuarios():
    try:
        res = requests.get(f"{FIREBASE_URL}/usuarios.json")
        return res.json() if res.status_code == 200 and res.json() else {}
    except: return {}

# ==========================================
# MOTOR DE BUSCA E WHATSAPP
# ==========================================
def buscar_5_melhores(origem, destino, ida, volta, passageiros, orcamento):
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
                encontrados.append({"preco": preco, "cia": v["flights"][0]["airline"], "link": link_geral})
                if len(encontrados) >= 5: break
        return encontrados
    except: return []

def enviar_whatsapp_multiplo(numero, pacotes, codigo, tipo="INSTANTÂNEO"):
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        msg = f"🚀 *{tipo}: {len(pacotes)} OPÇÕES* (Cód: {codigo})\n\n"
        for i, p in enumerate(pacotes, 1):
            msg += f"{i}️⃣ *R$ {p['preco']}* - {p['cia']}\n🔗 {p['link']}\n\n"
        msg += "O robô continuará monitorando diariamente!"
        dest = f"whatsapp:{numero}" if not numero.startswith("whatsapp:") else numero
        client.messages.create(from_=TWILIO_WHATSAPP_NUMBER, body=msg, to=dest)
        return True
    except: return False

# ==========================================
# LOGIN (RESTANTE IGUAL AO ORIGINAL)
# ==========================================
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
if not st.session_state["autenticado"]:
    # (Omitido para brevidade, mantenha o código de login do seu arquivo anterior)
    # ... 
    st.title("🔒 Login Monitor de Viagens")
    tel = st.text_input("Telefone")
    senha = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        st.session_state["autenticado"] = True
        st.session_state["usuario_logado"] = tel
        st.rerun()
    st.stop()

# ==========================================
# INTERFACE PRINCIPAL (O DESIGN VOLTOU!)
# ==========================================
st.sidebar.title("🤖 Painel do Robô")
st.sidebar.write(f"👤 Usuário: **{st.session_state['usuario_logado']}**")

# Sidebar - Consultar e Ativar (RESTAURADO)
bd_atual = carregar_bd()
with st.sidebar.expander("📂 Consultar Orçamentos"):
    for c, i in bd_atual.items():
        if i.get("telefone") == st.session_state["usuario_logado"]:
            st.write(f"Cod: `{c}` | {'✅ Ativo' if i['monitorar'] else '⏸️ Pausado'}")

with st.sidebar.expander("📲 Ativar Monitoramento"):
    cod_m = st.text_input("Código")
    acao_m = st.selectbox("Ação", ["ATIVAR Monitoramento", "CANCELAR Monitoramento"])
    if st.button("Aplicar Ação"):
        if cod_m in bd_atual:
            bd_atual[cod_m]["monitorar"] = (acao_m == "ATIVAR Monitoramento")
            salvar_bd(bd_atual)
            st.success("Atualizado!")

st.title("✈️ Monitor de Viagens Avançado")

with st.expander("⚙️ CONFIGURAR PREMISSAS DA VIAGEM", expanded=True):
    tipo_v = st.radio("Tipo:", ["Ida e Volta", "Somente Ida"], horizontal=True)
    
    col_o, col_d, col_i, col_v = st.columns(4)
    with col_o: origem_n = st.selectbox("Origem", list(AEROPORTOS.keys()))
    with col_d: destino_n = st.selectbox("Destino", list(AEROPORTOS.keys()))
    with col_i: d_ida = st.date_input("Ida", datetime.date(2026, 7, 25))
    with col_v: d_volta = st.date_input("Volta", datetime.date(2026, 8, 1))

    st.subheader("🛫 Filtros Aéreos e Orçamento Total")
    colA, colB, colC, colD = st.columns(4)
    with colA: orc_max = st.number_input("Orçamento Máx", value=15000)
    with colB: escalas = st.number_input("Máx Escalas", 0, 5, 1)
    with colC: duracao = st.number_input("Duração Máx (h)", 1, 40, 20)
    with colD: cia = st.text_input("Cia Aérea", placeholder="Todas")

    st.subheader("👥 Passageiros e 📱 Alerta")
    colP1, colP2 = st.columns(2)
    with colP1:
        cA, cC = st.columns(2)
        with cA: adt = st.number_input("Adultos", 1, 10, 2)
        with cC: cri = st.number_input("Crianças", 0, 10, 2)
        idades = []
        if cri > 0:
            cols_id = st.columns(cri)
            for j in range(cri):
                with cols_id[j]: idades.append(st.number_input(f"Idade C{j+1}", 0, 17, 6))
    with colP2:
        tel_a = st.text_input("WhatsApp", value=st.session_state["usuario_logado"], disabled=True)
        hora_a = st.time_input("Horário Diário", datetime.time(9, 45))

if st.button("Buscar Pacotes & Salvar Automação", type="primary", use_container_width=True):
    with st.spinner("🚀 Pesquisando e Ativando..."):
        # 1. BUSCA NA HORA (5 OPÇÕES)
        res = buscar_multiplas_opcoes(AEROPORTOS[origem_n], AEROPORTOS[destino_n], d_ida.strftime("%Y-%m-%d"), d_volta.strftime("%Y-%m-%d"), (adt+cri), orc_max)
        
        # 2. SALVA NO BANCO
        cod_novo = str(uuid.uuid4())[:6].upper()
        bd_atual[cod_novo] = {
            "monitorar": True, "telefone": tel_a, "horario": hora_a.strftime("%H:%M"),
            "origem": AEROPORTOS[origem_n], "destino": AEROPORTOS[destino_n],
            "data_ida": d_ida.strftime("%Y-%m-%d"), "data_volta": d_volta.strftime("%Y-%m-%d"),
            "orcamento_max": orc_max, "adultos": adt, "criancas": cri, "ultimo_disparo": ""
        }
        salvar_bd(bd_atual)
        
        if res:
            st.success(f"✅ ORÇAMENTO {cod_novo} SALVO E DISPARADO!")
            enviar_whatsapp_multiplo(tel_a, res, cod_novo)
            for r in res:
                with st.container(border=True):
                    st.write(f"💰 **{formatar_moeda(r['preco'])}** | ✈️ {r['cia']}")
                    st.markdown(f"[🔗 Ver no Google Flights]({r['link']})")
        else:
            st.warning("Salvo! Nenhuma opção barata agora, mas o robô vigiará.")
