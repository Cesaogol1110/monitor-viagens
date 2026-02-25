# código final 20/01/2026
# dashboard_v2.py
import streamlit as st
import datetime
import requests
import uuid
import json
import os
import threading
import time
import urllib.parse
from twilio.rest import Client

st.set_page_config(page_title="Robô de Viagens", layout="wide")

# ==========================================
# CONFIGURAÇÕES E BANCO DE DADOS LOCAL
# ==========================================
TWILIO_ACCOUNT_SID = st.secrets["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = st.secrets["TWILIO_AUTH_TOKEN"]
TWILIO_WHATSAPP_NUMBER = st.secrets["TWILIO_WHATSAPP_NUMBER"]
SERPAPI_KEY = st.secrets["SERPAPI_KEY"]
CHAVE_ACESSO = st.secrets.get("CHAVE_ACESSO_CLIENTES", "ARCA2026") # Puxa a senha do cofre

ARQUIVO_BD = "monitoramentos.json"

# ==========================================
# SISTEMA DE LOGIN / PAYWALL (COM O SEU LINK STRIPE)
# ==========================================
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False

if not st.session_state["autenticado"]:
    st.title("🔒 Acesso Restrito - Monitor ARCA")
    st.write("Bem-vindo ao robô inteligente de busca de passagens e hotéis.")
    
    with st.container(border=True):
        st.subheader("Faça seu Login")
        senha_digitada = st.text_input("Digite sua Chave de Acesso (Licença):", type="password")
        
        if st.button("Entrar no Sistema", type="primary", use_container_width=True):
            if senha_digitada == CHAVE_ACESSO:
                st.session_state["autenticado"] = True
                st.rerun() # Recarrega a página liberando o sistema
            else:
                st.error("❌ Chave de acesso inválida ou expirada.")
                
    st.divider()
    st.info("💡 **Ainda não tem acesso?** Adquira a sua licença mensal para desbloquear buscas ilimitadas e alertas diários no WhatsApp.")
    
    # NOVO: O seu link de pagamento oficial do Stripe está aqui!
    st.markdown("### [🛒 **Clique aqui para Assinar e Liberar seu Acesso**](https://buy.stripe.com/test_4gM28r8YbgXQ0et0sZaAw00)") 
    
    st.stop() # Isto impede que o resto do código abaixo seja lido por quem não pagou!

# Se o código chegou aqui, o utilizador pagou e está autenticado!
# ==========================================
# O RESTANTE DO CÓDIGO (INTACTO)
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

LOGOS_CIAS = {
    "LATAM": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d0/Logo_LATAM.svg/512px-Logo_LATAM.svg.png",
    "GOL": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/52/GOL_Linhas_A%C3%A9reas_Inteligentes_logo.svg/512px-GOL_Linhas_A%C3%A9reas_Inteligentes_logo.svg.png",
    "Azul": "https://upload.wikimedia.org/wikipedia/commons/thumb/z/z0/Azul_Linhas_Aereas_logo.svg/512px-Azul_Linhas_Aereas_logo.svg.png",
    "Avianca": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/Avianca_logo.svg/512px-Avianca_logo.svg.png",
    "Copa": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/15/Copa_Airlines_logo.svg/512px-Copa_Airlines_logo.svg.png",
    "American": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f6/American_Airlines_logo_2013.svg/512px-American_Airlines_logo_2013.svg.png",
    "United": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e0/United_Airlines_Logo.svg/512px-United_Airlines_Logo.svg.png",
    "TAP": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fa/TAP_Portugal_Logo.svg/512px-TAP_Portugal_Logo.svg.png",
    "South African": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/16/South_African_Airways_logo.svg/512px-South_African_Airways_logo.svg.png",
    "Aerolineas": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/Aerolineas_Argentinas_Logo_2010.svg/512px-Aerolineas_Argentinas_Logo_2010.svg.png",
    "Arajet": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/87/Arajet_Logo.png/512px-Arajet_Logo.png"
}

def obter_logo_cia(nome_cia):
    for chave, url_logo in LOGOS_CIAS.items():
        if chave.lower() in nome_cia.lower():
            return url_logo
    return "https://cdn-icons-png.flaticon.com/512/3125/3125713.png"

def carregar_bd():
    if os.path.exists(ARQUIVO_BD):
        with open(ARQUIVO_BD, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def salvar_bd(dados):
    with open(ARQUIVO_BD, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)

def formatar_moeda(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def testar_alerta_whatsapp(numero_destino, mensagem):
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        destino_formatado = numero_destino if numero_destino.startswith("whatsapp:") else f"whatsapp:{numero_destino}"
        message = client.messages.create(from_=TWILIO_WHATSAPP_NUMBER, body=mensagem, to=destino_formatado)
        return True, message.sid
    except Exception as e:
        return False, str(e)

def validar_horario(hora_str, filtro):
    if filtro == "Qualquer horário" or hora_str == "--:--": return True
    try:
        hora_int = int(hora_str.split(':')[0])
        if filtro == "Madrugada (00h - 06h)" and 0 <= hora_int < 6: return True
        if filtro == "Manhã (06h - 12h)" and 6 <= hora_int < 12: return True
        if filtro == "Tarde (12h - 18h)" and 12 <= hora_int < 18: return True
        if filtro == "Noite (18h - 00h)" and 18 <= hora_int <= 23: return True
    except: pass
    return False

def buscar_hoteis_google(cidade_hotel, bairros, data_ida_str, data_volta_str, adultos, criancas, idades_criancas, quartos, min_estrelas, min_nota, palavra_chave):
    url = "https://serpapi.com/search.json"
    palavra_chave_real = palavra_chave.strip()
    bairros_real = bairros.strip()
    cidade_limpa = cidade_hotel.split("(")[0].strip()
    
    if bairros_real: local_busca = f"{bairros_real}, {cidade_limpa}"
    else: local_busca = cidade_limpa
        
    pedacos_busca = []
    if palavra_chave_real: pedacos_busca.append(palavra_chave_real)
    if quartos > 1: pedacos_busca.append(f"{quartos} quartos")
    pedacos_busca.append(local_busca)
    termo_busca = " ".join(pedacos_busca).strip()
    
    hoteis_brutos = []
    next_page_token = None
    
    for pagina in range(4):
        params = {"engine": "google_hotels", "q": termo_busca, "check_in_date": data_ida_str, "check_out_date": data_volta_str, "adults": adultos, "currency": "BRL", "hl": "pt-br", "gl": "br", "api_key": SERPAPI_KEY}
        if criancas > 0:
            params["children"] = criancas
            if idades_criancas: params["children_ages"] = ",".join(str(idade) for idade in idades_criancas)
        if next_page_token: params["next_page_token"] = next_page_token
                
        try:
            response = requests.get(url, params=params)
            dados = response.json()
            if "error" in dados and pagina == 0: return [{"erro": True, "mensagem": f"O Google Hotels recusou a busca: {dados['error']}"}]
            hoteis_pagina = dados.get("properties", [])
            if not hoteis_pagina: break
            hoteis_brutos.extend(hoteis_pagina)
            serpapi_pagination = dados.get("serpapi_pagination", {})
            next_page_token = serpapi_pagination.get("next_page_token")
            if len(hoteis_brutos) >= 100 or not next_page_token: break
        except Exception as e:
            if pagina == 0: return [{"erro": True, "mensagem": f"Falha na conexão de hotéis: {str(e)}"}]
            break 

    if not hoteis_brutos: return [{"erro": True, "mensagem": f"O Google não encontrou propriedades para a busca: '{termo_busca}'."}]
    
    hoteis_filtrados = []
    for h in hoteis_brutos:
        nome = h.get("name", "Hotel Desconhecido")
        nota = round(h.get("overall_rating", 0.0), 1)
        bairro_oficial = h.get("neighborhood", "")
        
        if bairros_real:
            bairros_permitidos = [b.strip().lower() for b in bairros_real.split(",")]
            texto_para_validar = f"{bairro_oficial} {nome}".lower()
            passou_cerca = False
            for bp in bairros_permitidos:
                if bp in texto_para_validar:
                    passou_cerca = True
                    break
            if not passou_cerca: continue 

        classe_str = str(h.get("hotel_class", "0"))
        estrelas = int(''.join(filter(str.isdigit, classe_str))) if any(c.isdigit() for c in classe_str) else 0
        rate_info = h.get("total_rate", {}) or h.get("rate_per_night", {})
        preco_total = rate_info.get("extracted_lowest", 0)
        
        if preco_total == 0:
            preco_str = str(rate_info.get("lowest", "0")).replace("R$", "").replace("\u00a0", "").replace(".", "").replace(",", ".").strip()
            try: preco_total = float(preco_str)
            except: preco_total = 0
        
        link_original = h.get("link", "")
        if "travel/search" in link_original or not link_original:
            termo_link = urllib.parse.quote_plus(f"{nome} {local_busca}")
            link_direto = f"https://www.google.com/search?q={termo_link}"
        else: link_direto = link_original
        
        if nota >= min_nota and preco_total > 0:
            if estrelas >= min_estrelas or estrelas == 0:
                hoteis_filtrados.append({"nome": nome, "bairro": bairro_oficial if bairro_oficial else (bairros_real if bairros_real else cidade_limpa), "estrelas": estrelas if estrelas > 0 else "N/A", "nota": nota, "preco_total": preco_total, "preco_formatado": formatar_moeda(preco_total), "link": link_direto})
    
    hoteis_filtrados = sorted(hoteis_filtrados, key=lambda x: x["preco_total"])
    if len(hoteis_filtrados) == 0: return [{"erro": True, "mensagem": f"NENHUM hotel passou nos seus filtros estritos de Bairro, Nota ou Estrelas."}]
    return hoteis_filtrados

def buscar_pacotes_completos(tipo_voo, origem, destino, incluir_hospedagem, cidade_hotel, bairros_hotel, data_ida_str, data_volta_str, adultos, criancas, idades_criancas, quartos, max_duracao, max_escalas, orcamento_max, min_estrelas, min_nota, palavra_chave, filtro_cia, filtro_horario_ida="Qualquer horário", filtro_horario_volta="Qualquer horário"):
    
    lista_hoteis = []
    if incluir_hospedagem:
        lista_hoteis = buscar_hoteis_google(cidade_hotel, bairros_hotel, data_ida_str, data_volta_str, adultos, criancas, idades_criancas, quartos, min_estrelas, min_nota, palavra_chave)
        if len(lista_hoteis) > 0 and "erro" in lista_hoteis[0]: return {"status": "erro", "mensagem": lista_hoteis[0]["mensagem"]}

    url = "https://serpapi.com/search.json"
    total_passageiros = adultos + criancas
    params = {"engine": "google_flights", "departure_id": origem, "arrival_id": destino, "outbound_date": data_ida_str, "currency": "BRL", "hl": "pt-br", "gl": "br", "api_key": SERPAPI_KEY, "adults": total_passageiros}
    
    if tipo_voo == "Somente Ida": params["type"] = "2"
    else:
        params["type"] = "1"
        params["return_date"] = data_volta_str
        
    try:
        response = requests.get(url, params=params)
        dados = response.json()
        link_voo_oficial = dados.get("search_metadata", {}).get("google_flights_url", "")
        if not link_voo_oficial: link_voo_oficial = f"https://www.google.com/travel/flights?q=Flights%20from%20{origem}%20to%20{destino}"
            
        todos_voos_brutos = dados.get("best_flights", []) + dados.get("other_flights", [])
        if not todos_voos_brutos: return {"status": "erro", "mensagem": f"Nenhum voo para a rota {origem} ➔ {destino} nestas datas."}
        
        voos_validos = []
        for v in todos_voos_brutos:
            preco_voo = v.get("price", 0) 
            trecho_ida = v.get("flights", [])
            if not trecho_ida: continue
            
            duracao_ida_h = sum([seg.get("duration", 0) for seg in trecho_ida]) / 60
            escalas_ida = len(trecho_ida) - 1
            cia_ida = trecho_ida[0].get("airline", "N/A")
            saida_ida = trecho_ida[0].get("departure_airport", {}).get("time", "--:--")
            chegada_ida = trecho_ida[-1].get("arrival_airport", {}).get("time", "--:--")
            
            duracao_volta_h, escalas_volta = 0, 0
            cia_volta, saida_volta, chegada_volta = "Escolher no site", "--:--", "--:--"
            tem_detalhe_volta = False
            
            if tipo_voo == "Ida e Volta":
                trecho_volta = v.get("return_flights", [])
                if trecho_volta:
                    tem_detalhe_volta = True
                    duracao_volta_h = sum([seg.get("duration", 0) for seg in trecho_volta]) / 60
                    escalas_volta = len(trecho_volta) - 1
                    cia_volta = trecho_volta[0].get("airline", "N/A")
                    saida_volta = trecho_volta[0].get("departure_airport", {}).get("time", "--:--")
                    chegada_volta = trecho_volta[-1].get("arrival_airport", {}).get("time", "--:--")
            
            passou_cia = True
            if filtro_cia.strip():
                filtro = filtro_cia.strip().lower()
                if filtro not in cia_ida.lower() and filtro not in cia_volta.lower(): passou_cia = False
            
            passou_filtro_volta = True
            if tem_detalhe_volta:
                if duracao_volta_h > max_duracao or escalas_volta > max_escalas: passou_filtro_volta = False

            passou_horario_ida = validar_horario(saida_ida, filtro_horario_ida)
            passou_horario_volta = True
            if tem_detalhe_volta: passou_horario_volta = validar_horario(saida_volta, filtro_horario_volta)

            if (passou_cia and duracao_ida_h <= max_duracao and escalas_ida <= max_escalas and passou_filtro_volta and passou_horario_ida and passou_horario_volta):
                voos_validos.append({
                    "preco_voo": preco_voo, "preco_formatado": formatar_moeda(preco_voo), "link": link_voo_oficial,
                    "cia_ida": cia_ida, "saida_ida": saida_ida, "chegada_ida": chegada_ida, "duracao_ida": round(duracao_ida_h, 1), "escalas_ida": escalas_ida,
                    "cia_volta": cia_volta, "saida_volta": saida_volta, "chegada_volta": chegada_volta, "duracao_volta": round(duracao_volta_h, 1), "escalas_volta": escalas_volta,
                    "logo": obter_logo_cia(cia_ida)
                })
        
        if not voos_validos: return {"status": "erro", "mensagem": "Nenhum voo atendeu aos seus filtros de duração, escalas, CIA ou HORÁRIO."}
            
        voos_validos = sorted(voos_validos, key=lambda x: x["preco_voo"])
        pacotes_filtrados = []
        
        if incluir_hospedagem:
            voo_campeao = voos_validos[0]
            menor_custo_absoluto = voo_campeao["preco_voo"] + lista_hoteis[0]["preco_total"]
            if menor_custo_absoluto > orcamento_max:
                return {"status": "erro", "mensagem": f"A opção mais barata estourou o limite: **{formatar_moeda(menor_custo_absoluto)}**."}

            for h in lista_hoteis:
                custo_total = h["preco_total"] + voo_campeao["preco_voo"]
                if custo_total <= orcamento_max:
                    pacotes_filtrados.append({"custo_total": custo_total, "custo_formatado": formatar_moeda(custo_total), "hotel": h, "voo": voo_campeao})
        else:
            if voos_validos[0]["preco_voo"] > orcamento_max:
                return {"status": "erro", "mensagem": f"A opção de voo mais barata estourou o limite: **{formatar_moeda(voos_validos[0]['preco_voo'])}**."}
                
            for v in voos_validos[:15]: 
                if v["preco_voo"] <= orcamento_max:
                    pacotes_filtrados.append({"custo_total": v["preco_voo"], "custo_formatado": formatar_moeda(v["preco_voo"]), "hotel": None, "voo": v})
                    
        pacotes_filtrados = sorted(pacotes_filtrados, key=lambda x: x["custo_total"])
        return {"status": "sucesso", "pacotes": pacotes_filtrados}
            
    except Exception as e: return {"status": "erro", "mensagem": f"Falha na comunicação: {str(e)}"}

# ==========================================
# MOTOR DE FUNDO (BACKGROUND THREAD)
# ==========================================
def loop_vigilante():
    while True:
        try:
            bd = carregar_bd()
            agora = datetime.datetime.now().strftime("%H:%M")
            hoje = datetime.datetime.now().strftime("%Y-%m-%d")
            houve_mudanca = False
            
            for cod, info in bd.items():
                if info.get("monitorar") == True and info.get("tipo_voo") != "Multidestino":
                    horario_alvo = info.get("horario", "18:00")
                    ultimo_disparo = info.get("ultimo_disparo", "")
                    
                    if agora == horario_alvo and ultimo_disparo != hoje:
                        res = buscar_pacotes_completos(
                            info["tipo_voo"], info["origem"], info["destino"], info.get("incluir_hospedagem", True),
                            info.get("cidade_hotel", info["destino"]), info.get("bairros_hotel", ""), 
                            info["data_ida"], info["data_volta"], info["adultos"], info["criancas"], info.get("idades_criancas", []), info.get("quartos", 1), info["max_duracao"], info["max_escalas"], 
                            info["orcamento_max"], info.get("min_estrelas", 3), info.get("min_nota", 4.0), info.get("palavra_chave", ""), info.get("filtro_cia", ""),
                            info.get("filtro_horario_ida", "Qualquer horário"), info.get("filtro_horario_volta", "Qualquer horário")
                        )
                        
                        if res["status"] == "sucesso" and len(res["pacotes"]) > 0:
                            pacotes_unicos = []
                            if info.get("incluir_hospedagem", True):
                                hoteis_vistos = set()
                                for pct in res["pacotes"]:
                                    if pct['hotel']['nome'] not in hoteis_vistos:
                                        pacotes_unicos.append(pct)
                                        hoteis_vistos.add(pct['hotel']['nome'])
                            else:
                                voos_vistos = set()
                                for pct in res["pacotes"]:
                                    id_voo = f"{pct['voo']['cia_ida']}-{pct['voo']['saida_ida']}"
                                    if id_voo not in voos_vistos:
                                        pacotes_unicos.append(pct)
                                        voos_vistos.add(id_voo)
                            
                            titulo_wpp = "Voo+Hotel" if info.get("incluir_hospedagem", True) else "Apenas Voos"
                            msg_diaria = f"⏰ *ATUALIZAÇÃO DIÁRIA ({horario_alvo})*\nCódigo: {cod}\n\nEncontramos {len(pacotes_unicos)} opções ({titulo_wpp}) hoje:\n\n"
                            
                            for i, pct in enumerate(pacotes_unicos[:2], 1):
                                msg_diaria += f"🏆 *OPÇÃO {i}: {pct['custo_formatado']}*\n"
                                if info.get("incluir_hospedagem", True):
                                    msg_diaria += f"🏨 {pct['hotel']['nome']} (Nota: {pct['hotel']['nota']})\n"
                                    msg_diaria += f"🔗 Hotel: {pct['hotel']['link']}\n"
                                msg_diaria += f"✈️ Voo: {pct['voo']['cia_ida']} ({pct['voo']['preco_formatado']})\n"
                                msg_diaria += f"🔗 Voo: {pct['voo']['link']}\n"
                                msg_diaria += "-----------------------\n"
                            
                            msg_diaria += f"🛑 *Para cancelar os avisos automáticos, acesse o painel e clique em Cancelar.*"
                            testar_alerta_whatsapp(info["telefone"], msg_diaria)
                        
                        info["ultimo_disparo"] = hoje
                        houve_mudanca = True
            if houve_mudanca: salvar_bd(bd)
        except Exception as e: pass
        time.sleep(30)

@st.cache_resource
def iniciar_motor_fundo():
    t = threading.Thread(target=loop_vigilante, daemon=True)
    t.start()
    return True

iniciar_motor_fundo()

# ==========================================
# BARRA LATERAL E INTERFACE PRINCIPAL
# ==========================================
st.sidebar.title("🤖 Painel do Robô Automático")

bd_atual = carregar_bd()
with st.sidebar.expander("📂 Consultar Orçamentos Salvos"):
    if not bd_atual: st.info("Nenhum orçamento salvo.")
    else:
        for codigo, info in bd_atual.items():
            status_monitoramento = "✅ ATIVO" if info.get("monitorar") else "⏸️ Pausado"
            st.markdown(f"**Código:** `{codigo}`")
            st.write(f"Status: {status_monitoramento}")
            st.divider()

with st.sidebar.expander("📲 Ativar Monitoramento Automático"):
    st.write("Insira o código do seu pacote abaixo para receber as variações de preço todos os dias!")
    codigo_simulacao = st.text_input("Código do Orçamento (ex: A1B2C3)")
    resposta_simulacao = st.selectbox("Ação", ["ATIVAR Monitoramento", "CANCELAR Monitoramento"])
    if st.button("Aplicar Ação", use_container_width=True):
        codigo_limpo = codigo_simulacao.strip().upper()
        if codigo_limpo in bd_atual:
            if resposta_simulacao == "ATIVAR Monitoramento":
                bd_atual[codigo_limpo]["monitorar"] = True
                salvar_bd(bd_atual)
                st.sidebar.success(f"✅ Monitoramento {codigo_limpo} ATIVADO! Avisaremos no WhatsApp cadastrado.")
            else:
                bd_atual[codigo_limpo]["monitorar"] = False
                salvar_bd(bd_atual)
                st.sidebar.warning(f"🛑 Monitoramento {codigo_limpo} CANCELADO!")
        else:
            st.sidebar.error("Código não encontrado no banco de dados.")

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
        with colZ1: seu_numero = st.text_input("WhatsApp (ex: +5511999999999)")
        with colZ2: horario_alerta = st.time_input("Horário Diário", datetime.time(18, 0))

st.divider()

if st.button("Buscar Pacotes & Salvar Automação", type="primary", use_container_width=True):
    if not seu_numero:
        st.warning("⚠️ Preencha o número de WhatsApp.")
    elif tipo_voo != "Multidestino" and (not origem_nome or not destino_nome or not orcamento_max):
        st.error("⚠️ Por favor, selecione a Origem, Destino e o Orçamento Máximo para buscar.")
    elif tipo_voo == "Multidestino":
        st.info("A funcionalidade Voo+Hotel para Multidestinos entrará em breve. No momento, concentre-se nas abas 'Ida e Volta' ou 'Somente Ida'.")
    else:
        aviso_spinner = "Pescando resultados ocultos em múltiplas páginas do Google e cruzando com os voos..." if incluir_hospedagem else "Analisando malhas aéreas e tarifas disponíveis..."
        with st.spinner(aviso_spinner):
            
            data_ida_str = data_ida.strftime("%Y-%m-%d")
            data_volta_str = data_volta.strftime("%Y-%m-%d") if data_volta else ""
            hora_str = horario_alerta.strftime("%H:%M")
            
            resultado = buscar_pacotes_completos(
                tipo_voo, origem, destino, incluir_hospedagem, cidade_hotel, bairros_hotel, data_ida_str, data_volta_str, adultos, criancas, idades_criancas, quartos,
                max_duracao, max_escalas, orcamento_max, min_estrelas, min_nota, palavra_chave, filtro_cia, filtro_horario_ida, filtro_horario_volta
            )
            
            if resultado["status"] == "sucesso":
                lista_pacotes = resultado["pacotes"]
                
                codigo_orcamento = str(uuid.uuid4())[:6].upper()
                bd_atual[codigo_orcamento] = {
                    "monitorar": False,
                    "telefone": seu_numero, "horario": hora_str, "ultimo_disparo": "",
                    "origem": origem, "destino": destino, "incluir_hospedagem": incluir_hospedagem, "cidade_hotel": cidade_hotel, "bairros_hotel": bairros_hotel,
                    "tipo_voo": tipo_voo, "data_ida": data_ida_str, "data_volta": data_volta_str,
                    "adultos": adultos, "criancas": criancas, "idades_criancas": idades_criancas, "quartos": quartos, "max_duracao": max_duracao, "max_escalas": max_escalas,
                    "orcamento_max": orcamento_max, "min_estrelas": min_estrelas, "min_nota": min_nota, "palavra_chave": palavra_chave, "filtro_cia": filtro_cia,
                    "filtro_horario_ida": filtro_horario_ida, "filtro_horario_volta": filtro_horario_volta
                }
                salvar_bd(bd_atual)
                
                pacotes_unicos = []
                if incluir_hospedagem:
                    hoteis_vistos = set()
                    for pct in lista_pacotes:
                        nome_h = pct['hotel']['nome']
                        if nome_h not in hoteis_vistos:
                            pacotes_unicos.append(pct)
                            hoteis_vistos.add(nome_h)
                else:
                    voos_vistos = set()
                    for pct in lista_pacotes:
                        id_voo = f"{pct['voo']['cia_ida']}-{pct['voo']['saida_ida']}"
                        if id_voo not in voos_vistos:
                            pacotes_unicos.append(pct)
                            voos_vistos.add(id_voo)
                
                texto_sucesso = f"🎉 Exibindo TODAS as {len(pacotes_unicos)} opções únicas do menor para o maior preço! CÓDIGO: {codigo_orcamento}"
                st.success(texto_sucesso)
                st.info("💡 **Dica do Robô:** O valor dos voos abaixo já reflete o total para todos os passageiros selecionados!")
                
                titulo_wpp = "Voo+Hotel" if incluir_hospedagem else "Apenas Voos"
                msg_automatica = f"🚨 *PACOTES ENCONTRADOS ({titulo_wpp})* 🚨\n\nEncontramos {len(pacotes_unicos)} opções no total! Aqui estão as 2 melhores:\n\n"
                
                for i, pct in enumerate(pacotes_unicos[:2], 1):
                    msg_automatica += f"🏆 *OPÇÃO {i}: {pct['custo_formatado']}*\n"
                    if incluir_hospedagem:
                        msg_automatica += f"🏨 {pct['hotel']['nome']} ({pct['hotel']['estrelas']}⭐ - Nota: {pct['hotel']['nota']})\n"
                        msg_automatica += f"🔗 Hotel: {pct['hotel']['link']}\n"
                    msg_automatica += f"✈️ Voo: {pct['voo']['cia_ida']} ({pct['voo']['preco_formatado']})\n"
                    msg_automatica += f"🔗 Voo: {pct['voo']['link']}\n"
                    msg_automatica += "-----------------------\n"
                
                msg_automatica += f"\n🤖 *MONITORAMENTO DIÁRIO ({hora_str})*\nPara ligar os alertas deste pacote, use o menu lateral do site e digite o código: *{codigo_orcamento}*"
                
                sucesso_wa, retorno_wa = testar_alerta_whatsapp(seu_numero, msg_automatica)
                if not sucesso_wa:
                    if "1600" in str(retorno_wa):
                        st.error("⚠️ **O pacote foi montado, mas o WhatsApp bloqueou a mensagem por ser longa demais!** A operadora cortou os links gigantes do Google.")
                    else:
                        st.error(f"⚠️ **Falha na operadora Twilio:** `{retorno_wa}`\n\n**Solução:** Envie o comando de ativação para o número `+1 415 523 8886`.")
                else:
                    st.success(f"✅ As opções foram disparadas com sucesso para o WhatsApp {seu_numero}!")

                for pct in pacotes_unicos: 
                    with st.container(border=True):
                        if incluir_hospedagem:
                            st.markdown(f"### 🏨 {pct['hotel']['nome']} + ✈️ Voos ({pct['custo_formatado']})")
                            colA, colB = st.columns(2)
                            
                            with colA:
                                st.markdown(f"#### 🏨 Hospedagem")
                                st.write(f"**💰 Estadia Total:** {pct['hotel']['preco_formatado']}")
                                st.write(f"📍 Região: {pct['hotel']['bairro']}")
                                st.write(f"⭐ Classificação: {pct['hotel']['estrelas']} | 🏆 Nota: {pct['hotel']['nota']}/5.0")
                                st.markdown(f"[🔗 **Ir Direto para o Hotel**]({pct['hotel']['link']})")
                                
                            with colB:
                                st.markdown(f"""
                                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
                                        <img src="{pct['voo']['logo']}" width="40" style="border-radius: 4px;">
                                        <h4 style="margin: 0;">✈️ Voos ({pct['voo']['cia_ida']})</h4>
                                    </div>
                                """, unsafe_allow_html=True)
                                st.write(f"**💰 Passagens Totais:** {pct['voo']['preco_formatado']} *(Pode estar mais barato no site!)*")
                                st.write(f"🛫 IDA: {pct['voo']['saida_ida']} - {pct['voo']['chegada_ida']}")
                                if tipo_voo == "Ida e Volta":
                                    if pct['voo']['cia_volta'] == "Escolher no site":
                                        st.write("🛬 VOLTA: *Horário a escolher no site (Preço já incluso)*")
                                    else:
                                        st.write(f"🛬 VOLTA: {pct['voo']['cia_volta']} | {pct['voo']['saida_volta']} - {pct['voo']['chegada_volta']}")
                                st.markdown(f"[🔗 **Ver Passagens no Google**]({pct['voo']['link']})")
                        else:
                            st.markdown(f"""
                                <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 10px;">
                                    <img src="{pct['voo']['logo']}" width="50" style="border-radius: 5px;">
                                    <h3 style="margin: 0;">✈️ Passagens Aéreas ({pct['custo_formatado']})</h3>
                                </div>
                            """, unsafe_allow_html=True)
                            st.write(f"**Cia Aérea:** {pct['voo']['cia_ida']}")
                            st.write(f"🛫 IDA: {pct['voo']['saida_ida']} - {pct['voo']['chegada_ida']} (Escalas: {pct['voo']['escalas_ida']})")
                            if tipo_voo == "Ida e Volta":
                                if pct['voo']['cia_volta'] == "Escolher no site":
                                    st.write("🛬 VOLTA: *Horário a escolher no site (Preço já incluso)*")
                                else:
                                    st.write(f"🛬 VOLTA: {pct['voo']['cia_volta']} | {pct['voo']['saida_volta']} - {pct['voo']['chegada_volta']} (Escalas: {pct['voo']['escalas_volta']})")
                            st.markdown(f"[🔗 **Ver Passagens no Google**]({pct['voo']['link']})")
            else:
                st.warning("⚠️ Aviso do Robô:")
                st.markdown(resultado['mensagem'])
