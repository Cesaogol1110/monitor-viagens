# código final 26/02/2026 - O SEU LAYOUT ORIGINAL + INTELIGÊNCIA DE BUSCA
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
FIREBASE_URL = st.secrets["FIREBASE_URL"] 

# ==========================================
# CONEXÃO DEFINITIVA COM FIREBASE (NUVEM)
# ==========================================
def carregar_usuarios():
    try:
        res = requests.get(f"{FIREBASE_URL}/usuarios.json")
        if res.status_code == 200 and res.json() is not None:
            return res.json()
    except: pass
    return {}

def salvar_usuarios(dados):
    try:
        requests.put(f"{FIREBASE_URL}/usuarios.json", json=dados)
    except: pass

def carregar_bd():
    try:
        res = requests.get(f"{FIREBASE_URL}/monitoramentos.json")
        if res.status_code == 200 and res.json() is not None:
            return res.json()
    except: pass
    return {}

def salvar_bd(dados):
    try:
        requests.put(f"{FIREBASE_URL}/monitoramentos.json", json=dados)
    except: pass

def testar_alerta_whatsapp(numero_destino, mensagem):
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        destino_formatado = numero_destino if numero_destino.startswith("whatsapp:") else f"whatsapp:{numero_destino}"
        message = client.messages.create(from_=TWILIO_WHATSAPP_NUMBER, body=mensagem, to=destino_formatado)
        return True, message.sid
    except Exception as e:
        return False, str(e)

# ==========================================
# NOVAS FUNÇÕES DE BUSCA (VOOS + HOTÉIS + 5 OPÇÕES)
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

def buscar_pacotes_completos_v2(origem, destino, ida, volta, adt, cri, idades, orc_total, incluir_h, cidade_hotel):
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

def enviar_alerta_whatsapp_5_opcoes(numero, pacotes, codigo):
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        msg = f"🚀 *{len(pacotes)} OPÇÕES ENCONTRADAS!* (Cód: {codigo})\n\n"
        for i, p in enumerate(pacotes, 1):
            msg += f"{i}️⃣ *R$ {p['total']:,.2f}*\n✈️ {p['voo']}\n🏨 {p['hotel']}\n🔗 Voo: {p['link_v']}\n"
            if p['link_h']: msg += f"🔗 Hotel: {p['link_h']}\n"
            msg += "\n"
        msg += "O robô vigilante continuará monitorando diariamente no Render!"
        dest = f"whatsapp:{numero}" if not numero.startswith("whatsapp:") else f"whatsapp:+{numero.lstrip('+')}"
        client.messages.create(from_=TWILIO_WHATSAPP_NUMBER, body=msg, to=dest)
        return True
    except: return False


# ==========================================
# SISTEMA DE LOGIN E GESTÃO MASTER
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
                elif not novo_tel.startswith("+"):
                    st.warning("⚠️ O número de telefone precisa começar com o sinal de + e o código do país (ex: +5511999999999).")
                else:
                    usuarios = carregar_usuarios()
                    if novo_tel in usuarios:
                        st.warning("⚠️ Este telefone já possui conta. Por favor, faça o login na aba ao lado.")
                    else:
                        usuarios[novo_tel] = {"senha": nova_senha, "data_cadastro": str(datetime.date.today()), "precisa_trocar_senha": False}
                        salvar_usuarios(usuarios)
                        st.success("✅ Conta criada com sucesso! Salvando nas nuvens...")
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
                if not tel_recuperar.startswith("+"):
                    st.warning("⚠️ Digite o número completo com o sinal de + (ex: +5511999999999).")
                else:
                    usuarios = carregar_usuarios()
                    if tel_recuperar in usuarios:
                        nova_senha_random = str(random.randint(100000, 999999))
                        usuarios[tel_recuperar]["senha"] = nova_senha_random
                        usuarios[tel_recuperar]["precisa_trocar_senha"] = True 
                        salvar_usuarios(usuarios)
                        
                        msg_recuperacao = f"🔐 *Monitor de Viagens - Recuperação de Acesso*\n\nSua senha foi redefinida. A sua nova senha provisória é: *{nova_senha_random}*\n\nFaça o login com ela. O sistema exigirá que você crie uma nova senha em seguida."
                        sucesso_wa, erro_wa = testar_alerta_whatsapp(tel_recuperar, msg_recuperacao)
                        
                        if sucesso_wa:
                            st.success("✅ Nova senha enviada para o seu WhatsApp com sucesso!")
                        else:
                            st.error("⚠️ Ocorreu um erro no envio. Contate o administrador.")
                    else:
                        st.error("❌ Telefone não encontrado no banco de dados.")

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
            if not nova_senha_1:
                st.error("⚠️ A senha não pode ficar em branco.")
            elif nova_senha_1 != nova_senha_2:
                st.error("❌ As senhas não coincidem. Digite novamente.")
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
# DICIONÁRIOS E FUNÇÕES DE BUSCA DA INTERFACE
# ==========================================
AEROPORTOS = {
    "São Paulo (GRU) - Guarulhos": "GRU",
    "São Paulo (CGH) - Congonhas": "CGH",
    "São Paulo (VCP) - Viracopos": "VCP",
    "Rio de Janeiro (GIG) - Galeão": "GIG",
    "Rio de Janeiro (SDU) - Santos Dumont": "SDU",
    "Brasília (BSB) - Juscelino Kubitschek": "BSB",
    "Belo Horizonte (CNF) - Confins": "CNF",
    "Salvador (SSA) - Dep. Luís Eduardo Magalhães": "SSA",
    "Recife (REC) - Guararapes": "REC",
    "Fortaleza (FOR) - Pinto Martins": "FOR",
    "Jericoacoara, CE (JJD) - Comandante Ariston Pessoa": "JJD",
    "Cancun, México (CUN)": "CUN",
    "Cape Town, África do Sul (CPT)": "CPT",
    "Joanesburgo, África do Sul (JNB)": "JNB",
    "Buenos Aires, Arg (EZE) - Ezeiza": "EZE",
    "Buenos Aires, Arg (AEP) - Aeroparque": "AEP",
    "Santiago, Chile (SCL)": "SCL",
    "Bogotá, Colômbia (BOG)": "BOG",
    "Nova York, EUA (JFK) - John F. Kennedy": "JFK",
    "Nova York, EUA (EWR) - Newark": "EWR",
    "Miami, EUA (MIA)": "MIA",
    "Orlando, EUA (MCO)": "MCO",
    "Londres, UK (LHR) - Heathrow": "LHR",
    "Paris, França (CDG) - Charles de Gaulle": "CDG",
    "Lisboa, Portugal (LIS)": "LIS",
    "Madri, Espanha (MAD)": "MAD"
}

