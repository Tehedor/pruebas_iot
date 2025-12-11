from flask import Flask, request, jsonify
import requests
import json

# ============================================================
#  CONFIG
# ============================================================

AUTHORITY_URL = "http://127.0.0.1:1500"
CONSUMER_URL = "http://127.0.0.1:1100"
PROVIDER_URL = "http://127.0.0.1:1200"

AUTHORITY_DOCKER = "http://host.docker.internal:1500"
CONSUMER_DOCKER = "http://host.docker.internal:1100"
PROVIDER_DOCKER = "http://host.docker.internal:1200"

app = Flask(__name__)


# ============================================================
#  UTILITY REQUEST WRAPPER
# ============================================================

def call(method, url, body=None):
    headers = {"Content-Type": "application/json"}
    data = json.dumps(body) if body else None

    print(f"\n→ CALL {method} {url}")
    if body:
        print("  BODY:", json.dumps(body, indent=2))

    resp = requests.request(method, url, headers=headers, data=data)

    try:
        parsed = resp.json()
        print("  RESPONSE:", json.dumps(parsed, indent=2))
        return parsed
    except Exception:
        print("  RAW RESPONSE:", resp.text)
        return resp.text


# ============================================================
# 1. AUTO-ONBOARDING (Authority / Consumer / Provider)
# ============================================================

def auto_onboard():
    print("\n========== AUTO ONBOARD ==========")

    call("POST", f"{AUTHORITY_URL}/api/v1/wallet/onboard")
    call("POST", f"{CONSUMER_URL}/api/v1/wallet/onboard")
    call("POST", f"{PROVIDER_URL}/api/v1/wallet/onboard")

    authority_did = call("GET", f"{AUTHORITY_URL}/api/v1/wallet/did.json")["id"]
    consumer_did = call("GET", f"{CONSUMER_URL}/api/v1/wallet/did.json")["id"]
    provider_did = call("GET", f"{PROVIDER_URL}/api/v1/wallet/did.json")["id"]

    print("\nDIDs SUCCESS:")
    print("  Authority:", authority_did)
    print("  Consumer:", consumer_did)
    print("  Provider:", provider_did)

    return authority_did, consumer_did, provider_did


# ============================================================
# 2. CREDENTIAL (OIDC4VCI)
# ============================================================

def get_credential(authority_did):
    print("\n========== OIDC4VCI CREDENTIAL ==========")

    # Consumer → pide credencial
    beg_body = {
        "url": f"{AUTHORITY_DOCKER}/api/v1/gate/access",
        "id": authority_did,
        "slug": "rainbow_authority",
        "vc_type": "DataspaceParticipantCredential"
    }
    call("POST", f"{CONSUMER_URL}/api/v1/vc-request/beg/cross-user", beg_body)

    # Authority → lista peticiones
    all_requests = call("GET", f"{AUTHORITY_URL}/api/v1/vc-request/all")
    petition_id = all_requests[-1]["id"]

    # Authority → aprueba
    call("POST", f"{AUTHORITY_URL}/api/v1/vc-request/{petition_id}", {"approve": True})

    # Consumer → recoge el VC issuance URI
    arr = call("GET", f"{CONSUMER_URL}/api/v1/vc-request/all")
    vc_uri = arr[-1]["vc_uri"]

    # Consumer → procesa el VCI
    call("POST", f"{CONSUMER_URL}/api/v1/wallet/oidc4vci", {"uri": vc_uri})

    return True


# ============================================================
# 3. GRANT PROVIDER ACCESS (OIDC4VP)
# ============================================================

def grant_provider_access(provider_did):
    print("\n========== OIDC4VP PERMISSION ==========")

    body = {
        "url": f"{PROVIDER_DOCKER}/api/v1/gate/access",
        "id": provider_did,
        "slug": "rainbow_provider",
        "actions": "talk"
    }

    uri = call("POST", f"{CONSUMER_URL}/api/v1/onboard/provider", body)

    # La API a veces devuelve string, a veces JSON
    if isinstance(uri, dict):
        uri = uri.get("uri") or list(uri.values())[0]

    uri = str(uri).strip()

    # Consumer procesa el VP
    call("POST", f"{CONSUMER_URL}/api/v1/wallet/oidc4vp", {"uri": uri})

    return True


# ============================================================
# 4. CONTRACT NEGOTIATION  (ROBUST)
# ============================================================

def extract_id(resp):
    """Extrae un ID válido sin importar el formato real."""
    if not isinstance(resp, dict):
        raise Exception(f"Response is not JSON: {resp}")

    candidates = ["id", "@id", "processId", "contractId"]
    for key in candidates:
        if key in resp:
            return resp[key]

    raise Exception(f"No ID field found in response: {resp}")


def negotiate_contract(provider_did):
    print("\n========== NEGOTIATE CONTRACT ==========")

    body = {
        "providerId": provider_did,
        "offer": {
            "id": "offer-001",
            "permissions": ["SEND_DATA"]
        }
    }

    resp = call("POST", f"{CONSUMER_URL}/api/v1/contract-negotiation/processes", body)

    process_id = extract_id(resp)
    print("Negotiation ID:", process_id)

    return process_id


# ============================================================
# 5. TRANSFER PROCESS (ROBUST)
# ============================================================

def create_transfer(provider_did):
    print("\n========== CREATE TRANSFER ==========")

    body = {
        "providerId": provider_did,
        "assetId": "iot-stream-001",
        "protocol": "dataspace-protocol"
    }

    resp = call("POST", f"{CONSUMER_URL}/api/v1/transfers/rpc/setup-request", body)

    transfer_id = extract_id(resp)
    print("Transfer ID =", transfer_id)

    return transfer_id


# ============================================================
# 6. SEND TELEMETRY
# ============================================================

def send_telemetry(transfer_id, data):
    print("\n========== SEND TELEMETRY ==========")

    body = {
        "measurement": data
    }

    return call("POST", f"{PROVIDER_URL}/api/v1/transfers/{transfer_id}/messages", body)


# ============================================================
#  FLASK ENDPOINTS
# ============================================================

@app.route("/init", methods=["POST"])
def init_all():
    try:
        authority_did, consumer_did, provider_did = auto_onboard()

        get_credential(authority_did)
        grant_provider_access(provider_did)

        contract_id = negotiate_contract(provider_did)
        transfer_id = create_transfer(provider_did)

        return jsonify({
            "authority_did": authority_did,
            "consumer_did": consumer_did,
            "provider_did": provider_did,
            "contract_id": contract_id,
            "transfer_id": transfer_id
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/telemetry", methods=["POST"])
def telemetry():
    req = request.get_json()
    transfer_id = req["transfer_id"]
    measurement = req["data"]

    resp = send_telemetry(transfer_id, measurement)
    return jsonify(resp)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


# ============================================================
#  MAIN
# ============================================================

if __name__ == "__main__":
    app.run(port=9090, debug=True)