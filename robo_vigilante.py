# código final 20/01/2026
# robo_vigilante.py
import datetime
import requests
import json
import time
import urllib.parse
import streamlit as st # Usado aqui apenas para ler o cofre (secrets.toml) da mesma forma que antes
from twilio.rest import Client

print("Iniciando o Motor Vigilante do Monitor de Viagens...")

# ==========================================
# CONFIGURAÇÕES E CHAVES DO COFRE
# ==========================================
TWILIO_ACCOUNT_SID = st.secrets["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = st.secrets["TWILIO_AUTH_TOKEN"]
TWILIO_WHATSAPP_NUMBER = st.secrets["TWILIO_WHATSAPP_NUMBER"]
SERPAPI_KEY = st.secrets["SERPAPI_KEY"]
FIREBASE_URL = st.secrets["FIREBASE_URL"] 

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
        if chave.lower() in nome_cia.lower(): return url_logo
    return "https://cdn-icons-png.flaticon.com/512/3125/3125713.png"

def formatar_moeda(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def testar_alerta_whatsapp(numero_destino, mensagem):
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        destino_formatado = numero_destino if numero_destino.startswith("whatsapp:") else f"whatsapp:{numero_destino}"
        message = client.messages.create(from_=TWILIO_WHATSAPP_NUMBER, body=mensagem, to=destino_formatado)
        print(f"WhatsApp enviado com sucesso para {numero_destino}")
        return True, message.sid
    except Exception as e:
        print(f"Erro no WhatsApp: {e}")
        return False, str(e)

def carregar_bd():
    try:
        res = requests.get(f"{FIREBASE_URL}/monitoramentos.json")
        if res.status_code == 200 and res.json() is not None:
            return res.json()
    except Exception as e:
        print(f"Erro ao carregar do Firebase: {e}")
    return {}

def salvar_bd(dados):
    try:
        requests.put(f"{FIREBASE_URL}/monitoramentos.json", json=dados)
    except Exception as e:
        print(f"Erro ao salvar no Firebase: {e}")

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
    local_busca = f"{bairros_real}, {cidade_limpa}" if bairros_real else cidade_limpa
        
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
            if not any(bp in texto_para_validar for bp in bairros_permitidos): continue

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
    params = {"engine": "google_flights", "departure_id": origem, "arrival_id": destino, "outbound_date": data_ida_str, "currency": "BRL", "hl": "pt-br", "gl": "br", "api_key": SERPAPI_KEY, "adults": (adultos + criancas)}
    
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

def processar_disparo(cod, info, hoje):
    print(f"Processando disparo para o código {cod}...")
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
        msg_diaria = f"⏰ *ATUALIZAÇÃO DIÁRIA - MONITOR DE VIAGENS*\nCódigo: {cod}\n\nEncontramos {len(pacotes_unicos)} opções ({titulo_wpp}) hoje:\n\n"
        for i, pct in enumerate(pacotes_unicos[:2], 1):
            msg_diaria += f"🏆 *OPÇÃO {i}: {pct['custo_formatado']}*\n"
            if info.get("incluir_hospedagem", True):
                msg_diaria += f"🏨 {pct['hotel']['nome']} (Nota: {pct['hotel']['nota']})\n"
                msg_diaria += f"🔗 {pct['hotel']['link']}\n"
            msg_diaria += f"✈️ Voo: {pct['voo']['cia_ida']} ({pct['voo']['preco_formatado']})\n"
            msg_diaria += f"🔗 {pct['voo']['link']}\n"
            msg_diaria += "-----------------------\n"
        
        msg_diaria += f"🛑 *Para cancelar os avisos automáticos, acesse o seu painel.*"
        
        sucesso, _ = testar_alerta_whatsapp(info["telefone"], msg_diaria)
        if sucesso:
            info["ultimo_disparo"] = hoje
            return True
    print(f"Não foram encontradas opções abaixo do orçamento para {cod}.")
    return False

def loop_vigilante():
    print("Iniciando loop infinito de varredura...")
    while True:
        try:
            bd = carregar_bd()
            fuso_br = datetime.timezone(datetime.timedelta(hours=-3))
            agora = datetime.datetime.now(fuso_br).strftime("%H:%M")
            hoje = datetime.datetime.now(fuso_br).strftime("%Y-%m-%d")
            houve_mudanca = False
            
            for cod, info in bd.items():
                if info.get("monitorar") == True and info.get("tipo_voo") != "Multidestino":
                    horario_alvo = info.get("horario", "18:00")
                    ultimo_disparo = info.get("ultimo_disparo", "")
                    
                    if agora >= horario_alvo and ultimo_disparo != hoje:
                        if processar_disparo(cod, info, hoje):
                            houve_mudanca = True
            
            if houve_mudanca: 
                salvar_bd(bd)
                
        except Exception as e: 
            print(f"Erro no loop principal: {e}")
            
        time.sleep(30) 

if __name__ == "__main__":
    loop_vigilante()
