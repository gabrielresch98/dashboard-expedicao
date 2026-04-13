from flask import Flask, jsonify, render_template
import requests
import json
import threading
import time
from datetime import datetime, timezone

app = Flask(__name__)

# ─── CONFIGURAÇÃO ─────────────────────────────────────────────────────────────
CONTAS = {
    "udx": {
        "nome": "UDX",
        "token": "ced66a42848f546e630ba4f44ccbe9203ef8ca7f",
    },
    "rgx": {
        "nome": "RGX",
        "token": "7478429c9b64d4db35c66ade10743a1dd33b83ad164aa8ce1cdc266c59a4d1ad",
    },
}

BASE_URL = "https://api.tiny.com.br/api2"

SITUACOES = {
    "aguardando":   "1",
    "em_separacao": "4",
    "separadas":    "2",
    "embaladas":    "3",
}

TRANSPORTADORAS = {
    "mandae":   ["mandaê", "mandae"],
    "correios": ["correios", "pac", "sedex"],
}

# Cache de dados em memória
dados_cache = {}
ultima_atualizacao = None

# ─── FUNÇÕES ──────────────────────────────────────────────────────────────────

def pesquisar_separacoes(token, situacao):
    url    = f"{BASE_URL}/separacao.pesquisa.php"
    itens  = []
    pagina = 1
    while True:
        payload = {"token": token, "formato": "json", "situacao": situacao, "pagina": pagina}
        resp = requests.post(url, data=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        retorno = data.get("retorno", {})
        if retorno.get("status") != "OK":
            break
        registros = retorno.get("separacoes", [])
        if not registros:
            break
        for r in registros:
            itens.append(r.get("separacao", r))
        if len(registros) < 100:
            break
        pagina += 1
    return itens


def classificar_transportadora(nome):
    if not nome:
        return "outros"
    nome_lower = nome.lower()
    for chave, palavras in TRANSPORTADORAS.items():
        if any(p in nome_lower for p in palavras):
            return chave
    return "outros"


def buscar_conta(nome, token):
    resultado = {}
    for chave, situacao in SITUACOES.items():
        if chave == "embaladas":
            continue
        try:
            resultado[chave] = len(pesquisar_separacoes(token, situacao))
        except Exception as e:
            print(f"[ERRO] {nome}/{chave}: {e}")
            resultado[chave] = 0

    try:
        embalados = pesquisar_separacoes(token, SITUACOES["embaladas"])
        contagem  = {"mandae": 0, "correios": 0, "outros": 0}

        cache_formas = {}
        try:
            r = requests.post(f"{BASE_URL}/formas.envio.pesquisa.php", data={"token": token, "formato": "json"}, timeout=10)
            for f in r.json().get("retorno", {}).get("registros", []):
                cache_formas[str(f.get("id", ""))] = f.get("nome", "")
        except Exception:
            pass

        for item in embalados:
            id_forma   = str(item.get("idFormaEnvio", ""))
            nome_forma = cache_formas.get(id_forma, "")
            contagem[classificar_transportadora(nome_forma)] += 1

        resultado["embaladas"]               = len(embalados)
        resultado["embaladas_transportadora"] = contagem
    except Exception as e:
        print(f"[ERRO] {nome}/embaladas: {e}")
        resultado["embaladas"]               = 0
        resultado["embaladas_transportadora"] = {"mandae": 0, "correios": 0, "outros": 0}

    resultado["total"] = sum([resultado.get(k, 0) for k in SITUACOES])
    return resultado


def atualizar_dados():
    global dados_cache, ultima_atualizacao
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Atualizando dados...")
    output = {"updated_at": datetime.now(timezone.utc).isoformat()}
    for chave, config in CONTAS.items():
        output[chave] = buscar_conta(config["nome"], config["token"])
    dados_cache = output
    ultima_atualizacao = datetime.now()
    print(f"[OK] Dados atualizados")


def loop_atualizacao():
    while True:
        try:
            atualizar_dados()
        except Exception as e:
            print(f"[ERRO] Loop: {e}")
        time.sleep(120)  # atualiza a cada 2 minutos


# ─── ROTAS ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/data.json")
def data():
    return jsonify(dados_cache)


# ─── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Busca dados iniciais antes de subir
    atualizar_dados()
    # Inicia loop de atualização em background
    t = threading.Thread(target=loop_atualizacao, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=8080)
