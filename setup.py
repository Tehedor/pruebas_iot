#!/usr/bin/env python3
import requests
import json
import sys

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


# ----------------------------------------------------
# 1. Crear Asset
# ----------------------------------------------------
def create_asset():
    asset = {
        "asset": {
            "@type": "Asset",
            "properties": {
                "asset:prop:id": "iot-stream-001",
                "asset:prop:description": "IoT telemetry stream"
            }
        },
        "dataAddress": {
            "type": "HttpData",
            "endpoint": "http://localhost:9090/telemetry"
        }
    }

    post(f"{PROVIDER}/api/v1/assets", asset)


# ----------------------------------------------------
# 2. Crear Policy
# ----------------------------------------------------
def create_policy():
    policy = {
        "uid": "policy-iot",
        "permissions": [
            {
                "edctype": "dataspaceconnector:permission",
                "target": "iot-stream-001",
                "action": {"type": "use"}
            }
        ]
    }

    post(f"{PROVIDER}/api/v1/policydefinitions", policy)


# ----------------------------------------------------
# 3. Crear Contract Definition
# ----------------------------------------------------
def create_contract_definition():
    body = {
        "id": "contract-iot-001",
        "accessPolicyId": "policy-iot",
        "contractPolicyId": "policy-iot",
        "assetsSelector": [
            {
                "operandLeft": "asset:prop:id",
                "operator": "=",
                "operandRight": "iot-stream-001"
            }
        ]
    }

    post(f"{PROVIDER}/api/v1/contractdefinitions", body)


# ----------------------------------------------------
# MAIN
# ----------------------------------------------------
if __name__ == "__main__":
    print("=== SETTING UP PROVIDER (ASSET + POLICY + CONTRACT) ===")
    create_asset()
    create_policy()
    create_contract_definition()
    print("\n=== Provider setup complete ===")