"""API serverless do Monitor de Promoções para Vercel + PostgreSQL."""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import ipaddress
import json
import os
import re
import secrets
import smtplib
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Request as FastAPIRequest
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row

app = FastAPI(title="Monitor de Promoções API", version="3.0.0", docs_url=None, redoc_url=None, openapi_url=None)

VALID_FREQUENCIES = {"A cada 15 min", "A cada hora", "A cada 6 horas", "Uma vez por dia"}
VALID_SOURCES = {"Steam", "CheapShark", "RSS", "Epic Games", "GOG", "Nuuvem", "Amazon"}
VALID_CHANNELS = {"E-mail", "Telegram", "WhatsApp"}
TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def db():
    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn:
        raise HTTPException(503, "Banco não configurado. Defina DATABASE_URL na Vercel.")
    try:
        conn = psycopg.connect(dsn, connect_timeout=8, row_factory=dict_row)
        conn.execute("SET statement_timeout = '20s'")
        return conn
    except Exception as exc:
        print("DATABASE_CONNECT_ERROR", type(exc).__name__)
        raise HTTPException(503, "Não foi possível conectar ao banco de dados.")


def ensure_schema(conn):
    conn.execute("""
      CREATE TABLE IF NOT EXISTS items (
        id UUID PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'Outro',
        target_price NUMERIC(12,2), min_discount NUMERIC(5,2), sources JSONB NOT NULL,
        channels JSONB NOT NULL, destination JSONB NOT NULL DEFAULT '{}'::jsonb,
        frequency TEXT NOT NULL DEFAULT 'A cada hora', active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), next_check TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_checked TIMESTAMPTZ
      )
    """)
    conn.execute("""
      CREATE TABLE IF NOT EXISTS offers (
        id BIGSERIAL PRIMARY KEY, item_id UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,
        name TEXT NOT NULL, store TEXT NOT NULL, kind TEXT NOT NULL, currency TEXT NOT NULL,
        original_price NUMERIC(12,2), price NUMERIC(12,2) NOT NULL, discount NUMERIC(5,2) NOT NULL DEFAULT 0,
        url TEXT NOT NULL, checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(item_id, store, url, price)
      )
    """)
    conn.execute("""
      CREATE TABLE IF NOT EXISTS alerts (
        id BIGSERIAL PRIMARY KEY, item_id UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,
        name TEXT NOT NULL, store TEXT NOT NULL, kind TEXT NOT NULL, currency TEXT NOT NULL,
        original_price NUMERIC(12,2), price NUMERIC(12,2) NOT NULL, discount NUMERIC(5,2) NOT NULL DEFAULT 0,
        url TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), notified TEXT NOT NULL DEFAULT ''
      )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_items_due ON items(active, next_check)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_offers_item_checked ON offers(item_id, checked_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at DESC)")
    conn.commit()


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def issue_token() -> str:
    secret = os.getenv("JWT_SECRET", "")
    if len(secret) < 32:
        raise HTTPException(503, "JWT_SECRET precisa ter pelo menos 32 caracteres.")
    header = b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = {"sub": "owner", "iat": int(time.time()), "exp": int(time.time()) + TOKEN_TTL_SECONDS}
    body = b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = header + "." + body
    signature = b64url(hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest())
    return signing_input + "." + signature


def verify_token(token: str) -> bool:
    try:
        header, body, signature = token.split(".", 2)
        secret = os.getenv("JWT_SECRET", "")
        signing_input = header + "." + body
        expected = b64url(hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest())
        if not secret or not hmac.compare_digest(signature, expected):
            return False
        decoded_header = json.loads(base64.urlsafe_b64decode(header + "=" * (-len(header) % 4)))
        if decoded_header.get("alg") != "HS256":
            return False
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        return payload.get("sub") == "owner" and int(payload.get("exp", 0)) > int(time.time())
    except Exception:
        return False


async def require_auth(authorization: str | None = Header(default=None)):
    token = authorization[7:].strip() if authorization and authorization.startswith("Bearer ") else ""
    if not token or not verify_token(token):
        raise HTTPException(401, "Sessão inválida ou expirada. Entre novamente.")
    return True


def clean_url(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 2000:
        return ""
    try:
        p = urlparse(value.strip())
        if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password:
            return ""
        return value.strip()
    except ValueError:
        return ""


def http_bytes(url: str, headers: dict | None = None, timeout: int = 8, limit: int = 2_000_000) -> bytes:
    req = Request(url, headers={"User-Agent": "PromoMonitor/3.0", **(headers or {})})
    with urlopen(req, timeout=timeout) as response:
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError("Resposta da fonte excede o limite permitido")
        return data


def http_json(url: str) -> Any:
    return json.loads(http_bytes(url, {"Accept": "application/json"}).decode("utf-8", "replace"))


def steam_search(term: str) -> list[dict]:
    data = http_json("https://store.steampowered.com/api/storesearch/?term=" + quote(term) + "&cc=br&l=brazilian")
    out = []
    for item in data.get("items", [])[:6]:
        appid = item.get("id")
        if not appid:
            continue
        try:
            details = json.loads(http_bytes(f"https://store.steampowered.com/api/appdetails?appids={appid}&cc=br&l=brazilian", timeout=5).decode("utf-8", "replace"))
            entry = details.get(str(appid), {}).get("data", {})
            price = entry.get("price_overview")
            if not price:
                continue
            final, original = int(price.get("final", 0)), int(price.get("initial", price.get("final", 0)))
            out.append({"name": entry.get("name", item.get("name", term)), "store": "Steam", "kind": "Loja oficial", "currency": "BRL", "price": final / 100, "original_price": original / 100, "discount": float(price.get("discount_percent", 0)), "url": clean_url(entry.get("store_url") or f"https://store.steampowered.com/app/{appid}/")})
        except Exception as exc:
            print("STEAM_ITEM_ERROR", type(exc).__name__)
    return out


def cheapshark_search(term: str) -> list[dict]:
    data = http_json("https://www.cheapshark.com/api/1.0/deals?title=" + quote(term) + "&pageSize=10&sortBy=Price")
    out = []
    for deal in data if isinstance(data, list) else []:
        try:
            deal_id = str(deal.get("dealID", ""))
            out.append({"name": deal.get("title", term), "store": "CheapShark", "kind": "Revendedor", "currency": "USD", "price": float(deal.get("salePrice", 0)), "original_price": float(deal.get("normalPrice", 0)), "discount": float(deal.get("savings", 0)), "url": clean_url("https://www.cheapshark.com/redirect?dealID=" + quote(deal_id))})
        except (TypeError, ValueError):
            continue
    return out


def rss_search(term: str) -> list[dict]:
    try:
        feeds = json.loads(os.getenv("RSS_FEEDS", "[]"))
    except json.JSONDecodeError:
        print("RSS_FEEDS_INVALID_JSON")
        return []
    out = []
    for feed in feeds if isinstance(feeds, list) else []:
        if not isinstance(feed, dict):
            continue
        url = clean_url(feed.get("url"))
        if not url or urlparse(url).scheme != "https":
            continue
        try:
            root = ET.fromstring(http_bytes(url, {"Accept": "application/rss+xml, application/xml, text/xml"}, 8, 1_000_000))
            for node in root.findall(".//item"):
                title = node.findtext("title") or ""
                if term.casefold() not in title.casefold():
                    continue
                link = clean_url(node.findtext("link") or "")
                desc = html.unescape(re.sub(r"<[^>]+>", " ", node.findtext("description") or ""))
                match = re.search(r"(?:R\$|BRL)\s*([\d.,]+)", title + " " + desc, re.I)
                if not match or not link:
                    continue
                price = float(match.group(1).replace(".", "").replace(",", "."))
                out.append({"name": title[:180], "store": str(feed.get("name", "RSS"))[:100], "kind": "RSS", "currency": "BRL", "price": price, "original_price": price, "discount": 0, "url": link})
        except Exception as exc:
            print("RSS_SOURCE_ERROR", type(exc).__name__)
    return out


def search_sources(item: dict) -> tuple[list[dict], list[str]]:
    found, errors = [], []
    for source in item["sources"]:
        try:
            if source == "Steam": found.extend(steam_search(item["name"]))
            elif source == "CheapShark": found.extend(cheapshark_search(item["name"]))
            elif source == "RSS": found.extend(rss_search(item["name"]))
            else: errors.append(source + ": integração ainda não configurada; use uma API oficial ou RSS.")
        except Exception as exc:
            errors.append(source + ": " + type(exc).__name__)
    return found, errors


def qualifies(item: dict, offer: dict) -> bool:
    price_ok = item["target_price"] is not None and offer["currency"] == "BRL" and float(offer["price"]) <= float(item["target_price"])
    discount_ok = item["min_discount"] is not None and float(offer["discount"]) >= float(item["min_discount"])
    return bool(price_ok or discount_ok)


def send_notifications(item: dict, offer: dict) -> str:
    channels = item["channels"]
    destinations = item.get("destination") or {}
    message = f"Promoção encontrada: {offer['name']}\nLoja: {offer['store']}\nPreço: {offer['currency']} {float(offer['price']):.2f}\nDesconto: {float(offer['discount']):.0f}%\n{offer['url']}"
    sent = []
    if "Telegram" in channels:
        token, chat = os.getenv("TELEGRAM_BOT_TOKEN", ""), destinations.get("Telegram") or os.getenv("TELEGRAM_CHAT_ID", "")
        if token and chat:
            try:
                payload = json.dumps({"chat_id": chat, "text": message}).encode()
                req = Request(f"https://api.telegram.org/bot{token}/sendMessage", data=payload, headers={"Content-Type": "application/json"})
                with urlopen(req, timeout=15) as response: response.read(4096)
                sent.append("Telegram")
            except Exception as exc: print("TELEGRAM_SEND_ERROR", type(exc).__name__)
    if "E-mail" in channels:
        to = destinations.get("E-mail", "")
        host, user = os.getenv("SMTP_HOST", ""), os.getenv("SMTP_USER", "")
        if host and to and "@" in to:
            try:
                msg = EmailMessage(); msg["Subject"] = "Promoção encontrada: " + offer["name"]
                msg["From"] = os.getenv("SMTP_FROM", "") or user; msg["To"] = to; msg.set_content(message)
                with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=15) as smtp:
                    if os.getenv("SMTP_STARTTLS", "true").lower() == "true": smtp.starttls()
                    if user: smtp.login(user, os.getenv("SMTP_PASSWORD", ""))
                    smtp.send_message(msg)
                sent.append("E-mail")
            except Exception as exc: print("SMTP_SEND_ERROR", type(exc).__name__)
    if "WhatsApp" in channels:
        token, phone_id, to = os.getenv("WHATSAPP_TOKEN", ""), os.getenv("WHATSAPP_PHONE_NUMBER_ID", ""), destinations.get("WhatsApp", "")
        if token and phone_id and to:
            try:
                body = json.dumps({"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": message}}).encode()
                version = os.getenv("WHATSAPP_API_VERSION", "v23.0")
                req = Request(f"https://graph.facebook.com/{version}/{phone_id}/messages", data=body, headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
                with urlopen(req, timeout=15) as response: response.read(4096)
                sent.append("WhatsApp")
            except Exception as exc: print("WHATSAPP_SEND_ERROR", type(exc).__name__)
    return ",".join(sent)


def scan_one(conn, item: dict) -> dict:
    offers, errors = search_sources(item)
    added = triggered = 0
    for offer in offers:
        if not offer.get("url") or float(offer.get("price", -1)) < 0:
            continue
        row = conn.execute("""INSERT INTO offers(item_id,name,store,kind,currency,original_price,price,discount,url)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(item_id,store,url,price) DO NOTHING RETURNING id""",
          (item["id"], offer["name"], offer["store"], offer["kind"], offer["currency"], offer.get("original_price"), offer["price"], offer["discount"], offer["url"])).fetchone()
        if row: added += 1
        if qualifies(item, offer):
            exists = conn.execute("SELECT id FROM alerts WHERE item_id=%s AND url=%s AND price=%s AND created_at >= date_trunc('day', NOW()) LIMIT 1", (item["id"], offer["url"], offer["price"])).fetchone()
            if not exists:
                alert = conn.execute("""INSERT INTO alerts(item_id,name,store,kind,currency,original_price,price,discount,url)
                  VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                  (item["id"], offer["name"], offer["store"], offer["kind"], offer["currency"], offer.get("original_price"), offer["price"], offer["discount"], offer["url"])).fetchone()
                conn.commit()
                notified = send_notifications(item, offer)
                conn.execute("UPDATE alerts SET notified=%s WHERE id=%s", (notified, alert["id"]))
                triggered += 1
    conn.execute("UPDATE items SET last_checked=NOW(), next_check=NOW() + (%s::double precision * INTERVAL '1 second') WHERE id=%s", (frequency_seconds(item["frequency"]), item["id"]))
    conn.commit()
    return {"offers_found": len(offers), "offers_added": added, "alerts_created": triggered, "errors": errors}


