# código final 20/01/2026
# robo_vigilante.py
import datetime
import requests
import time
import os
from twilio.rest import Client

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
FIREBASE_URL = os.environ.get("FIREBASE_URL").rstrip('/')

print("Iniciando o Motor Vigilante Profissional...")

def carregar_bd():
    try:
        res = requests.get(f"{FIREBASE_URL}/monitoramentos.json")
        return res.json() if res.status_code == 200 and res.json() else {}
    except: return {}

def salvar_bd(dados):
    try:
        requests.put(f"{FIREBASE_URL}/monitoramentos.json", json=dados)
    except: pass

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
        msg = f"⏰ *ALERTA DIÁRIO!* {len(pacotes)} OPÇÕES ENCONTRADAS (Cód: {codigo})\n\n"
        for i, p in enumerate(pacotes, 1):
            msg += f"{i}️⃣ *R$ {p['total']:,.2f}*\n✈️ {p['voo']}\n🏨 {p['hotel']}\n🔗 Voo: {p['link_v']}\n"
            if p['link_h']: msg += f"🔗 Hotel: {p['link_h']}\n"
            msg += "\n"
        dest = f"whatsapp:{numero}" if not numero.startswith("whatsapp:") else numero
        client.messages.create(from_=TWILIO_WHATSAPP_NUMBER, body=msg, to=dest)
        return True
    except Exception as e:
        print(f"Erro WhatsApp: {e}") 
        return False

def loop_vigilante():
    print("Motor em vigília ativa no Render. Verificando relógio...")
    while True:
        try:
            bd = carregar_bd()
            fuso_br = datetime.timezone(datetime.timedelta(hours=-3))
            agora = datetime.datetime.now(fuso_br).strftime("%H:%M")
            hoje = datetime.datetime.now(fuso_br).strftime("%Y-%m-%d")
            
            houve_mudanca = False
            for cod, info in bd.items():
                if info.get("monitorar") == True:
                    if agora == info.get("horario") and info.get("ultimo_disparo") != hoje:
                        print(f"⏰ Disparando código {cod}...")
                        
                        # Busca o pacote com as mesmas premissas do site
                        res = buscar_pacotes_completos(
                            info.get("origem"), info.get("destino"), info.get("data_ida"), info.get("data_volta", ""),
                            info.get("adultos", 1), info.get("criancas", 0), info.get("idades_criancas", []),
                            info.get("orcamento_max", 99999), info.get("incluir_hospedagem", False), info.get("cidade_hotel", "")
                        )
                        
                        if res:
                            # Gravar histórico no bd para o gráfico
                            if "historico" not in info:
                                info["historico"] = {}
                            info["historico"][hoje] = res[0]["total"]
                            
                            # Envia o whatsapp
                            if enviar_alerta_whatsapp(info.get("telefone"), res, cod):
                                info["ultimo_disparo"] = hoje
                                houve_mudanca = True
            
            if houve_mudanca: 
                salvar_bd(bd)
        except Exception as e: print(f"Erro no loop: {e}")
        time.sleep(30)

if __name__ == "__main__":
    loop_vigilante()
