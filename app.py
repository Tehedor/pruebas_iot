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


# ------------------------------------------------------------------
# 1. ONBOARDING AUTHORITY / CONSUMER / PROVIDER
# ------------------------------------------------------------------
def auto_onboard():
    call("POST", f"{AUTH_URL}/api/v1/wallet/onboard")
    call("POST", f"{CONSUMER_URL}/api/v1/wallet/onboard")
    call("POST", f"{PROVIDER_URL}/api/v1/wallet/onboard")

    A = call("GET", f"{AUTH_URL}/api/v1/wallet/did.json")["id"]
    C = call("GET", f"{CONSUMER_URL}/api/v1/wallet/did.json")["id"]
    P = call("GET", f"{PROVIDER_URL}/api/v1/wallet/did.json")["id"]

    print("DIDs SUCCESS:", A, C, P)
    return A, C, P


# ------------------------------------------------------------------
# 2. CREDENTIAL ISSUING (OIDC4VCI)
# ------------------------------------------------------------------
def get_credential(authority_did):
    body = {
        "url": "http://host.docker.internal:1500/api/v1/gate/access",
        "id": authority_did,
        "slug": "rainbow_authority",
        "vc_type": "DataspaceParticipantCredential"
    }

    call("POST", f"{CONSUMER_URL}/api/v1/vc-request/beg/cross-user", body)

    all_req = call("GET", f"{AUTH_URL}/api/v1/vc-request/all")
    req_id = all_req[-1]["id"]

    call("POST", f"{AUTH_URL}/api/v1/vc-request/{req_id}", {"approve": True})

    all_consumer = call("GET", f"{CONSUMER_URL}/api/v1/vc-request/all")
    valid = [x for x in all_consumer if x.get("vc_uri")]
    vc_uri = valid[-1]["vc_uri"]

    call("POST", f"{CONSUMER_URL}/api/v1/wallet/oidc4vci", {"uri": vc_uri})

    return vc_uri


# ------------------------------------------------------------------
# 3. OIDC4VP GRANT FROM PROVIDER
# ------------------------------------------------------------------
def grant_provider_access(provider_did):
    body = {
        "url": "http://host.docker.internal:1200/api/v1/gate/access",
        "id": provider_did,
        "slug": "rainbow_provider",
        "actions": "talk"
    }

    uri = call("POST", f"{CONSUMER_URL}/api/v1/onboard/provider", body)
    if isinstance(uri, dict):
        uri = ""
    uri = str(uri).strip()

    call("POST", f"{CONSUMER_URL}/api/v1/wallet/oidc4vp", {"uri": uri})

    return uri


# ------------------------------------------------------------------
# 4. CONTRACT NEGOTIATION  (CORREGIDO: providerPid)
# ------------------------------------------------------------------
def negotiate_contract(provider_did):
    body = {
        "providerPid": provider_did,
        "offer": {
            "id": "offer-001",
            "permissions": ["SEND_DATA"]
        }
    }

    resp = call("POST", f"{CONSUMER_URL}/api/v1/contract-negotiation/processes", body)
    if "id" not in resp:
        raise Exception("Negotiation failed, no 'id' in response")

    return resp["id"]


# ------------------------------------------------------------------
# 5. TRANSFER PROCESS CREATION
# ------------------------------------------------------------------
def create_transfer(provider_did):
    body = {
        "providerPid": provider_did,
        "assetId": "iot-stream-001",
        "contractId": "contract-iot-001"
    }

    resp = call("POST", f"{CONSUMER_URL}/api/v1/transfer/process", body)
    return resp.get("id", None)


# ------------------------------------------------------------------
# FLASK APP
# ------------------------------------------------------------------
app = Flask(__name__)

@app.route("/init", methods=["POST"])
def init_all():
    A, C, P = auto_onboard()
    get_credential(A)
    grant_provider_access(P)

    contract_process = negotiate_contract(P)
    transfer_process = create_transfer(P)

    return jsonify({
        "authority_did": A,
        "consumer_did": C,
        "provider_did": P,
        "contract_process": contract_process,
        "transfer_process": transfer_process
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