def formatar_moeda(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ==========================================
# BARRA LATERAL E INTERFACE PRINCIPAL
# ==========================================
st.sidebar.title("🤖 Painel do Robô")

st.sidebar.write(f"👤 Usuário: **{st.session_state['usuario_logado']}**")
if st.sidebar.button("🚪 Sair (Logout)", use_container_width=True):
    st.session_state["autenticado"] = False
    st.session_state["usuario_logado"] = None
    st.rerun()
st.sidebar.divider()

bd_atual = carregar_bd()
with st.sidebar.expander("📂 Consultar Orçamentos Salvos"):
    if not bd_atual: st.info("Nenhum orçamento salvo.")
    else:
        # Apenas mostrar os orçamentos que pertencem ao usuário logado
        telefone_logado = st.session_state.get("usuario_logado", "")
        encontrou_algum = False
        for codigo, info in bd_atual.items():
            if info.get("telefone") == telefone_logado:
                encontrou_algum = True
                status_monitoramento = "✅ ATIVO" if info.get("monitorar") else "⏸️ Pausado"
                st.markdown(f"**Código:** `{codigo}`")
                st.write(f"Status: {status_monitoramento}")
                st.divider()
        if not encontrou_algum:
            st.info("Você ainda não tem orçamentos salvos.")

with st.sidebar.expander("📲 Ativar Monitoramento Automático"):
    st.write("Insira o código do pacote abaixo para ligar ou desligar os avisos.")
    codigo_simulacao = st.text_input("Código do Orçamento (ex: A1B2C3)")
    resposta_simulacao = st.selectbox("Ação", ["ATIVAR Monitoramento", "CANCELAR Monitoramento"])
    if st.button("Aplicar Ação", use_container_width=True):
        codigo_limpo = codigo_simulacao.strip().upper()
        if codigo_limpo in bd_atual:
            if resposta_simulacao == "ATIVAR Monitoramento":
                bd_atual[codigo_limpo]["monitorar"] = True
                salvar_bd(bd_atual)
                st.sidebar.success(f"✅ Monitoramento {codigo_limpo} ATIVADO!")
            else:
                bd_atual[codigo_limpo]["monitorar"] = False
                salvar_bd(bd_atual)
                st.sidebar.warning(f"🛑 Monitoramento {codigo_limpo} CANCELADO!")
        else:
            st.sidebar.error("Código não encontrado no banco de dados nas nuvens.")

st.title("✈️ Monitor de Viagens Avançado")

with st.expander("⚙️ CONFIGURAR PREMISSAS DA VIAGEM", expanded=True):
    tipo_voo = st.radio("Tipo de viagem:", ["Ida e Volta", "Somente Ida", "Multidestino"], horizontal=True)
    incluir_hospedagem = st.checkbox("🏨 Adicionar Hospedagem à Busca", value=(tipo_voo != "Multidestino"), disabled=(tipo_voo == "Multidestino"))
    st.divider()

    if tipo_voo == "Multidestino":
        st.warning("⚠️ Multidestinos ativado! O motor inteligente foca apenas nos voos para esta modalidade.")
        if 'num_trechos' not in st.session_state: st.session_state.num_trechos = 2
        def adicionar_trecho():
            if st.session_state.num_trechos < 6: st.session_state.num_trechos += 1
        def remover_trecho():
            if st.session_state.num_trechos > 2: st.session_state.num_trechos -= 1
        for i in range(st.session_state.num_trechos):
            col_orig, col_dest, col_data = st.columns(3)
            with col_orig: st.selectbox(f"Origem Trecho {i+1}", options=list(AEROPORTOS.keys()), index=None, placeholder="Selecione...", key=f"orig_multi_{i}")
            with col_dest: st.selectbox(f"Destino Trecho {i+1}", options=list(AEROPORTOS.keys()), index=None, placeholder="Selecione...", key=f"dest_multi_{i}")
            with col_data: st.date_input(f"Data Trecho {i+1}", datetime.date(2026, 7, 25 + i), format="DD/MM/YYYY", key=f"data_multi_{i}")
        
        st.write("") 
        col_btn1, col_btn2, _ = st.columns([2, 2, 6])
        with col_btn1: st.button("➕ Adicionar Trecho", on_click=adicionar_trecho, use_container_width=True)
        with col_btn2: st.button("➖ Remover Trecho", on_click=remover_trecho, use_container_width=True)
        st.divider()
        origem_nome = "Multidestino"
        destino_nome = "Multidestino"
    else:
        col_orig, col_dest, col_ida, col_volta = st.columns(4)
        with col_orig:
            origem_nome = st.selectbox("Origem", options=list(AEROPORTOS.keys()), index=None, placeholder="Escolha a origem...")
            origem = AEROPORTOS.get(origem_nome) if origem_nome else None
        with col_dest:
            destino_nome = st.selectbox("Destino", options=list(AEROPORTOS.keys()), index=None, placeholder="Escolha o destino...") 
            destino = AEROPORTOS.get(destino_nome) if destino_nome else None
        with col_ida:
            data_ida = st.date_input("Data de Ida", datetime.date(2026, 7, 25), format="DD/MM/YYYY")
        with col_volta:
            if tipo_voo == "Ida e Volta":
                data_volta = st.date_input("Data de Volta", datetime.date(2026, 8, 1), format="DD/MM/YYYY")
            else:
                data_volta = None
                st.info("Apenas ida.")
        st.divider()

    st.subheader("🛫 Filtros Aéreos e Orçamento Total")
    col1, col2, col3, col4 = st.columns(4)
    with col1: orcamento_max = st.number_input("Orçamento Máx TOTAL", min_value=1000, value=None, step=1000, placeholder="Ex: 15000")
    with col2: max_escalas = st.number_input("Máximo de Escalas", min_value=0, max_value=5, value=1)
    with col3: max_duracao = st.number_input("Duração Máx Voo (hrs)", min_value=1, max_value=40, value=20)
    with col4: filtro_cia = st.text_input("Companhia Aérea", value="", placeholder="Todas as cias aéreas")
    
    col_hora_ida, col_hora_volta = st.columns(2)
    opcoes_horario = ["Qualquer horário", "Madrugada (00h - 06h)", "Manhã (06h - 12h)", "Tarde (12h - 18h)", "Noite (18h - 00h)"]
    with col_hora_ida: filtro_horario_ida = st.selectbox("Preferência: Horário de Ida", opcoes_horario)
    with col_hora_volta: 
        filtro_horario_volta = st.selectbox("Preferência: Horário de Volta", opcoes_horario, disabled=(tipo_voo != "Ida e Volta"))
    st.divider()
    
    if incluir_hospedagem:
        st.subheader("🏨 Exigências da Hospedagem")
        colH_C, colH_B = st.columns(2)
        with colH_C: 
            cidade_sugerida = destino_nome.split('(')[0].strip() if destino_nome and destino_nome != "Multidestino" else ""
            cidade_hotel = st.text_input("Cidade do Hotel", value=cidade_sugerida)
        with colH_B: 
            bairros_hotel = st.text_input("Bairro(s) (opcional)", value="", placeholder="ex: Ipanema, Copacabana")
            
        colH1, colH2, colH3 = st.columns(3)
        with colH1: min_estrelas = st.slider("Mínimo de Estrelas", 1, 5, 4)
        with colH2: min_nota = st.slider("Nota dos Hóspedes (Google)", 1.0, 5.0, 4.0, 0.1)
        with colH3: palavra_chave = st.text_input("Preferência (ex: Resort)", value="")
        st.divider()
    else:
        cidade_hotel, bairros_hotel, min_estrelas, min_nota, palavra_chave = "", "", 3, 4.0, ""

    col6, col7 = st.columns(2)
    with col6:
        st.subheader("👥 Passageiros")
        colA, colB, colC = st.columns(3)
        with colA: adultos = st.number_input("Adultos", min_value=1, value=2)
        with colB: criancas = st.number_input("Crianças", min_value=0, max_value=6, value=0)
        with colC: quartos = st.number_input("Quartos", min_value=1, max_value=5, value=1, disabled=(not incluir_hospedagem))
        
        idades_criancas = []
        if criancas > 0:
            st.markdown("**Idade das Crianças:**")
            cols_idades = st.columns(criancas)
            for i in range(criancas):
                with cols_idades[i]:
                    idade = st.number_input(f"Criança {i+1}", min_value=0, max_value=17, value=6, key=f"idade_crianca_{i}")
                    idades_criancas.append(idade)

    with col7:
        st.subheader("📱 Alerta Automático")
        colZ1, colZ2 = st.columns(2)
        with colZ1: seu_numero = st.text_input("WhatsApp (ex: +5511999999999)", value=st.session_state.get("usuario_logado", ""), disabled=True)
        with colZ2: horario_alerta = st.time_input("Horário Diário", datetime.time(18, 0))

st.divider()

if st.button("Buscar Pacotes & Salvar Automação", type="primary", use_container_width=True):
    if tipo_voo != "Multidestino" and (not origem_nome or not destino_nome or not orcamento_max):
        st.error("⚠️ Por favor, selecione a Origem, Destino e o Orçamento Máximo para buscar.")
    elif tipo_voo == "Multidestino":
        st.info("A funcionalidade Voo+Hotel para Multidestinos entrará em breve.")
    else:
        with st.spinner("Pesquisando pacotes em tempo real e salvando no servidor..."):
            data_ida_str = data_ida.strftime("%Y-%m-%d")
            data_volta_str = data_volta.strftime("%Y-%m-%d") if data_volta else ""
            hora_str = horario_alerta.strftime("%H:%M")
            
            # --- NOVIDADE: BUSCA EM TEMPO REAL ---
            resultados = buscar_pacotes_completos_v2(origem, destino, data_ida_str, data_volta_str, adultos, criancas, idades_criancas, orcamento_max, incluir_hospedagem, cidade_hotel)
            
            codigo_orcamento = str(uuid.uuid4())[:6].upper()
            bd_atual[codigo_orcamento] = {
                "monitorar": True, # Já fica ativo automaticamente
                "telefone": seu_numero, "horario": hora_str, "ultimo_disparo": "",
                "origem": origem, "destino": destino, "incluir_hospedagem": incluir_hospedagem, "cidade_hotel": cidade_hotel, "bairros_hotel": bairros_hotel,
                "tipo_voo": tipo_voo, "data_ida": data_ida_str, "data_volta": data_volta_str,
                "adultos": adultos, "criancas": criancas, "idades_criancas": idades_criancas, "quartos": quartos, "max_duracao": max_duracao, "max_escalas": max_escalas,
                "orcamento_max": orcamento_max, "min_estrelas": min_estrelas, "min_nota": min_nota, "palavra_chave": palavra_chave, "filtro_cia": filtro_cia,
                "filtro_horario_ida": filtro_horario_ida, "filtro_horario_volta": filtro_horario_volta
            }
            salvar_bd(bd_atual)
            
            if resultados:
                st.success(f"🎉 **✅ ORÇAMENTO SALVO! CÓDIGO: {codigo_orcamento}**")
                st.info(f"O motor vigiará este pacote todos os dias às **{hora_str}**.")
                
                # --- NOVIDADE: WHATSAPP NA HORA ---
                enviar_alerta_whatsapp_5_opcoes(seu_numero, resultados, codigo_orcamento)
                
                # --- NOVIDADE: MOSTRAR RESULTADOS NA TELA ---
                st.subheader("🛫 Opções Encontradas Agora:")
                for r in resultados:
                    with st.container(border=True):
                        st.write(f"💰 **R$ {r['total']:,.2f}**")
                        st.write(f"✈️ Voo: {r['voo']} | 🏨 Hotel: {r['hotel']}")
                        if r['link_h']:
                            st.markdown(f"[🔗 Ver Voo no Google]({r['link_v']}) | [🔗 Ver Hotel no Google]({r['link_h']})")
                        else:
                            st.markdown(f"[🔗 Ver Voo no Google]({r['link_v']})")
            else:
                st.success(f"🎉 **✅ ORÇAMENTO SALVO COM SUCESSO! CÓDIGO: {codigo_orcamento}**")
                st.warning("⚠️ No momento não encontramos pacotes abaixo desse teto, mas o robô continuará vigiando diariamente!")
