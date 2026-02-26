# código final 26/02/2026
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
import re
from twilio.rest import Client

st.set_page_config(page_title="Monitor Universal", layout="wide")

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
# FUNÇÃO DE LIMPEZA DE PREÇOS À PROVA DE BALAS
# ==========================================
def parse_price(val):
    if val is None: return 999999.0
    if isinstance(val, (int, float)): return float(val)
    val_str = str(val).upper().replace("R$", "").replace("BRL", "").strip()
    match = re.search(r'[\d\.,]+', val_str)
    if not match: return 999999.0
    num_str = match.group(0)
    if "." in num_str and "," in num_str:
        num_str = num_str.replace(".", "").replace(",", ".")
    elif "," in num_str:
        num_str = num_str.replace(",", ".")
    try: return float(num_str)
    except: return 999999.0

# ==========================================
# MOTORES DE BUSCA: VIAGENS
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
            preco = parse_price(h.get("total_rate", {}).get("extracted_lowest", 0))
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
        
        if "error" in res:
            st.error(f"🚫 Erro da SerpApi (Voos): {res['error']}")
            return []
            
        voos = (res.get("best_flights", []) + res.get("other_flights", []))
        link_voo = res.get("search_metadata", {}).get("google_flights_url")
        
        hoteis = []
        if incluir_h and cidade_hotel:
            hoteis = buscar_hoteis_google(cidade_hotel, ida, volta, adt, cri, idades, 1, orc_total)
            
        pacotes = []
        for v in voos[:5]:
            p_voo = parse_price(v.get("price", 0))
            if incluir_h and hoteis:
                for h in hoteis[:2]: 
                    if (p_voo + h["preco"]) <= orc_total:
                        pacotes.append({"total": (p_voo + h["preco"]), "voo": v["flights"][0]["airline"], "hotel": h["nome"], "link_v": link_voo, "link_h": h["link"]})
            elif not incluir_h and p_voo <= orc_total:
                pacotes.append({"total": p_voo, "voo": v["flights"][0]["airline"], "hotel": "Apenas Voo", "link_v": link_voo, "link_h": ""})
        
        return sorted(pacotes, key=lambda x: x["total"])[:5]
    except Exception as e: 
        st.error(f"Erro Crítico ao buscar Viagem: {e}")
        return []

# ==========================================
# MOTORES DE BUSCA: PRODUTOS (LINKS NATIVOS DIRETOS)
# ==========================================
def buscar_produtos_google(metodo, produto_base, marca, termos_excluir, link_produto, orcamento):
    try:
        params = {"hl": "pt-br", "gl": "br", "google_domain": "google.com.br", "currency": "BRL", "api_key": SERPAPI_KEY}
        
        if "Filtros" in metodo: 
            query = f"{produto_base}"
            if marca: query += f" {marca}"
            if termos_excluir:
                exclusoes = " ".join([f"-{t.strip()}" for t in termos_excluir.split(",") if t.strip()])
                query += f" {exclusoes}"
            params["engine"] = "google_shopping"
            params["q"] = query.strip()
        else:
            match = re.search(r'pid:(\d+)', link_produto) or re.search(r'product/(\d+)', link_produto)
            if match:
                params["engine"] = "google_product"
                params["product_id"] = match.group(1)
            else:
                params["engine"] = "google_shopping"
                params["q"] = link_produto
        
        res = requests.get("https://serpapi.com/search.json", params=params).json()
        
        if "error" in res:
            st.error(f"🚫 Falha na Busca do Google: {res['error']}")
            if "exhausted" in res["error"].lower() or "credits" in res["error"].lower():
                st.warning("💡 O seu plano da SerpApi atingiu o limite (100 buscas gratuitas). Será necessário aguardar a renovação ou criar uma nova chave de API.")
            return []
            
        encontrados = []
        
        if "shopping_results" in res:
            for item in res["shopping_results"]:
                preco_bruto = item.get("extracted_price") or item.get("price")
                preco = parse_price(preco_bruto)
                
                if preco <= orcamento:
                    titulo = item.get("title", "")
                    
                    # Usa o link nativo da loja
                    link_oferta = item.get("link", "")
                    
                    # Se o link nativo for aquele problemático, tenta usar o link oficial de comparação da API
                    if "ibp=oshop" in link_oferta:
                        link_oferta = item.get("product_link", "")
                        
                    # Se mesmo assim falhar, cria uma busca limpa
                    if not link_oferta or not link_oferta.startswith("http"):
                        link_oferta = f"https://www.google.com.br/search?tbm=shop&q={urllib.parse.quote(titulo)}"
                    
                    encontrados.append({
                        "nome": titulo,
                        "total": preco, 
                        "loja": item.get("source", "Loja não informada"),
                        "link": link_oferta
                    })
                    if len(encontrados) >= 5: break
        
        elif "product_results" in res:
            nome_produto = res.get("product_results", {}).get("title", "Produto Rastreado")
            # Link da página de comparação retornado diretamente pela SerpApi (nada de inventar URLs)
            link_matriz = res.get("product_results", {}).get("product_link", "")
            
            for seller in res.get("sellers_results", {}).get("online_sellers", []):
                preco_bruto = seller.get("base_price")
                preco = parse_price(preco_bruto)
                
                if preco <= orcamento:
                    link_oferta = seller.get("link", "")
                    
                    if "ibp=oshop" in link_oferta or not link_oferta.startswith("http"):
                        if link_matriz:
                            link_oferta = link_matriz
                        else:
                            link_oferta = f"https://www.google.com.br/search?tbm=shop&q={urllib.parse.quote(nome_produto)}"
                        
                    encontrados.append({
                        "nome": nome_produto,
                        "total": preco,
                        "loja": seller.get("name", "Loja não informada"),
                        "link": link_oferta
                    })
                    if len(encontrados) >= 5: break
                    
        return sorted(encontrados, key=lambda x: x["total"])
    except Exception as e:
        st.error(f"Erro Crítico ao buscar Produto: {e}")
        return []

