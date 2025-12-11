"""Minimal Flask app that simulates an IoT device following the Rainbow specs.

The goal of this first iteration is to keep everything in a single file so we
have a clear place to extend the simulator. The simulator is aware of
``specs/openapi/*`` so it can expose the API surface defined for auth and
catalog, and it reuses the same dataspace defaults that appear in
``testing-env/pull_flow_rpc.ipynb``.
"""

from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from flask import Flask, jsonify, request

BASE_DIR = Path(__file__).resolve().parent
SPEC_FILES = {
    "auth": BASE_DIR / "specs" / "openapi" / "auth" / "auth_provider.json",
    "catalog": BASE_DIR / "specs" / "openapi" / "catalog" / "catalog_provider.json",
}

NOTEBOOK_DEFAULTS = {
    "provider_url": "http://127.0.0.1:1200",
    "consumer_url": "http://127.0.0.1:1100",
    "api_endpoint": "https://jsonplaceholder.typicode.com/todos",
}


def _load_spec(path: Path) -> Dict[str, Any]:
    """Load an OpenAPI spec file so the simulator can expose its metadata."""
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


class SpecCache:
    """Lazy loader for OpenAPI specs so we only parse them once."""

    def __init__(self) -> None:
        self._cache: Dict[str, Dict[str, Any]] = {}

    def get(self, name: str) -> Dict[str, Any]:
        if name not in SPEC_FILES:
            raise KeyError(f"Unknown spec {name}")
        if name not in self._cache:
            self._cache[name] = _load_spec(SPEC_FILES[name])
        return self._cache[name]

    def default_server(self, name: str) -> str:
        spec = self.get(name)
        servers = spec.get("servers", [])
        return servers[0]["url"] if servers else ""


spec_cache = SpecCache()


@dataclass
class CatalogDescriptor:
    catalog_id: str
    dataset_id: str
    distribution_id: str
    data_service_id: str


@dataclass
class IoTDeviceConfig:
    user_id: str
    user_token: str
    participant_type: str
    provider_url: str = NOTEBOOK_DEFAULTS["provider_url"]
    consumer_url: str = NOTEBOOK_DEFAULTS["consumer_url"]
    api_endpoint: str = NOTEBOOK_DEFAULTS["api_endpoint"]
    catalog: CatalogDescriptor = field(
        default_factory=lambda: CatalogDescriptor(
            catalog_id="rainbow-catalog",
            dataset_id="rainbow-dataset",
            distribution_id="rainbow-distribution",
            data_service_id="rainbow-data-service",
        )
    )


@dataclass
class DeviceState:
    token: Optional[str] = None
    last_payload: Optional[Dict[str, Any]] = None


class IoTDeviceSimulator:
    """Small orchestrator that mimics the device lifecycle."""

    def __init__(self, config: IoTDeviceConfig) -> None:
        self.config = config
        self.state = DeviceState()

    def authenticate(self) -> str:
        """Pseudo authentication that would map to the /token operation."""
        if self.state.token:
            return self.state.token

        token_seed = f"{self.config.user_id}:{self.config.user_token}"
        token = f"mock-token-{abs(hash(token_seed)) % 10_000}"
        self.state.token = token
        return token

    def ensure_catalog_entry(self) -> Dict[str, Any]:
        """Return the catalog entry that would exist on the provider."""
        catalog_spec = spec_cache.get("catalog")
        metadata = {
            "catalog": self.config.catalog.catalog_id,
            "dataset": self.config.catalog.dataset_id,
            "distribution": self.config.catalog.distribution_id,
            "data_service": self.config.catalog.data_service_id,
            "provider_url": self.config.provider_url,
            "spec_summary": catalog_spec["info"]["title"],
        }
        return metadata

    def build_payload(self, measurement: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare a telemetry payload the way the dataspace expects it."""
        now = datetime.now(timezone.utc).isoformat()
        sample_measurement = {
            "temperature": round(random.uniform(18.0, 25.0), 2),
            "humidity": round(random.uniform(40.0, 60.0), 2),
        }
        sample_measurement.update(measurement)
        payload = {
            "measured_at": now,
            "device_user": self.config.user_id,
            "participant_type": self.config.participant_type,
            "api_endpoint": self.config.api_endpoint,
            "data": sample_measurement,
        }
        return payload

    def transmit(self, measurement: Dict[str, Any]) -> Dict[str, Any]:
        token = self.authenticate()
        catalog_entry = self.ensure_catalog_entry()
        payload = self.build_payload(measurement)
        envelope = {
            "auth_token": token,
            "catalog_entry": catalog_entry,
            "payload": payload,
        }
        self.state.last_payload = envelope
        return envelope

    def describe(self) -> Dict[str, Any]:
        return {
            "config": asdict(self.config),
            "auth_server": spec_cache.default_server("auth"),
            "catalog_server": spec_cache.default_server("catalog"),
            "last_payload": self.state.last_payload,
        }


def build_device() -> IoTDeviceSimulator:
    """Factory that wires env vars with the defaults from the notebook."""
    config = IoTDeviceConfig(
        user_id=os.getenv("RAINBOW_USER_ID", "did:example:provider-user"),
        user_token=os.getenv("RAINBOW_USER_TOKEN", "provider-secret"),
        participant_type=os.getenv("RAINBOW_PARTICIPANT_TYPE", "Provider"),
    )
    return IoTDeviceSimulator(config)


app = Flask(__name__)
device = build_device()


@app.route("/health", methods=["GET"])
def health() -> Any:
    return jsonify({"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()})


@app.route("/device", methods=["GET"])
def describe_device() -> Any:
    return jsonify(device.describe())


@app.route("/telemetry", methods=["POST"])
def push_telemetry() -> Any:
    measurement = request.get_json(silent=True) or {}
    envelope = device.transmit(measurement)
    return jsonify(envelope)


if __name__ == "__main__":
    debug_flag = os.getenv("FLASK_DEBUG", "1") == "1"
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=debug_flag)
