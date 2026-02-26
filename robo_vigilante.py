# código final 26/02/2026 - VERSÃO INDUSTRIAL
# robo_vigilante.py
import datetime
import requests
import json
import time
import os 
import urllib.parse
from twilio.rest import Client

print("Iniciando o Motor Vigilante Profissional...")

# ==========================================
# CONFIGURAÇÕES E CHAVES (LENDO DO RENDER)
# ==========================================
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
FIREBASE_URL = os.environ.get("FIREBASE_URL") 

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
        client.messages.create(from_=TWILIO_WHATSAPP_NUMBER, body=mensagem, to=destino_formatado)
        return True
    except: return False

def buscar_pacotes_completos(tipo_voo, origem, destino, data_ida, data_volta, adultos, criancas, orcamento_max):
    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google_flights",
        "departure_id": origem,
        "arrival_id": destino,
        "outbound_date": data_ida,
        "return_date": data_volta,
        "currency": "BRL",
        "hl": "pt-br",
        "api_key": SERPAPI_KEY,
        "adults": (adultos + criancas)
    }
    try:
        res = requests.get(url, params=params).json()
        voos = res.get("best_flights", []) + res.get("other_flights", [])
        if voos and voos[0].get("price", 999999) <= orcamento_max:
            return {"status": "sucesso", "preco": voos[0]["price"], "link": res.get("search_metadata", "").get("google_flights_url")}
    except: pass
    return {"status": "erro"}

def processar_disparo(cod, info, hoje):
    res = buscar_pacotes_completos(
        info["tipo_voo"], info["origem"], info["destino"], 
        info["data_ida"], info["data_volta"], 
        info["adultos"], info["criancas"], info["orcamento_max"]
    )
    if res["status"] == "sucesso":
        msg = f"✅ *OFERTA ENCONTRADA!* (Código: {cod})\nPreço: R$ {res['preco']}\nLink: {res['link']}"
        if testar_alerta_whatsapp(info["telefone"], msg):
            info["ultimo_disparo"] = hoje
            return True
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
                        if processar_disparo(cod, info, hoje):
                            houve_mudanca = True
            
            if houve_mudanca: salvar_bd(bd)
        except Exception as e: print(f"Erro: {e}")
        time.sleep(30)

if __name__ == "__main__":
    loop_vigilante()
