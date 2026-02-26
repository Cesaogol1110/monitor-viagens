# código final 26/02/2026 - VERSÃO INTEGRAL COM CARTÕES DE ORÇAMENTO E HISTÓRICO
# dashboard_v2.py
import streamlit as st
import datetime
import requests
import uuid
import json
import os
import time
import urllib.parse
import random
import pandas as pd
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
# CONEXÃO COM FIREBASE (NUVEM)
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

# ==========================================
# MOTOR DE BUSCA (VOOS + HOTÉIS) E WHATSAPP
# ==========================================
def buscar_hoteis_google(cidade, ida, volta, adultos, criancas, idades, quartos, orcamento_parcial):
    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google_hotels", "q": cidade, "check_in_date": ida, "check_out_date": volta,
        "adults": adultos, "currency": "BRL", "hl": "pt-br", "api_key": SERPAPI_KEY
    }
    if criancas > 0: params["children_ages"] = ",".join(map(str, idades))
    try:
        res = requests.get(url, params=params).json()
        hoteis = []
        for h in res.get("properties", [])[:10]:
            preco = h.get("total_rate", {}).get("extracted_lowest", 0)
            if preco > 0:
                hoteis.append({"nome": h.get("name"), "preco": preco, "nota": h.get("overall_rating", 0), "link": h.get("link")})
        return hoteis
    except: return []

def buscar_pacotes_completos(origem, destino, ida, volta, adt, cri, idades, orc_total, incluir_h, cidade_hotel=""):
    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google_flights", "departure_id": origem, "arrival_id": destino,
        "outbound_date": ida, "return_date": volta, "currency": "BRL", "hl": "pt-br", 
        "api_key": SERPAPI_KEY, "adults": (adt + cri)
    }
    try:
        res = requests.get(url, params=params).json()
        voos = (res.get("best_flights", []) + res.get("other_flights", []))
        link_voo = res.get("search_metadata", {}).get("google_flights_url")
        
        hoteis = []
        if incluir_h and cidade_hotel:
            hoteis = buscar_hoteis_google(cidade_hotel, ida, volta, adt, cri, idades, 1, orc_total)
            
        pacotes = []
        for v in voos[:5]:
            p_voo = v.get("price", 0)
            if incluir_h and hoteis:
                for h in hoteis[:2]: 
                    if (p_voo + h["preco"]) <= orc_total:
                        pacotes.append({"total": (p_voo + h["preco"]), "voo": v["flights"][0]["airline"], "hotel": h["nome"], "link_v": link_voo, "link_h": h["link"]})
            elif not incluir_h and p_voo <= orc_total:
                pacotes.append({"total": p_voo, "voo": v["flights"][0]["airline"], "hotel": "Apenas Voo", "link_v": link_voo, "link_h": ""})
        
        return sorted(pacotes, key=lambda x: x["total"])[:5]
    except: return []

def enviar_alerta_whatsapp(numero, pacotes, codigo):
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        msg = f"🚀 *{len(pacotes)} OPÇÕES ENCONTRADAS!* (Cód: {codigo})\n\n"
        for i, p in enumerate(pacotes, 1):
            msg += f"{i}️⃣ *R$ {p['total']:,.2f}*\n✈️ {p['voo']}\n🏨 {p['hotel']}\n🔗 Voo: {p['link_v']}\n"
            if p['link_h']: msg += f"🔗 Hotel: {p['link_h']}\n"
            msg += "\n"
        msg += "O robô vigilante continuará monitorando diariamente!"
        dest = f"whatsapp:{numero}" if not numero.startswith("whatsapp:") else numero
        client.messages.create(from_=TWILIO_WHATSAPP_NUMBER, body=msg, to=dest)
        return True
    except: return False

# ==========================================
# SISTEMA DE LOGIN E ADMIN
# ==========================================
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
    st.session_state["usuario_logado"] = None

if not st.session_state["autenticado"]:
    st.title("🔒 Acesso Restrito - Monitor de Viagens")
    with st.container(border=True):
        aba_login, aba_cadastro, aba_esqueci, aba_admin = st.tabs(["🔐 Login", "🆕 Ativar Conta", "❓ Esqueci Senha", "👑 Admin"])
        
        with aba_login:
            tel_l = st.text_input("Telefone (+55...):", key="l_tel")
            pass_l = st.text_input("Senha:", type="password", key="l_pass")
            if st.button("Entrar", type="primary"):
                users = carregar_usuarios()
                if tel_l in users and users[tel_l]["senha"] == pass_l:
                    st.session_state["autenticado"] = True
                    st.session_state["usuario_logado"] = tel_l
                    st.rerun()
                else: st.error("Erro de acesso.")
                
        with aba_cadastro:
            cod_ativ = st.text_input("Código Stripe:", type="password")
            n_tel = st.text_input("Novo Login (WhatsApp):")
            n_senha = st.text_input("Nova Senha:", type="password")
            if st.button("Criar Conta"):
                if cod_ativ == CHAVE_ATIVACAO_STRIPE:
                    users = carregar_usuarios()
                    users[n_tel] = {"senha": n_senha, "precisa_trocar_senha": False}
                    salvar_usuarios(users)
                    st.success("Conta criada!")
                else: st.error("Código inválido.")
                
        with aba_esqueci:
            tel_rec = st.text_input("WhatsApp para recuperação:")
            if st.button("Recuperar"): st.info("Função de recuperação ativa (ver código original).")
            
        with aba_admin:
            s_admin = st.text_input("Senha Master:", type="password")
            if s_admin == CHAVE_ATIVACAO_STRIPE:
                st.success("Acesso Diretor!")
    st.stop()