# ==========================================
# ALERTAS DE WHATSAPP
# ==========================================
def enviar_alerta_whatsapp_painel(numero, itens, codigo, tipo_monitoramento="viagem"):
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        if tipo_monitoramento == "viagem":
            msg = f"✈️ *{len(itens)} OPÇÕES DE VIAGEM!* (Cód: {codigo})\n\n"
            for i, p in enumerate(itens, 1):
                msg += f"{i}️⃣ *R$ {p['total']:,.2f}*\n✈️ {p['voo']}\n🏨 {p['hotel']}\n🔗 Voo: {p['link_v']}\n"
                if p.get('link_h'): msg += f"🔗 Hotel: {p['link_h']}\n"
                msg += "\n"
        else:
            msg = f"📦 *{len(itens)} OFERTAS DE PRODUTO!* (Cód: {codigo})\n\n"
            for i, p in enumerate(itens, 1):
                msg += f"{i}️⃣ *R$ {p['total']:,.2f}* na loja {p['loja']}\n🛒 {p['nome'][:45]}...\n🔗 Link: {p['link']}\n\n"
                
        msg += "O sistema continuará monitorando na frequência escolhida!"
        
        num_limpo = str(numero).strip().replace("-", "").replace(" ", "").replace("+", "").replace("whatsapp:", "")
        if len(num_limpo) == 10 or len(num_limpo) == 11:
            num_limpo = f"55{num_limpo}"
        dest = f"whatsapp:+{num_limpo}"
        
        message = client.messages.create(from_=TWILIO_WHATSAPP_NUMBER, body=msg, to=dest)
        return True, ""
    except Exception as e:
        return False, str(e)

# ==========================================
# SISTEMA DE LOGIN E ADMIN
# ==========================================
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
    st.session_state["usuario_logado"] = None

if not st.session_state["autenticado"]:
    st.title("🔒 Acesso Restrito - Sistema de Monitoramento")
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
            if st.button("Recuperar"): st.info("Função de recuperação ativa.")
            
        with aba_admin:
            s_admin = st.text_input("Senha Master:", type="password")
            if s_admin == CHAVE_ATIVACAO_STRIPE:
                st.success("✅ Acesso Master Liberado!")
                st.divider()
                usuarios_bd = carregar_usuarios()
                
                if usuarios_bd:
                    st.write(f"**Total de Clientes Registrados:** {len(usuarios_bd)}")
                    user_to_reset = st.selectbox("Selecione o utilizador para gerenciar:", list(usuarios_bd.keys()))
                    
                    col_adm1, col_adm2 = st.columns(2)
                    with col_adm1:
                        if st.button("Forçar Reset de Senha (123456)", use_container_width=True):
                            usuarios_bd[user_to_reset]["senha"] = "123456"
                            usuarios_bd[user_to_reset]["precisa_trocar_senha"] = True 
                            salvar_usuarios(usuarios_bd)
                            st.success(f"✅ Senha do utilizador {user_to_reset} resetada.")
                    with col_adm2:
                        if st.button("🗑️ Excluir Usuário", use_container_width=True):
                            del usuarios_bd[user_to_reset]
                            salvar_usuarios(usuarios_bd)
                            
                            bd_geral = carregar_bd()
                            codigos_para_remover = [cod for cod, info in bd_geral.items() if info.get("telefone") == user_to_reset]
                            for cod in codigos_para_remover: del bd_geral[cod]
                            if codigos_para_remover: salvar_bd(bd_geral)
                            
                            st.success(f"✅ Usuário {user_to_reset} e orçamentos excluídos!")
                            time.sleep(1.5)
                            st.rerun()
                else: st.info("Nenhum utilizador registado.")
    st.stop()

