from flask import Flask, request, jsonify
import requests
import json
import datetime

AUTH_URL = "http://127.0.0.1:1500"
CONSUMER_URL = "http://127.0.0.1:1100"
PROVIDER_URL = "http://127.0.0.1:1200"

def pretty(x):
    return json.dumps(x, indent=2)

def call(method, url, body=None):
    print(f"\n→ CALL {method} {url}")
    if body:
        print("BODY:", pretty(body))
    r = requests.request(method, url, json=body)
    try:
        print("RESPONSE:", pretty(r.json()))
        return r.json()
    except:
        print("RAW:", r.text)
        return {}

# -------------------------
# 1. ONBOARD WALLETS
# -------------------------
def auto_onboard():
    call("POST", f"{AUTH_URL}/v1/wallet")
    call("POST", f"{CONSUMER_URL}/v1/wallet")
    call("POST", f"{PROVIDER_URL}/v1/wallet")

    A = call("GET", f"{AUTH_URL}/v1/wallet")["did"]
    C = call("GET", f"{CONSUMER_URL}/v1/wallet")["did"]
    P = call("GET", f"{PROVIDER_URL}/v1/wallet")["did"]

    return A, C, P

# -------------------------
# 2. NEGOTIATION
# -------------------------
def negotiate_contract(provider_did):
    body = {
        "providerId": provider_did,
        "providerUrl": f"{PROVIDER_URL}/v3/ids",
        "offer": {
            "assetId": "iot-stream-001"
        }
    }

    resp = call("POST", f"{CONSUMER_URL}/v2/contractnegotiations", body)
    return resp.get("id")

# -------------------------
# 3. TRANSFER
# -------------------------
def create_transfer(contract_id):
    body = {
        "assetId": "iot-stream-001",
        "contractId": contract_id,
        "connectorAddress": f"{PROVIDER_URL}/v3/ids",
        "protocol": "dataspace-protocol-http"
    }

    resp = call("POST", f"{CONSUMER_URL}/v2/transferprocesses", body)
    return resp.get("id")

# -------------------------
# FLASK
# -------------------------
app = Flask(__name__)

@app.route("/init", methods=["POST"])
def init_all():
    A, C, P = auto_onboard()

    negotiation = negotiate_contract(P)
    transfer = create_transfer("contract-iot-001")

    return jsonify({
        "authority_did": A,
        "consumer_did": C,
        "provider_did": P,
        "contract_process": negotiation,
        "transfer_process": transfer
    })

@app.route("/telemetry", methods=["POST"])
def telemetry():
    data = request.json
    out = {
        "received_at": datetime.datetime.utcnow().isoformat(),
        "payload": data
    }
    print("\n=== TELEMETRY RECEIVED ===")
    print(pretty(out))
    return jsonify(out)

if __name__ == "__main__":
    app.run(port=9090, debug=True)
