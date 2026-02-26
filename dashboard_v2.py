# código final 26/02/2026 - VERSÃO PREMIUM (ADMIN COMPLETO + ANTI-ERRO TWILIO)
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

def testar_alerta_whatsapp(numero_destino, mensagem):
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        # Formatação inteligente do número
        num_limpo = str(numero_destino).strip().replace("-", "").replace(" ", "").replace("+", "").replace("whatsapp:", "")
        if len(num_limpo) == 10 or len(num_limpo) == 11:
            num_limpo = f"55{num_limpo}"
        destino_formatado = f"whatsapp:+{num_limpo}"
        
        message = client.messages.create(from_=TWILIO_WHATSAPP_NUMBER, body=mensagem, to=destino_formatado)
        return True, message.sid
    except Exception as e:
        return False, str(e)

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

def enviar_alerta_whatsapp_painel(numero, pacotes, codigo):
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        msg = f"🚀 *{len(pacotes)} OPÇÕES ENCONTRADAS!* (Cód: {codigo})\n\n"
        for i, p in enumerate(pacotes, 1):
            msg += f"{i}️⃣ *R$ {p['total']:,.2f}*\n✈️ {p['voo']}\n🏨 {p['hotel']}\n🔗 Voo: {p['link_v']}\n"
            if p['link_h']: msg += f"🔗 Hotel: {p['link_h']}\n"
            msg += "\n"
        msg += "O robô continuará monitorando na frequência escolhida!"
        
        # Tratamento inteligente de número (+55 automático)
        num_limpo = str(numero).strip().replace("-", "").replace(" ", "").replace("+", "").replace("whatsapp:", "")
        if len(num_limpo) == 10 or len(num_limpo) == 11:
            num_limpo = f"55{num_limpo}"
        dest = f"whatsapp:+{num_limpo}"
        
        message = client.messages.create(from_=TWILIO_WHATSAPP_NUMBER, body=msg, to=dest)
        return True, ""
    except Exception as e:
        return False, str(e)

# ==========================================
# SISTEMA DE LOGIN E GESTÃO MASTER (RESTAURADO)
# ==========================================
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
    st.session_state["usuario_logado"] = None

if not st.session_state["autenticado"]:
    st.title("🔒 Acesso Restrito - Monitor de Viagens")
    st.write("Bem-vindo ao robô inteligente de busca de passagens e hotéis.")
    
    with st.container(border=True):
        aba_login, aba_cadastro, aba_esqueci, aba_admin = st.tabs(["🔐 Fazer Login", "🆕 Ativar Conta", "❓ Esqueci a Senha", "👑 Admin"])
        
        with aba_login:
            st.subheader("Já tenho uma conta")
            tel_login = st.text_input("Seu Telefone (Login com +55 e DDD):", placeholder="Ex: +5511999999999", key="login_tel")
            senha_login = st.text_input("Sua Senha:", type="password", key="login_senha")
            
            if st.button("Entrar", type="primary", use_container_width=True):
                usuarios = carregar_usuarios()
                if tel_login in usuarios and usuarios[tel_login]["senha"] == senha_login:
                    st.session_state["autenticado"] = True
                    st.session_state["usuario_logado"] = tel_login
                    
                    if usuarios[tel_login].get("precisa_trocar_senha", False) or senha_login == "123456":
                        st.session_state["exigir_troca_senha"] = True
                    else:
                        st.session_state["exigir_troca_senha"] = False
                    st.rerun()
                else:
                    st.error("❌ Telefone ou senha incorretos.")
                    
        with aba_cadastro:
            st.subheader("Ativar minha assinatura")
            st.write("Insira o código recebido após o pagamento para criar seu login.")
            codigo_ativacao = st.text_input("Código de Ativação (Stripe):", type="password")
            st.divider()
            novo_tel = st.text_input("Crie seu Login (WhatsApp com +55 e DDD):", placeholder="Ex: +5511999999999")
            nova_senha = st.text_input("Crie uma Senha Pessoal:", type="password")
            
            if st.button("Criar Conta e Entrar", type="primary", use_container_width=True, key="btn_cad"):
                if codigo_ativacao != CHAVE_ATIVACAO_STRIPE:
                    st.error("❌ Código de ativação inválido ou expirado.")
                elif not novo_tel or not nova_senha:
                    st.warning("⚠️ Preencha o telefone e a senha desejada.")
                else:
                    usuarios = carregar_usuarios()
                    if novo_tel in usuarios:
                        st.warning("⚠️ Este telefone já possui conta. Por favor, faça o login.")
                    else:
                        usuarios[novo_tel] = {"senha": nova_senha, "data_cadastro": str(datetime.date.today()), "precisa_trocar_senha": False}
                        salvar_usuarios(usuarios)
                        st.success("✅ Conta criada com sucesso!")
                        st.session_state["autenticado"] = True
                        st.session_state["usuario_logado"] = novo_tel
                        st.session_state["exigir_troca_senha"] = False
                        time.sleep(1)
                        st.rerun()
        
        with aba_esqueci:
            st.subheader("Recuperar Senha")
            st.write("Enviaremos uma nova senha gerada pelo sistema para o seu WhatsApp.")
            tel_recuperar = st.text_input("Seu Telefone (com +55 e DDD):", placeholder="Ex: +5511999999999", key="rec_tel")
            
            if st.button("Receber Nova Senha", type="primary", use_container_width=True, key="btn_rec"):
                if not tel_recuperar:
                    st.warning("⚠️ Digite o número de telefone.")
                else:
                    usuarios = carregar_usuarios()
                    if tel_recuperar in usuarios:
                        nova_senha_random = str(random.randint(100000, 999999))
                        usuarios[tel_recuperar]["senha"] = nova_senha_random
                        usuarios[tel_recuperar]["precisa_trocar_senha"] = True 
                        salvar_usuarios(usuarios)
                        
                        msg_rec = f"🔐 *Monitor de Viagens*\n\nSua nova senha provisória é: *{nova_senha_random}*\n\nFaça o login com ela. O sistema exigirá que crie uma nova em seguida."
                        sucesso_wa, erro_wa = testar_alerta_whatsapp(tel_recuperar, msg_rec)
                        
                        if sucesso_wa: st.success("✅ Nova senha enviada para o seu WhatsApp!")
                        else: st.error(f"⚠️ Erro no envio do Twilio: {erro_wa}")
                    else:
                        st.error("❌ Telefone não encontrado.")

        with aba_admin:
            st.subheader("Painel de Gestão Master")
            senha_admin = st.text_input("Senha Master:", type="password", key="admin_pwd")
            
            if senha_admin == CHAVE_ATIVACAO_STRIPE:
                st.success("✅ Acesso de Diretor Liberado!")
                st.divider()
                usuarios_bd = carregar_usuarios()
                
                if usuarios_bd:
                    st.write(f"**Total de Clientes Registrados:** {len(usuarios_bd)}")
                    user_to_reset = st.selectbox("Selecione o usuário para gerenciar:", list(usuarios_bd.keys()))
                    
                    if st.button("Forçar Reset de Senha (Padrão: 123456)"):
                        usuarios_bd[user_to_reset]["senha"] = "123456"
                        usuarios_bd[user_to_reset]["precisa_trocar_senha"] = True 
                        salvar_usuarios(usuarios_bd)
                        st.success(f"✅ Senha do cliente {user_to_reset} resetada. Ele terá que criar uma nova ao entrar.")
                else:
                    st.info("Nenhum usuário cadastrado no banco de dados ainda.")

    st.divider()
    st.info("💡 **Ainda não tem acesso?** Adquira a sua licença mensal para desbloquear buscas ilimitadas.")
    st.markdown("### [🛒 **Clique aqui para Assinar e Liberar seu Acesso**](https://buy.stripe.com/test_4gM28r8YbgXQ0et0sZaAw00)") 
    st.stop()

