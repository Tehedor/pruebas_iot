#!/usr/bin/env python3
import requests
import json

PROVIDER = "http://127.0.0.1:1200"

def pretty(x):
    return json.dumps(x, indent=2)

def post(url, body):
    print(f"\n→ POST {url}")
    print(pretty(body))
    r = requests.post(url, json=body)
    try:
        print("RESPONSE:", pretty(r.json()))
    except:
        print("RAW:", r.text)
    return r

# -------------------------
# ASSET
# -------------------------
def create_asset():
    body = {
        "assetId": "iot-stream-001",
        "properties": {
            "description": "IoT telemetry stream"
        },
        "dataAddress": {
            "type": "HttpData",
            "endpoint": "http://localhost:9090/telemetry"
        }
    }

    post(f"{PROVIDER}/v3/assets", body)

# -------------------------
# POLICY
# -------------------------
def create_policy():
    policy = {
        "id": "policy-iot",
        "permissions": [
            {
                "edctype": "dataspaceconnector:permission",
                "target": "iot-stream-001",
                "action": { "type": "USE" }
            }
        ]
    }

    post(f"{PROVIDER}/v2/policydefinitions", policy)

# -------------------------
# CONTRACT DEFINITION
# -------------------------
def create_contract_definition():
    body = {
        "id": "contract-iot-001",
        "accessPolicyId": "policy-iot",
        "contractPolicyId": "policy-iot",
        "criteria": [
            {
                "operandLeft": "assetId",
                "operator": "=",
                "operandRight": "iot-stream-001"
            }
        ]
    }

    post(f"{PROVIDER}/v2/contractdefinitions", body)

# -------------------------
# MAIN
# -------------------------
if __name__ == "__main__":
    print("=== SETTING UP PROVIDER ===")
    create_asset()
    create_policy()
    create_contract_definition()
    print("=== PROVIDER READY ===")
