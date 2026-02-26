# código final 20/01/2026
# robo_vigilante.py
import datetime
import requests
import time
import os
import urllib.parse
import re
from twilio.rest import Client

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
FIREBASE_URL = os.environ.get("FIREBASE_URL").rstrip('/')

print("Iniciando o Motor Vigilante com Controle de Frequência...")

def carregar_bd():
    try:
        res = requests.get(f"{FIREBASE_URL}/monitoramentos.json")
        return res.json() if res.status_code == 200 and res.json() else {}
    except: return {}

def salvar_bd(dados):
    try:
        requests.put(f"{FIREBASE_URL}/monitoramentos.json", json=dados)
    except: pass

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

def obter_link_direto_ou_nada(link_bruto):
    if not link_bruto: return None
    parsed = urllib.parse.urlparse(str(link_bruto))
    
    if "google" not in parsed.netloc and parsed.scheme in ['http', 'https']:
        return str(link_bruto)
        
    try:
        qs = urllib.parse.parse_qs(parsed.query)
        for param in ['adurl', 'url']:
            if param in qs:
                target = str(qs[param][0])
                target_parsed = urllib.parse.urlparse(target)
                if target.startswith('http') and "google" not in target_parsed.netloc:
                    return target
    except: pass
    
    return None

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
            if preco > 0: hoteis.append({"nome": h.get("name"), "preco": preco, "nota": h.get("overall_rating", 0), "link": h.get("link")})
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
            print(f"Erro da SerpApi (Voos): {res['error']}")
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
    except: return []

def buscar_produtos_google(metodo, produto_base, marca, termos_excluir, link_produto, orcamento):
    try:
        params = {"hl": "pt-br", "gl": "br", "google_domain": "google.com.br", "currency": "BRL", "device": "desktop", "api_key": SERPAPI_KEY}
        
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
            print(f"Falha na Busca de Produtos (Google): {res['error']}")
            return []
            
        encontrados = []
        
        if "shopping_results" in res:
            for item in res["shopping_results"]:
                preco_bruto = item.get("extracted_price") or item.get("price")
                preco = parse_price(preco_bruto)
                
                if preco <= orcamento:
                    link_final = obter_link_direto_ou_nada(item.get("link", ""))
                    if not link_final:
                        continue
                        
                    encontrados.append({
                        "nome": item.get("title", "Produto"),
                        "total": preco, 
                        "loja": item.get("source", "Loja não informada"),
                        "link": link_final
                    })
                    if len(encontrados) >= 5: break
        
        elif "product_results" in res:
            nome_produto = res.get("product_results", {}).get("title", "Produto Rastreado")
            
            for seller in res.get("sellers_results", {}).get("online_sellers", []):
                preco_bruto = seller.get("base_price")
                preco = parse_price(preco_bruto)
                
                if preco <= orcamento:
                    link_final = obter_link_direto_ou_nada(seller.get("link", ""))
                    if not link_final:
                        continue
                        
                    encontrados.append({
                        "nome": nome_produto,
                        "total": preco,
                        "loja": seller.get("name", "Loja não informada"),
                        "link": link_final
                    })
                    if len(encontrados) >= 5: break
                    
        return sorted(encontrados, key=lambda x: x["total"])
    except Exception as e:
        print("Erro Produto:", e)
        return []

def enviar_alerta_whatsapp(numero, itens, codigo, tipo_monitoramento, freq):
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        if tipo_monitoramento == "viagem":
            msg = f"⏰ *ALERTA {freq.upper()}!* {len(itens)} OPÇÕES DE VIAGEM (Cód: {codigo})\n\n"
            for i, p in enumerate(itens, 1):
                msg += f"{i}️⃣ *R$ {p['total']:,.2f}*\n✈️ {p['voo']}\n🏨 {p['hotel']}\n🔗 Voo: {p['link_v']}\n"
                if p.get('link_h'): msg += f"🔗 Hotel: {p['link_h']}\n"
                msg += "\n"
        else:
            msg = f"⏰ *ALERTA {freq.upper()}!* {len(itens)} OFERTAS DE PRODUTO (Cód: {codigo})\n\n"
            for i, p in enumerate(itens, 1):
                msg += f"{i}️⃣ *R$ {p['total']:,.2f}* na loja {p['loja']}\n🛒 {p['nome'][:45]}...\n🔗 Acesse Diretamente a Oferta: {p['link']}\n\n"
        
        num_limpo = str(numero).strip().replace("-", "").replace(" ", "").replace("+", "").replace("whatsapp:", "")
        if len(num_limpo) == 10 or len(num_limpo) == 11:
            num_limpo = f"55{num_limpo}"
        dest = f"whatsapp:+{num_limpo}"
        
        client.messages.create(from_=TWILIO_WHATSAPP_NUMBER, body=msg, to=dest)
        return True
    except Exception as e:
        print(f"Erro WhatsApp: {e}")
        return False