# ==========================================
# TELA OBRIGATÓRIA DE TROCA DE SENHA
# ==========================================
if st.session_state.get("exigir_troca_senha", False):
    st.title("🔐 Atualização de Senha Obrigatória")
    st.warning("Detectamos que você está usando uma senha provisória. Por motivos de segurança, crie sua senha definitiva abaixo.")
    
    with st.container(border=True):
        nova_senha_1 = st.text_input("Digite a Nova Senha:", type="password", key="ns1")
        nova_senha_2 = st.text_input("Repita a Nova Senha:", type="password", key="ns2")
        
        if st.button("Salvar Senha e Entrar no Sistema", type="primary", use_container_width=True):
            if not nova_senha_1: st.error("⚠️ A senha não pode ficar em branco.")
            elif nova_senha_1 != nova_senha_2: st.error("❌ As senhas não coincidem.")
            else:
                usuarios = carregar_usuarios()
                user = st.session_state["usuario_logado"]
                usuarios[user]["senha"] = nova_senha_1
                usuarios[user]["precisa_trocar_senha"] = False 
                salvar_usuarios(usuarios)
                
                st.session_state["exigir_troca_senha"] = False
                st.success("✅ Senha atualizada com sucesso! A carregar o painel...")
                time.sleep(1)
                st.rerun()
    st.stop() 

# ==========================================
# MEGA DICIONÁRIO DE AEROPORTOS (GLOBAL)
# ==========================================
AEROPORTOS = {
    "São Paulo (GRU) - Guarulhos": "GRU", "São Paulo (CGH) - Congonhas": "CGH", "São Paulo (VCP) - Viracopos": "VCP",
    "Rio de Janeiro (GIG) - Galeão": "GIG", "Rio de Janeiro (SDU) - Santos Dumont": "SDU",
    "Brasília (BSB)": "BSB", "Belo Horizonte (CNF)": "CNF", "Salvador (SSA)": "SSA", "Recife (REC)": "REC", "Fortaleza (FOR)": "FOR",
    "Miami, EUA (MIA)": "MIA", "Orlando, EUA (MCO)": "MCO", "Nova York, EUA (JFK)": "JFK",
    "Cancun, México (CUN)": "CUN", "Lisboa, Portugal (LIS)": "LIS", "Paris, França (CDG)": "CDG",
    "Londres, UK (LHR)": "LHR", "Madri, Espanha (MAD)": "MAD", "Buenos Aires, Arg (EZE)": "EZE",
    "Santiago, Chile (SCL)": "SCL", "Cape Town, África do Sul (CPT)": "CPT", "Joanesburgo (JNB)": "JNB"
}

