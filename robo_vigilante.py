# código final 26/02/2026
# robo_vigilante.py
import datetime
import requests
import json
import time
import os # Biblioteca essencial para ler as variáveis do Render
import urllib.parse
from twilio.rest import Client

print("Iniciando o Motor Vigilante do Monitor de Viagens...")

# ==========================================
# CONFIGURAÇÕES E CHAVES (LENDO DO SERVIDOR)
# ==========================================
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
FIREBASE_URL = os.environ.get("FIREBASE_URL") 

def carregar_bd():
    try:
        # Removemos o st.secrets e usamos a FIREBASE_URL lida acima
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

# ... (Mantenha as funções buscar_hoteis_google e buscar_pacotes_completos iguais) ...

def loop_vigilante():
    print("Motor em vigília ativa. Verificando relógio...")
    while True:
        try:
            bd = carregar_bd()
            fuso_br = datetime.timezone(datetime.timedelta(hours=-3))
            agora = datetime.datetime.now(fuso_br).strftime("%H:%M")
            hoje = datetime.datetime.now(fuso_br).strftime("%Y-%m-%d")
            
            for cod, info in bd.items():
                if info.get("monitorar") == True:
                    horario_alvo = info.get("horario", "08:45")
                    ultimo_disparo = info.get("ultimo_disparo", "")
                    
                    if agora == horario_alvo and ultimo_disparo != hoje:
                        print(f"⏰ Hora do show! Disparando código {cod}...")
                        processar_disparo(cod, info, hoje)
            
        except Exception as e: print(f"Erro no loop: {e}")
        time.sleep(30) 

if __name__ == "__main__":
    loop_vigilante()