def frequency_seconds(value: str) -> int:
    return {"A cada 15 min": 900, "A cada hora": 3600, "A cada 6 horas": 21600, "Uma vez por dia": 86400}.get(value, 3600)


def json_item(row: dict) -> dict:
    result = dict(row)
    result["target_price"] = float(result["target_price"]) if result.get("target_price") is not None else None
    result["min_discount"] = float(result["min_discount"]) if result.get("min_discount") is not None else None
    result["sources"] = result["sources"] if isinstance(result["sources"], list) else json.loads(result["sources"])
    result["channels"] = result["channels"] if isinstance(result["channels"], list) else json.loads(result["channels"])
    result["destination"] = result["destination"] if isinstance(result["destination"], dict) else json.loads(result["destination"])
    result["created_at"] = result["created_at"].isoformat() if result.get("created_at") else None
    result["last_checked"] = result["last_checked"].isoformat() if result.get("last_checked") else None
    return result


@app.get("/api/health")
def health():
    database_ok = False
    try:
        with db() as conn:
            ensure_schema(conn)
            conn.execute("SELECT 1")
            database_ok = True
    except HTTPException:
        raise
    except Exception as exc:
        print("HEALTH_DATABASE_ERROR", type(exc).__name__)
    return {"ok": True, "database": database_ok, "time": now(), "version": app.version}


