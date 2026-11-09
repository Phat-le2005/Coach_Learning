"""Explicit demo preflight. Offline unless --live; never invoked by app startup."""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
from pathlib import Path
import struct
import time
import zlib

import httpx

from app.ai.gemini_failover import (
    DEFAULT_MODELS,
    MODEL_ID,
    GeminiFailoverManager,
    PoolUnavailable,
    classify_failure,
)
from app.core.config import Settings

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"


def _red_png() -> str:
    def chunk(name, data):
        return (
            struct.pack(">I", len(data))
            + name
            + data
            + struct.pack(">I", zlib.crc32(name + data))
        )

    data = b"\x89PNG\r\n\x1a\n" + chunk(
        b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0)
    )
    data += chunk(b"IDAT", zlib.compress((b"\x00" + b"\xff\x00\x00" * 8) * 8)) + chunk(
        b"IEND", b""
    )
    return base64.b64encode(data).decode("ascii")


async def inspect_models(
    settings: Settings, *, live=False, probe=False, transport=None
) -> dict:
    """Metadata proves access; probes separately prove JSON, vision and PDF input."""
    manager = GeminiFailoverManager(settings)
    models = list(
        dict.fromkeys(
            (settings.gemini_model_priority or ",".join(DEFAULT_MODELS)).split(",")
        )
    )
    models = [m.strip() for m in models if MODEL_ID.fullmatch(m.strip())]
    report = {
        "mode": "live" if live else "offline",
        "verified": False,
        "expires_at": time.time() + 6 * 3600,
        "credentials": {},
    }
    if not live:
        report["credentials"] = {
            c.id: {"project": c.project, "status": "UNVERIFIED", "models": models}
            for c in manager.credentials
        }
        return report  # Do not even construct a network client offline.
    async with httpx.AsyncClient(timeout=8, transport=transport) as client:
        for credential in manager.credentials:
            entry = {
                "project": credential.project,
                "fingerprint": credential.fingerprint,
                "models": {},
            }
            report["credentials"][credential.id] = entry
            headers = {"x-goog-api-key": credential.secret.get_secret_value()}
            for model in models:
                flags = {"available": False, "capabilities": [], "status": "UNVERIFIED"}
                entry["models"][model] = flags
                try:
                    response = await client.get(f"{ENDPOINT}/{model}", headers=headers)
                    payload = response.json()
                    if response.status_code != 200:
                        flags["status"] = classify_failure(
                            response.status_code, payload
                        ).kind
                        continue
                    if "generateContent" not in payload.get(
                        "supportedGenerationMethods", []
                    ):
                        flags["status"] = "UNSUPPORTED_GENERATION"
                        continue
                    flags.update(
                        available=True,
                        capabilities=["generateContent"],
                        status="METADATA_ONLY",
                    )
                    if not probe:
                        continue
                    # A completed JSON probe is required, not inferred from a model name.
                    for capability in ("json", "vision", "pdf"):
                        prompt, expected = ("Return the sum 2+2 in field value.", 4)
                        parts = []
                        if capability == "vision":
                            prompt, expected = (
                                "What is the dominant color of the image? Return field value in lowercase English.",
                                "red",
                            )
                            parts.append(
                                {
                                    "inlineData": {
                                        "mimeType": "image/png",
                                        "data": _red_png(),
                                    }
                                }
                            )
                        if capability == "pdf":
                            from io import BytesIO
                            from pypdf import PdfWriter

                            writer, buffer = PdfWriter(), BytesIO()
                            writer.add_blank_page(width=100, height=100)
                            writer.write(buffer)
                            prompt, expected = (
                                "How many pages does this PDF have? Return field value.",
                                1,
                            )
                            parts.append(
                                {
                                    "inlineData": {
                                        "mimeType": "application/pdf",
                                        "data": base64.b64encode(
                                            buffer.getvalue()
                                        ).decode("ascii"),
                                    }
                                }
                            )
                        parts.append({"text": prompt})
                        body = {
                            "contents": [{"role": "user", "parts": parts}],
                            "generationConfig": {
                                "responseMimeType": "application/json",
                                "responseJsonSchema": {
                                    "type": "object",
                                    "properties": {
                                        "value": {
                                            "type": "integer"
                                            if isinstance(expected, int)
                                            else "string"
                                        }
                                    },
                                    "required": ["value"],
                                    "additionalProperties": False,
                                },
                            },
                        }
                        result = await client.post(
                            f"{ENDPOINT}/{model}:generateContent",
                            headers=headers,
                            json=body,
                        )
                        data = result.json()
                        if result.status_code != 200:
                            flags["status"] = classify_failure(
                                result.status_code, data
                            ).kind
                            break
                        candidate = data["candidates"][0]
                        if candidate.get("finishReason") != "STOP":
                            flags["status"] = "PROBE_FAILED"
                            break
                        raw = "".join(
                            p["text"]
                            for p in candidate["content"]["parts"]
                            if "text" in p and not p.get("thought")
                        )
                        if json.loads(raw).get("value") != expected:
                            flags["status"] = "PROBE_FAILED"
                            break
                        flags["capabilities"].append(capability)
                        flags["status"] = "PROBED"
                except (
                    httpx.RequestError,
                    ValueError,
                    KeyError,
                    IndexError,
                    TypeError,
                    AttributeError,
                ):
                    flags["status"] = "PROBE_FAILED"
    report["verified"] = probe and any(
        "json" in m["capabilities"]
        for e in report["credentials"].values()
        for m in e["models"].values()
    )
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Send real Gemini metadata requests. Requires user authorization.",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Also send billed JSON/image/PDF generations; requires --live.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write private capability manifest, preferably under ignored .tmp/.",
    )
    args = parser.parse_args(argv)
    if args.probe and not args.live:
        parser.error("--probe requires --live")
    try:
        result = asyncio.run(
            inspect_models(Settings(), live=args.live, probe=args.probe)
        )
    except PoolUnavailable:
        parser.exit(2, "Invalid Gemini pool configuration.\n")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(json.dumps(result, indent=2), encoding="utf-8")
        temporary.replace(args.output)
    # Deliberately omit key fingerprints and all provider payloads from terminal output.
    public = {
        **result,
        "credentials": {
            alias: {k: v for k, v in entry.items() if k != "fingerprint"}
            for alias, entry in result["credentials"].items()
        },
    }
    print(json.dumps(public, indent=2))


if __name__ == "__main__":
    main()