# ==========================================
# MEGA DICIONÁRIO DE AEROPORTOS (GLOBAL)
# ==========================================
AEROPORTOS = {
    "São Paulo (GRU)": "GRU", "São Paulo (CGH)": "CGH", "Rio de Janeiro (GIG)": "GIG", "Rio de Janeiro (SDU)": "SDU",
    "Brasília (BSB)": "BSB", "Salvador (SSA)": "SSA", "Recife (REC)": "REC", "Fortaleza (FOR)": "FOR",
    "Miami, EUA (MIA)": "MIA", "Orlando, EUA (MCO)": "MCO", "Nova York, EUA (JFK)": "JFK",
    "Cancun, México (CUN)": "CUN", "Lisboa, Portugal (LIS)": "LIS", "Paris, França (CDG)": "CDG",
    "Londres, UK (LHR)": "LHR", "Madri, Espanha (MAD)": "MAD", "Buenos Aires, Arg (EZE)": "EZE",
    "Santiago, Chile (SCL)": "SCL", "Cape Town (CPT)": "CPT", "Joanesburgo (JNB)": "JNB"
}

st.sidebar.title("🤖 Painel do Robô")
st.sidebar.write(f"👤 Usuário: **{st.session_state['usuario_logado']}**")

if st.sidebar.button("🚪 Sair (Logout)", use_container_width=True):
    st.session_state["autenticado"] = False
    st.session_state["usuario_logado"] = None
    st.rerun()
st.sidebar.divider()

bd_atual = carregar_bd()