@app.post("/api/auth/login")
def login(payload: dict, request: FastAPIRequest):
    expected = os.getenv("APP_PASSWORD", "")
    supplied = str(payload.get("password", ""))[:256]
    if len(expected) < 12:
        raise HTTPException(503, "APP_PASSWORD não foi configurada corretamente na Vercel.")
    if not secrets.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(401, "Senha incorreta.")
    return {"access_token": issue_token(), "token_type": "bearer", "expires_in": TOKEN_TTL_SECONDS}


@app.get("/api/auth/check")
def auth_check(_: bool = Depends(require_auth)):
    return {"authenticated": True}


@app.get("/api/items")
def list_items(_: bool = Depends(require_auth)):
    with db() as conn:
        ensure_schema(conn)
        rows = conn.execute("SELECT * FROM items ORDER BY created_at DESC").fetchall()
        return [json_item(row) for row in rows]


@app.get("/api/alerts")
def list_alerts(_: bool = Depends(require_auth)):
    with db() as conn:
        ensure_schema(conn)
        rows = conn.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT 300").fetchall()
        return [{**dict(r), "price": float(r["price"]), "original_price": float(r["original_price"]) if r["original_price"] is not None else None, "discount": float(r["discount"]), "created_at": r["created_at"].isoformat()} for r in rows]