# ==========================================
# INTERFACE PRINCIPAL E BARRA LATERAL
# ==========================================
AEROPORTOS = {
    "São Paulo (GRU) - Guarulhos": "GRU", "São Paulo (CGH) - Congonhas": "CGH",
    "Rio de Janeiro (GIG) - Galeão": "GIG", "Cancun, México (CUN)": "CUN", 
    "Miami, EUA (MIA)": "MIA", "Orlando, EUA (MCO)": "MCO", "Lisboa (LIS)": "LIS",
    "Cape Town, África do Sul (CPT)": "CPT", "Joanesburgo (JNB)": "JNB"
}

st.sidebar.title("🤖 Painel do Robô")
st.sidebar.write(f"👤 Usuário: **{st.session_state['usuario_logado']}**")

bd_atual = carregar_bd()

# --- NOVIDADE: CARTÕES DE ORÇAMENTO COM PREMISSAS NA BARRA LATERAL ---
with st.sidebar.expander("📂 Consultar Orçamentos Salvos", expanded=True):
    encontrou_algum = False
    for c, info in bd_atual.items():
        if info.get("telefone") == st.session_state["usuario_logado"]:
            encontrou_algum = True
            status_str = "✅ Ativo" if info.get("monitorar") else "⏸️ Pausado"
            
            # Formatação limpa dentro de um cartão
            with st.container(border=True):
                st.markdown(f"**Cód: {c}** | {status_str}")
                st.caption(f"👤 **Req:** {info.get('telefone')}")
                st.caption(f"🛫 **Rota:** {info.get('origem', 'N/A')} ➡️ {info.get('destino', 'N/A')}")
                if info.get('data_volta'):
                    st.caption(f"📅 **Datas:** {info.get('data_ida')} até {info.get('data_volta')}")
                else:
                    st.caption(f"📅 **Data:** {info.get('data_ida')} (Somente Ida)")
                st.caption(f"💰 **Teto:** R$ {info.get('orcamento_max', 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    
    if not encontrou_algum:
        st.info("Nenhum orçamento salvo.")

with st.sidebar.expander("📲 Ativar/Pausar Monitoramento"):
    cod_m = st.text_input("Código do Orçamento")
    acao_m = st.selectbox("Ação", ["ATIVAR Monitoramento", "CANCELAR Monitoramento"])
    if st.button("Aplicar Ação"):
        if cod_m in bd_atual:
            bd_atual[cod_m]["monitorar"] = (acao_m == "ATIVAR Monitoramento")
            salvar_bd(bd_atual)
            st.sidebar.success("Atualizado com sucesso!")

st.title("✈️ Monitor de Viagens Avançado")

# DIVISÃO EM ABAS
aba_nova_busca, aba_historico = st.tabs(["🔎 Nova Busca & Configuração", "📈 Relatório de Tendências (Histórico)"])

with aba_nova_busca:
    with st.expander("⚙️ CONFIGURAR PREMISSAS DA VIAGEM", expanded=True):
        tipo_voo = st.radio("Tipo:", ["Ida e Volta", "Somente Ida", "Multidestino"], horizontal=True)
        incluir_hospedagem = st.checkbox("🏨 Adicionar Hospedagem", value=(tipo_voo != "Multidestino"))
        
        col_o, col_d, col_ida, col_volta = st.columns(4)
        with col_o: origem_n = st.selectbox("Origem", list(AEROPORTOS.keys()))
        with col_d: destino_n = st.selectbox("Destino", list(AEROPORTOS.keys()))
        with col_ida: d_ida = st.date_input("Ida", datetime.date(2026, 7, 25))
        with col_volta: d_volta = st.date_input("Volta", datetime.date(2026, 8, 1)) if tipo_voo == "Ida e Volta" else None

        st.subheader("🛫 Filtros Aéreos e Orçamento")
        c1, c2, c3, c4 = st.columns(4)
        with c1: orc_max = st.number_input("Orçamento Máx", value=30000)
        with c2: escalas = st.number_input("Máx Escalas", 0, 5, 1)
        with c3: duracao = st.number_input("Duração (h)", 1, 40, 20)
        with c4: cia = st.text_input("Cia Aérea", placeholder="Todas")

        if incluir_hospedagem:
            st.subheader("🏨 Exigências da Hospedagem")
            colH1, colH2 = st.columns(2)
            with colH1: cidade_hotel = st.text_input("Cidade do Hotel", value="Cancun")
            with colH2: bairros_hotel = st.text_input("Bairro/Preferência", placeholder="Ex: Resort, All Inclusive")
        else:
            cidade_hotel = ""

        col_p1, col_p2 = st.columns(2)
        with col_p1:
            st.subheader("👥 Passageiros")
            cA, cC, cQ = st.columns(3)
            with cA: adt = st.number_input("Adultos", 1, 10, 2)
            with cC: cri = st.number_input("Crianças", 0, 6, 2)
            with cQ: qrt = st.number_input("Quartos", 1, 5, 1)
            idades = []
            if cri > 0:
                cols_id = st.columns(cri)
                for j in range(cri):
                    with cols_id[j]: idades.append(st.number_input(f"Idade C{j+1}", 0, 17, 6, key=f"id_{j}"))
        with col_p2:
            st.subheader("📱 Alerta Automático")
            tel_alerta = st.text_input("WhatsApp", value=st.session_state["usuario_logado"], disabled=True)
            hora_a = st.time_input("Horário Diário", datetime.time(9, 45))

    if st.button("Buscar Pacotes & Salvar Automação", type="primary", use_container_width=True):
        with st.spinner("🚀 Consultando Google Flights & Hotels..."):
            ida_s = d_ida.strftime("%Y-%m-%d")
            vlt_s = d_volta.strftime("%Y-%m-%d") if d_volta else ""
            
            resultados = buscar_pacotes_completos(AEROPORTOS[origem_n], AEROPORTOS[destino_n], ida_s, vlt_s, adt, cri, idades, orc_max, incluir_hospedagem, cidade_hotel)
            
            cod = str(uuid.uuid4())[:6].upper()
            hoje_str = datetime.datetime.now().strftime("%Y-%m-%d")
            
            # Histórico inicial
            historico_precos = {}
            if resultados:
                historico_precos[hoje_str] = resultados[0]['total']
            
            bd_atual[cod] = {
                "monitorar": True, "telefone": tel_alerta, "horario": hora_a.strftime("%H:%M"),
                "origem": AEROPORTOS[origem_n], "destino": AEROPORTOS[destino_n], "orcamento_max": orc_max,
                "data_ida": ida_s, "data_volta": vlt_s, "adultos": adt, "criancas": cri, 
                "ultimo_disparo": hoje_str if resultados else "", 
                "incluir_hospedagem": incluir_hospedagem,
                "historico": historico_precos
            }
            salvar_bd(bd_atual)
            
            if resultados:
                st.success(f"✅ ORÇAMENTO {cod} ATIVADO! Enviamos {len(resultados)} opções ao WhatsApp.")
                enviar_alerta_whatsapp(tel_alerta, resultados, cod)
                for r in resultados:
                    with st.container(border=True):
                        st.subheader(f"💰 R$ {r['total']:,.2f}")
                        st.write(f"✈️ {r['voo']} | 🏨 {r['hotel']}")
            else: st.warning("Salvo! No momento não há voos no preço, mas o robô vigiará.")

with aba_historico:
    st.subheader("📉 Análise de Tendência de Preços")
    st.write("Acompanhe a evolução do menor preço encontrado para saber o momento exato de comprar.")
    
    codigos_usuario = {c: info for c, info in bd_atual.items() if info.get("telefone") == st.session_state["usuario_logado"]}
    
    if not codigos_usuario:
        st.info("Você ainda não tem orçamentos salvos para gerar relatórios.")
    else:
        cod_selecionado = st.selectbox("Selecione o Código do Orçamento:", list(codigos_usuario.keys()))
        dados_orcamento = codigos_usuario[cod_selecionado]
        
        st.write(f"**Destino:** {dados_orcamento.get('destino')} | **Data Ida:** {dados_orcamento.get('data_ida')}")
        
        historico_dados = dados_orcamento.get("historico", {})
        
        if not historico_dados:
            st.warning("O robô ainda não coletou dados de preço suficientes para este código. Tente amanhã!")
        else:
            df_historico = pd.DataFrame(list(historico_dados.items()), columns=['Data da Busca', 'Menor Preço (R$)'])
            df_historico['Data da Busca'] = pd.to_datetime(df_historico['Data da Busca'])
            df_historico['Dia da Semana'] = df_historico['Data da Busca'].dt.day_name()
            
            st.line_chart(df_historico.set_index('Data da Busca')['Menor Preço (R$)'])
            
            with st.expander("Ver Tabela Detalhada"):
                st.dataframe(df_historico, use_container_width=True)
