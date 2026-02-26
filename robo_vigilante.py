# código final 26/02/2026
# robo_vigilante.py
import datetime
import requests
import json
import time
import os # ESSENCIAL: Isso faz o robô ler o 'Environment' do Render
import urllib.parse
from twilio.rest import Client

print("Iniciando o Motor Vigilante do Monitor de Viagens...")

# ==========================================
# CONFIGURAÇÕES E CHAVES (LENDO DO RENDER)
# ==========================================
# Aqui substituímos o 'st.secrets' por 'os.environ.get'
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
    except Exception as e:
        print(f"Erro ao carregar banco de dados: {e}")
    return {}

# ... [O restante das funções de busca permanece igual] ...

def loop_vigilante():
    print("Motor em vigília ativa no Render. Verificando relógio...")
    while True:
        try:
            bd = carregar_bd()
            fuso_br = datetime.timezone(datetime.timedelta(hours=-3))
            agora = datetime.datetime.now(fuso_br).strftime("%H:%M")
            hoje = datetime.datetime.now(fuso_br).strftime("%Y-%m-%d")
            
            for cod, info in bd.items():
                if info.get("monitorar") == True:
                    horario_alvo = info.get("horario", "09:15")
                    ultimo_disparo = info.get("ultimo_disparo", "")
                    
                    if agora == horario_alvo and ultimo_disparo != hoje:
                        print(f"⏰ Hora do show! Processando código {cod}...")
                        # O robô agora tem as chaves para pesquisar e enviar o WhatsApp
                        processar_disparo(cod, info, hoje)
            
        except Exception as e: 
            print(f"Erro no loop: {e}")
            
        time.sleep(30) 

if __name__ == "__main__":
    loop_vigilante()