@app.get("/api/offers/{item_id}")
def list_offers(item_id: str, _: bool = Depends(require_auth)):
    try: uuid.UUID(item_id)
    except ValueError: raise HTTPException(400, "Identificador inválido.")
    with db() as conn:
        ensure_schema(conn)
        rows = conn.execute("SELECT * FROM offers WHERE item_id=%s ORDER BY checked_at DESC LIMIT 300", (item_id,)).fetchall()
        return [{**dict(r), "price": float(r["price"]), "original_price": float(r["original_price"]) if r["original_price"] is not None else None, "discount": float(r["discount"]), "checked_at": r["checked_at"].isoformat()} for r in rows]


@app.post("/api/items", status_code=201)
def create_item(payload: dict, _: bool = Depends(require_auth)):
    name = str(payload.get("name", "")).strip()[:180]
    sources, channels = payload.get("sources", []), payload.get("channels", [])
    destinations = payload.get("destinations", {})
    frequency = str(payload.get("frequency", "A cada hora"))
    target, discount = payload.get("target_price"), payload.get("min_discount")
    if not name or not isinstance(sources, list) or not sources or any(not isinstance(source, str) or source not in VALID_SOURCES for source in sources):
        raise HTTPException(400, "Informe nome e fontes válidas.")
    if not isinstance(channels, list) or not channels or any(not isinstance(channel, str) or channel not in VALID_CHANNELS for channel in channels) or not isinstance(destinations, dict):
        raise HTTPException(400, "Informe canais e destinos válidos.")
    if target in (None, "") and discount in (None, ""):
        raise HTTPException(400, "Informe preço-alvo ou desconto mínimo.")
    try:
        target = float(target) if target not in (None, "") else None
        discount = float(discount) if discount not in (None, "") else None
        if (target is not None and (target <= 0 or target > 1_000_000)) or (discount is not None and not 0 <= discount <= 100): raise ValueError
    except (TypeError, ValueError):
        raise HTTPException(400, "Preço deve ser positivo e desconto entre 0 e 100.")
    if frequency not in VALID_FREQUENCIES: raise HTTPException(400, "Frequência inválida.")
    item_id = str(uuid.uuid4())
    with db() as conn:
        ensure_schema(conn)
        conn.execute("""INSERT INTO items(id,name,category,target_price,min_discount,sources,channels,destination,frequency)
          VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s)""",
          (item_id, name, str(payload.get("category", "Outro"))[:50], target, discount, json.dumps(list(dict.fromkeys(sources))), json.dumps(list(dict.fromkeys(channels))), json.dumps(destinations), frequency))
        conn.commit()
    return {"id": item_id, "saved": True}


