#!/usr/bin/env python3
"""Translate text via DeepL or Google Cloud Translation API.

Usage:
    translate_text.py --provider deepl --target LANG --api-key KEY --text "Hello"
    echo "Hello" | translate_text.py --provider google --target ar --api-key KEY

Outputs translated text on stdout; errors to stderr with non-zero exit.
"""
import argparse
import json
import sys
import urllib.request
import urllib.error
import urllib.parse


def translate_deepl(text: str, target_lang: str, api_key: str, pro: bool = False) -> str:
    """Translate text using DeepL API."""
    host = "api.deepl.com" if pro else "api-free.deepl.com"
    url = f"https://{host}/v2/translate"
    data = urllib.parse.urlencode({
        "auth_key": api_key,
        "text": text,
        "target_lang": target_lang.upper(),
    }).encode("utf-8")

    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        try:
            err_json = json.loads(err_body)
            msg = err_json.get("message", err_body)
        except json.JSONDecodeError:
            msg = err_body or str(e)
        raise RuntimeError(f"DeepL API error: {msg}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"DeepL connection error: {e.reason}")

    translations = body.get("translations", [])
    if not translations:
        raise RuntimeError("DeepL returned empty translations.")
    return translations[0]["text"]


def translate_google(text: str, target_lang: str, api_key: str) -> str:
    """Translate text using Google Cloud Translation API v2."""
    url = (
        "https://translation.googleapis.com/language/translate/v2"
        f"?key={urllib.parse.quote(api_key)}"
    )
    payload = json.dumps({
        "q": text,
        "target": target_lang,
        "format": "text",
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        try:
            err_json = json.loads(err_body)
            msg = err_json.get("error", {}).get("message", err_body)
        except json.JSONDecodeError:
            msg = err_body or str(e)
        raise RuntimeError(f"Google Translate API error: {msg}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Google connection error: {e.reason}")

    translations = body.get("data", {}).get("translations", [])
    if not translations:
        raise RuntimeError("Google returned empty translations.")
    return translations[0]["translatedText"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Translate text via API.")
    parser.add_argument("--provider", required=True, choices=["deepl", "google"])
    parser.add_argument("--target", required=True, help="Target language code (e.g. ar, en, de)")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--pro", action="store_true", help="Use DeepL Pro endpoint (paid key)")
    parser.add_argument("--text", default="", help="Text to translate. If omitted, reads from stdin.")
    args = parser.parse_args()

    text = args.text
    if not text:
        text = sys.stdin.read()

    if not text.strip():
        print("", end="")
        return 0

    try:
        if args.provider == "deepl":
            result = translate_deepl(text, args.target, args.api_key, pro=args.pro)
        else:
            result = translate_google(text, args.target, args.api_key)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1

    print(result, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