def loop_vigilante():
    print("Motor em vigília ativa no Render. Verificando relógio e frequências...")
    while True:
        try:
            bd = carregar_bd()
            fuso_br = datetime.timezone(datetime.timedelta(hours=-3))
            agora_dt = datetime.datetime.now(fuso_br)
            agora_str = agora_dt.strftime("%H:%M")
            hoje_str = agora_dt.strftime("%Y-%m-%d")
            agora_full_str = agora_dt.strftime("%Y-%m-%d %H:%M")
            
            h_atual = agora_dt.hour
            m_atual = agora_dt.minute
            
            houve_mudanca = False
            for cod, info in bd.items():
                if info.get("monitorar") == True:
                    freq = info.get("frequencia", "Diariamente")
                    horario_alvo = info.get("horario", "00:00")
                    data_criacao = info.get("data_criacao", hoje_str)
                    
                    try: H_alvo, M_alvo = map(int, horario_alvo.split(":"))
                    except: H_alvo, M_alvo = 0, 0
                    
                    ultimo_disp_full = info.get("ultimo_disparo_full", info.get("ultimo_disparo", ""))
                    
                    disp_hoje = (ultimo_disp_full[:10] == hoje_str) if len(ultimo_disp_full) >= 10 else False
                    disp_esta_hora = (ultimo_disp_full == agora_full_str)
                    
                    deve_disparar = False
                    
                    if freq == "Diariamente":
                        if agora_str == horario_alvo and not disp_hoje: deve_disparar = True
                            
                    elif freq == "A cada hora":
                        if m_atual == M_alvo and not disp_esta_hora: deve_disparar = True
                            
                    elif freq == "2 vezes por dia":
                        if (h_atual % 12) == (H_alvo % 12) and m_atual == M_alvo and not disp_esta_hora: deve_disparar = True
                            
                    elif freq == "4 vezes por dia":
                        if (h_atual % 6) == (H_alvo % 6) and m_atual == M_alvo and not disp_esta_hora: deve_disparar = True
                            
                    elif freq == "Semanalmente":
                        try: dia_semana_base = datetime.datetime.strptime(data_criacao, "%Y-%m-%d").weekday()
                        except: dia_semana_base = agora_dt.weekday()
                        if agora_dt.weekday() == dia_semana_base and agora_str == horario_alvo and not disp_hoje: deve_disparar = True
                            
                    elif freq == "Mensalmente":
                        try: dia_mes_base = datetime.datetime.strptime(data_criacao, "%Y-%m-%d").day
                        except: dia_mes_base = agora_dt.day
                        if agora_dt.day == dia_mes_base and agora_str == horario_alvo and not disp_hoje: deve_disparar = True
                    
                    if deve_disparar:
                        print(f"⏰ Disparando código {cod} (Frequência: {freq})...")
                        tipo_mon = info.get("tipo_monitoramento", "viagem")
                        
                        if tipo_mon == "viagem":
                            res = buscar_pacotes_completos(
                                info.get("origem"), info.get("destino"), info.get("data_ida"), info.get("data_volta", ""),
                                info.get("adultos", 1), info.get("criancas", 0), info.get("idades_criancas", []),
                                info.get("orcamento_max", 99999), info.get("incluir_hospedagem", False), info.get("cidade_hotel", "")
                            )
                        else:
                            res = buscar_produtos_google(
                                info.get("metodo_busca"), info.get("produto_base"), info.get("marca"), 
                                info.get("termos_excluir"), info.get("link_produto"), info.get("orcamento_max", 99999)
                            )
                        
                        if res:
                            if "historico" not in info: info["historico"] = {}
                            info["historico"][agora_full_str] = res[0]["total"]
                            
                            if enviar_alerta_whatsapp(info.get("telefone"), res, cod, tipo_mon, freq):
                                info["ultimo_disparo"] = hoje_str
                                info["ultimo_disparo_full"] = agora_full_str
                                houve_mudanca = True
            
            if houve_mudanca: salvar_bd(bd)
        except Exception as e: print(f"Erro no loop: {e}")
        time.sleep(30)

if __name__ == "__main__":
    loop_vigilante()