@app.post("/api/scan")
def scan_now(_: bool = Depends(require_auth)):
    with db() as conn:
        ensure_schema(conn)
        rows = conn.execute("SELECT * FROM items WHERE active=TRUE ORDER BY created_at").fetchall()
        results = []
        for row in rows:
            item = json_item(row)
            results.append({"item": item["name"], **scan_one(conn, item)})
        return {"results": results}


@app.patch("/api/items/{item_id}")
def update_item(item_id: str, payload: dict, _: bool = Depends(require_auth)):
    try: uuid.UUID(item_id)
    except ValueError: raise HTTPException(400, "Identificador inválido.")
    fields, values = [], []
    if "active" in payload:
        fields.append("active=%s"); values.append(bool(payload["active"]))
    if "frequency" in payload:
        if payload["frequency"] not in VALID_FREQUENCIES: raise HTTPException(400, "Frequência inválida.")
        fields.append("frequency=%s"); values.append(payload["frequency"])
    if not fields: raise HTTPException(400, "Nenhuma alteração informada.")
    values.append(item_id)
    with db() as conn:
        ensure_schema(conn)
        cur = conn.execute("UPDATE items SET " + ",".join(fields) + " WHERE id=%s", values)
        conn.commit()
        if cur.rowcount == 0: raise HTTPException(404, "Monitoramento não encontrado.")
    return {"updated": True}


@app.delete("/api/items/{item_id}")
def delete_item(item_id: str, _: bool = Depends(require_auth)):
    try: uuid.UUID(item_id)
    except ValueError: raise HTTPException(400, "Identificador inválido.")
    with db() as conn:
        ensure_schema(conn)
        cur = conn.execute("DELETE FROM items WHERE id=%s", (item_id,))
        conn.commit()
        if cur.rowcount == 0: raise HTTPException(404, "Monitoramento não encontrado.")
    return {"deleted": True}


@app.get("/api/cron/scan")
def scheduled_scan(authorization: str | None = Header(default=None)):
    secret = os.getenv("CRON_SECRET", "")
    if len(secret) < 24 or not authorization or not secrets.compare_digest(authorization, "Bearer " + secret):
        raise HTTPException(401, "Não autorizado.")
    with db() as conn:
        ensure_schema(conn)
        due = conn.execute("SELECT * FROM items WHERE active=TRUE AND next_check<=NOW() ORDER BY next_check LIMIT 2").fetchall()
        results = []
        for row in due:
            item = json_item(row)
            try: results.append({"item": item["name"], **scan_one(conn, item)})
            except Exception as exc:
                conn.rollback(); print("CRON_SCAN_ERROR", type(exc).__name__)
                results.append({"item": item["name"], "error": "Falha ao consultar fonte."})
        return {"scanned": len(results), "results": results, "time": now()}


@app.exception_handler(Exception)
async def unhandled_error(_: FastAPIRequest, exc: Exception):
    print("UNHANDLED_API_ERROR", type(exc).__name__)
    return JSONResponse(status_code=500, content={"error": "Erro interno da API."})