st.sidebar.title("🤖 Painel do Robô")
st.sidebar.write(f"👤 Usuário: **{st.session_state['usuario_logado']}**")

# --- BOTÃO DE SAIR RESTAURADO ---
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
            
            with st.container(border=True):
                st.markdown(f"**Cód: {c}** | {status_str}")
                st.caption(f"🛫 **Rota:** {info.get('origem', 'N/A')} ➡️ {info.get('destino', 'N/A')}")
                st.caption(f"📅 **Data:** {info.get('data_ida')}")
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

st.title("✈️ Monitor de Viagens Avançado")

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
            cz1, cz2, cz3 = st.columns(3)
            with cz1: 
                tel_alerta = st.text_input("WhatsApp", value=st.session_state["usuario_logado"], disabled=True)
            with cz2:
                opcoes_frequencia = ["Diariamente", "A cada hora", "2 vezes por dia", "4 vezes por dia", "Semanalmente", "Mensalmente"]
                freq_alerta = st.selectbox("Frequência", opcoes_frequencia)
            with cz3:
                hora_a = st.time_input("Horário Base", datetime.time(9, 45))

    if st.button("Buscar Pacotes & Salvar Automação", type="primary", use_container_width=True):
        with st.spinner("🚀 Consultando Google Flights & Hotels..."):
            ida_s = d_ida.strftime("%Y-%m-%d")
            vlt_s = d_volta.strftime("%Y-%m-%d") if d_volta else ""
            
            resultados = buscar_pacotes_completos(AEROPORTOS[origem_n], AEROPORTOS[destino_n], ida_s, vlt_s, adt, cri, idades, orc_max, incluir_hospedagem, cidade_hotel)
            
            cod = str(uuid.uuid4())[:6].upper()
            hoje_str = datetime.datetime.now().strftime("%Y-%m-%d")
            
            historico_precos = {}
            if resultados:
                historico_precos[hoje_str] = resultados[0]['total']
            
            bd_atual[cod] = {
                "monitorar": True, "telefone": tel_alerta, "horario": hora_a.strftime("%H:%M"),
                "frequencia": freq_alerta, "data_criacao": hoje_str,
                "origem": AEROPORTOS[origem_n], "destino": AEROPORTOS[destino_n], "orcamento_max": orc_max,
                "data_ida": ida_s, "data_volta": vlt_s, "adultos": adt, "criancas": cri, 
                "ultimo_disparo": "", "ultimo_disparo_full": "", 
                "incluir_hospedagem": incluir_hospedagem, "cidade_hotel": cidade_hotel,
                "historico": historico_precos
            }
            salvar_bd(bd_atual)
            
            if resultados:
                sucesso_wa, erro_wa = enviar_alerta_whatsapp_painel(tel_alerta, resultados, cod)
                if sucesso_wa:
                    st.success(f"✅ ORÇAMENTO {cod} ATIVADO! A busca instantânea foi enviada para o WhatsApp.")
                else:
                    st.error(f"⚠️ ORÇAMENTO SALVO, mas o Twilio bloqueou o envio para {tel_alerta}!\n\n**Causa raiz enviada pelo Twilio:** {erro_wa}")
            else: 
                st.warning(f"✅ ORÇAMENTO {cod} ATIVADO! Nenhuma opção no teto de R$ {orc_max}, mas o robô ficará vigiando.")
            
            time.sleep(2)
            st.rerun() 

with aba_historico:
    st.subheader("📉 Análise de Tendência de Preços")
    codigos_usuario = {c: info for c, info in bd_atual.items() if info.get("telefone") == st.session_state["usuario_logado"]}
    if not codigos_usuario:
        st.info("Você ainda não tem orçamentos salvos para gerar relatórios.")
    else:
        cod_selecionado = st.selectbox("Selecione o Código do Orçamento:", list(codigos_usuario.keys()))
        dados_orcamento = codigos_usuario[cod_selecionado]
        st.write(f"**Destino:** {dados_orcamento.get('destino')} | **Data Ida:** {dados_orcamento.get('data_ida')}")
        
        historico_dados = dados_orcamento.get("historico", {})
        if not historico_dados:
            st.warning("O robô ainda não coletou dados de preço suficientes para este código.")
        else:
            df_historico = pd.DataFrame(list(historico_dados.items()), columns=['Data da Busca', 'Menor Preço (R$)'])
            df_historico['Data da Busca'] = pd.to_datetime(df_historico['Data da Busca'])
            df_historico['Dia da Semana'] = df_historico['Data da Busca'].dt.day_name()
            st.line_chart(df_historico.set_index('Data da Busca')['Menor Preço (R$)'])