# --- CARTÕES INTERATIVOS ---
with st.sidebar.expander("📂 Meus Orçamentos Salvos", expanded=True):
    encontrou_algum = False
    for c, info in list(bd_atual.items()):
        if info.get("telefone") == st.session_state["usuario_logado"]:
            encontrou_algum = True
            is_ativo = info.get("monitorar", False)
            status_str = "✅ Ativo" if is_ativo else "⏸️ Pausado"
            tipo_mon = info.get("tipo_monitoramento", "viagem") 
            
            with st.container(border=True):
                st.markdown(f"**Cód: {c}** | {status_str}")
                
                if tipo_mon == "viagem":
                    st.caption(f"🛫 **Rota:** {info.get('origem', 'N/A')} ➡️ {info.get('destino', 'N/A')}")
                    st.caption(f"📅 **Data:** {info.get('data_ida')}")
                else:
                    st.caption(f"📦 **Produto:** {info.get('produto_base', 'Link Específico')}")
                    st.caption(f"🔎 **Modo:** {info.get('metodo_busca', 'N/A')}")
                
                st.caption(f"💰 **Teto:** R$ {info.get('orcamento_max', 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                st.caption(f"⏰ **Freq:** {info.get('frequencia', 'Diariamente')} (Base: {info.get('horario', 'N/A')})") 
                
                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    lbl_btn = "⏸️ Pausar" if is_ativo else "▶️ Ativar"
                    if st.button(lbl_btn, key=f"tog_{c}", use_container_width=True):
                        bd_atual[c]["monitorar"] = not is_ativo
                        salvar_bd(bd_atual)
                        st.rerun() 
                with col_b2:
                    if st.button("🗑️ Excluir", key=f"del_{c}", use_container_width=True):
                        del bd_atual[c]
                        salvar_bd(bd_atual)
                        st.rerun() 
    if not encontrou_algum:
        st.info("Nenhum orçamento salvo.")

st.title("🌐 Monitor Universal (Viagens e Produtos)")

aba_nova_busca, aba_historico = st.tabs(["🔎 Nova Configuração", "📈 Relatório de Tendências (Histórico)"])

with aba_nova_busca:
    tipo_monitoramento = st.radio("O que deseja monitorar?", ["✈️ Viagens (Voo + Hotel)", "📦 Produtos (E-commerce)"], horizontal=True)
    st.divider()
    
    if tipo_monitoramento == "✈️ Viagens (Voo + Hotel)":
        st.header("✈️ Premissas da Viagem")
        tipo_voo = st.radio("Tipo:", ["Ida e Volta", "Somente Ida", "Multidestino"], horizontal=True)
        incluir_hospedagem = st.checkbox("🏨 Adicionar Hospedagem", value=(tipo_voo != "Multidestino"))
        
        col_o, col_d, col_ida, col_volta = st.columns(4)
        with col_o: origem_n = st.selectbox("Origem", list(AEROPORTOS.keys()))
        with col_d: destino_n = st.selectbox("Destino", list(AEROPORTOS.keys()))
        with col_ida: d_ida = st.date_input("Ida", datetime.date(2026, 7, 25))
        with col_volta: d_volta = st.date_input("Volta", datetime.date(2026, 8, 1)) if tipo_voo == "Ida e Volta" else None

        st.subheader("🛫 Filtros e Orçamento")
        c1, c2, c3 = st.columns(3)
        with c1: orc_max = st.number_input("Orçamento Máx", value=30000)
        with c2: escalas = st.number_input("Máx Escalas", 0, 5, 1)
        with c3: cia = st.text_input("Cia Aérea", placeholder="Todas")

        if incluir_hospedagem:
            st.subheader("🏨 Exigências da Hospedagem")
            colH1, colH2 = st.columns(2)
            with colH1: cidade_hotel = st.text_input("Cidade do Hotel", value="Cancun")
            with colH2: bairros_hotel = st.text_input("Bairro/Preferência", placeholder="Ex: Resort, All Inclusive")
        else: cidade_hotel = ""

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
                
    else:
        st.header("📦 Monitoramento de Preços de Produtos")
        metodo_busca = st.radio("Escolha o Método de Rastreio:", ["Busca por Filtros (Avançada)", "Rastrear Link Específico (Google Shopping)"])
        
        if metodo_busca == "Busca por Filtros (Avançada)":
            st.info("💡 Exemplo: Produto Base: 'Patinete Elétrico', Marca: 'Xiaomi', Excluir: 'pneu, carregador, infantil'")
            cP1, cP2 = st.columns(2)
            with cP1: prod_base = st.text_input("Produto Base (Obrigatório)", placeholder="Ex: iPhone 15 Pro Max")
            with cP2: prod_marca = st.text_input("Marca / Modelo", placeholder="Ex: Apple")
            prod_excluir = st.text_input("Palavras a Excluir (separadas por vírgula)", placeholder="Ex: capa, película, acessório, usado")
            link_produto = ""
        else:
            st.info("💡 Encontre o produto no Google Shopping, copie o link e cole abaixo para rastrear a tabela de preços do item exato.")
            link_produto = st.text_input("Cole o Link do Google Shopping aqui:")
            prod_base = "Produto por Link"
            prod_marca = ""
            prod_excluir = ""
            
        st.subheader("💰 Orçamento do Produto")
        orc_max = st.number_input("Orçamento Máximo (R$)", value=5000)

    st.divider()
    st.subheader("📱 Configuração do Robô de Alertas")
    cz1, cz2, cz3 = st.columns(3)
    with cz1: 
        tel_alerta = st.text_input("WhatsApp de Destino", value=st.session_state["usuario_logado"], disabled=True)
    with cz2:
        opcoes_frequencia = ["Diariamente", "A cada hora", "2 vezes por dia", "4 vezes por dia", "Semanalmente", "Mensalmente"]
        freq_alerta = st.selectbox("Frequência de Monitoramento", opcoes_frequencia)
    with cz3:
        hora_a = st.time_input("Horário Base do Alerta", datetime.time(9, 45))

    if st.button("Buscar e Salvar Automação", type="primary", use_container_width=True):
        with st.spinner("🚀 Consultando inteligência do Google..."):
            cod = str(uuid.uuid4())[:6].upper()
            hoje_str = datetime.datetime.now().strftime("%Y-%m-%d")
            historico_precos = {}
            
            if tipo_monitoramento == "✈️ Viagens (Voo + Hotel)":
                ida_s = d_ida.strftime("%Y-%m-%d")
                vlt_s = d_volta.strftime("%Y-%m-%d") if d_volta else ""
                resultados = buscar_pacotes_completos(AEROPORTOS[origem_n], AEROPORTOS[destino_n], ida_s, vlt_s, adt, cri, idades, orc_max, incluir_hospedagem, cidade_hotel)
                
                if resultados: historico_precos[hoje_str] = resultados[0]['total']
                
                bd_atual[cod] = {
                    "tipo_monitoramento": "viagem",
                    "monitorar": True, "telefone": tel_alerta, "horario": hora_a.strftime("%H:%M"), "frequencia": freq_alerta, "data_criacao": hoje_str,
                    "origem": AEROPORTOS[origem_n], "destino": AEROPORTOS[destino_n], "orcamento_max": orc_max,
                    "data_ida": ida_s, "data_volta": vlt_s, "adultos": adt, "criancas": cri, 
                    "ultimo_disparo": "", "ultimo_disparo_full": "", 
                    "incluir_hospedagem": incluir_hospedagem, "cidade_hotel": cidade_hotel,
                    "historico": historico_precos
                }
            else:
                resultados = buscar_produtos_google(metodo_busca, prod_base, prod_marca, prod_excluir, link_produto, orc_max)
                
                if resultados: historico_precos[hoje_str] = resultados[0]['total']
                
                bd_atual[cod] = {
                    "tipo_monitoramento": "produto",
                    "metodo_busca": metodo_busca, "produto_base": prod_base, "marca": prod_marca, "termos_excluir": prod_excluir, "link_produto": link_produto,
                    "monitorar": True, "telefone": tel_alerta, "horario": hora_a.strftime("%H:%M"), "frequencia": freq_alerta, "data_criacao": hoje_str,
                    "orcamento_max": orc_max, "ultimo_disparo": "", "ultimo_disparo_full": "", "historico": historico_precos
                }

            salvar_bd(bd_atual)
            
            if resultados:
                tipo_str = "viagem" if tipo_monitoramento == "✈️ Viagens (Voo + Hotel)" else "produto"
                sucesso_wa, erro_wa = enviar_alerta_whatsapp_painel(tel_alerta, resultados, cod, tipo_str)
                
                if sucesso_wa: 
                    st.success(f"✅ ATIVADO! A busca instantânea foi enviada para o WhatsApp.")
                else: 
                    st.error(f"⚠️ Salvo, mas o Twilio bloqueou: {erro_wa}")
                
                st.subheader("🔎 Opções Encontradas Agora:")
                for r in resultados:
                    with st.container(border=True):
                        if tipo_monitoramento == "✈️ Viagens (Voo + Hotel)":
                            st.write(f"💰 **R$ {r['total']:,.2f}**")
                            st.write(f"✈️ Voo: {r['voo']} | 🏨 Hotel: {r['hotel']}")
                            if r.get('link_h'):
                                st.markdown(f"[🔗 Ver Voo]({r['link_v']}) | [🔗 Ver Hotel]({r['link_h']})")
                            else:
                                st.markdown(f"[🔗 Ver Voo]({r['link_v']})")
                        else:
                            st.write(f"💰 **R$ {r['total']:,.2f}** | 🏬 Loja: {r['loja']}")
                            st.write(f"📦 {r['nome']}")
                            st.markdown(f"[🔗 Acessar Oferta]({r['link']})")
            else: 
                st.warning(f"🔔 ORÇAMENTO SALVO! O robô ficará vigiando, mas não enviou alerta agora porque não encontrou nenhuma opção no teto de R$ {orc_max}.")

with aba_historico:
    st.subheader("📉 Análise de Tendência de Preços")
    codigos_usuario = {c: info for c, info in bd_atual.items() if info.get("telefone") == st.session_state["usuario_logado"]}
    if not codigos_usuario:
        st.info("Ainda não tem orçamentos salvos para gerar relatórios.")
    else:
        cod_selecionado = st.selectbox("Selecione o Código do Orçamento:", list(codigos_usuario.keys()))
        dados_orcamento = codigos_usuario[cod_selecionado]
        
        if dados_orcamento.get("tipo_monitoramento", "viagem") == "viagem":
            st.write(f"✈️ **Viagem:** {dados_orcamento.get('destino')} | **Ida:** {dados_orcamento.get('data_ida')}")
        else:
            st.write(f"📦 **Produto:** {dados_orcamento.get('produto_base')}")
        
        historico_dados = dados_orcamento.get("historico", {})
        if not historico_dados:
            st.warning("O robô ainda não recolheu dados de preço suficientes para este código.")
        else:
            df_historico = pd.DataFrame(list(historico_dados.items()), columns=['Data da Busca', 'Menor Preço (R$)'])
            df_historico['Data da Busca'] = pd.to_datetime(df_historico['Data da Busca'])
            st.line_chart(df_historico.set_index('Data da Busca')['Menor Preço (R$)'])
