"""API local Minha Frota, sem dependencias externas.

Execute: python app.py
API: http://127.0.0.1:3001/api/health
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import threading
import webbrowser
import mimetypes
from contextlib import closing
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

APP_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "MinhaFrota"
DB_PATH = APP_DIR / "minha_frota.sqlite3"
HOST, PORT = "127.0.0.1", int(os.environ.get("MINHA_FROTA_PORT", "3001"))
PLATE_RE = re.compile(r"^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$")
PROJECT_DIR = Path(__file__).resolve().parent
ASSETS_DIR = PROJECT_DIR / "assets"

HOME_PAGE = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Minha Frota — API local</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f7fb;color:#14213d;font:16px Segoe UI,Arial,sans-serif}.top{background:#102a4c;color:white;padding:26px max(6vw,24px)}h1{margin:0;font-size:30px}.top p{opacity:.8;margin:7px 0 0}.main{max-width:1100px;margin:26px auto;padding:0 24px}.summary,.vehicles{display:grid;gap:16px}.summary{grid-template-columns:repeat(3,1fr);margin-bottom:24px}.card{background:white;border-radius:14px;padding:20px;box-shadow:0 4px 18px #16325c14}.label{color:#637490;font-size:13px}.number{font-size:25px;font-weight:700;margin-top:7px}.vehicle{border-left:5px solid #1683ff}.vehicle h3{margin:0 0 10px}.meta{color:#526680;font-size:14px;margin:5px 0}button{border:0;border-radius:8px;background:#087cff;color:#fff;font-weight:600;padding:11px 15px;cursor:pointer}button:hover{background:#0066d7}form{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin:20px 0}input,select{border:1px solid #cbd7e7;border-radius:8px;padding:10px;font:inherit}.notice{min-height:24px;color:#16733a;font-weight:600}@media(max-width:720px){.summary,form{grid-template-columns:1fr}.main{padding:0 15px}}
</style></head><body><header class="top"><h1>🚙 Minha Frota</h1><p>API local em execução — dados armazenados somente neste computador.</p></header><main class="main"><section class="summary"><article class="card"><div class="label">Veículos ativos</div><div class="number" id="total">—</div></article><article class="card"><div class="label">Custo do mês</div><div class="number" id="cost">—</div></article><article class="card"><div class="label">Próximo vencimento</div><div class="number" id="next">—</div></article></section><button id="refresh" type="button">Atualizar dados</button><p class="notice" id="notice" role="status"></p><h2>Veículos</h2><section class="vehicles" id="vehicles" aria-live="polite"></section><h2>Adicionar veículo de teste</h2><form id="vehicle-form"><select id="type" aria-label="Tipo"><option value="carro">Carro</option><option value="moto">Moto</option></select><input id="brand" required placeholder="Marca" value="Teste"><input id="model" required placeholder="Modelo" value="Local"><input id="year" required type="number" min="1886" value="2025"><input id="plate" required placeholder="Placa ABC1D23"><button type="submit">Cadastrar</button></form></main><script>
const money=new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'});const el=id=>document.getElementById(id);async function load(){try{const[d,v]=await Promise.all([fetch('/api/dashboard').then(r=>r.json()),fetch('/api/vehicles').then(r=>r.json())]);el('total').textContent=d.data.active_vehicles;el('cost').textContent=money.format(d.data.monthly_cost);el('next').textContent=d.data.upcoming[0]?.due_date?.split('-').reverse().join('/')||'Nenhum';el('vehicles').innerHTML=v.data.map(x=>`<article class="card vehicle"><h3>${x.brand} ${x.model} ${x.year}</h3><div class="meta">${x.type==='moto'?'Moto':'Carro'} · ${x.plate} · ${Number(x.odometer_km).toLocaleString('pt-BR')} km</div><div class="meta">Situação: ${x.status}</div></article>`).join('');el('notice').textContent='Dados atualizados.'}catch(e){el('notice').textContent='Não foi possível consultar a API local.';el('notice').style.color='#b42318'}}el('refresh').onclick=load;el('vehicle-form').onsubmit=async e=>{e.preventDefault();const p={type:el('type').value,brand:el('brand').value,model:el('model').value,year:+el('year').value,plate:el('plate').value};const r=await fetch('/api/vehicles',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)});const j=await r.json();if(!r.ok){el('notice').textContent=j.error.message;el('notice').style.color='#b42318';return}el('notice').style.color='#16733a';el('notice').textContent='Veículo cadastrado com sucesso.';e.target.reset();load()};load();</script></body></html>"""

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS vehicles (
 id INTEGER PRIMARY KEY, type TEXT NOT NULL CHECK(type IN ('carro','moto')),
 brand TEXT NOT NULL, model TEXT NOT NULL, version TEXT, year INTEGER NOT NULL,
 plate TEXT NOT NULL UNIQUE, renavam TEXT, chassis TEXT, color TEXT, fuel TEXT,
 odometer_km REAL NOT NULL DEFAULT 0 CHECK(odometer_km >= 0), acquired_on TEXT,
 acquisition_value REAL CHECK(acquisition_value >= 0), photo_path TEXT, notes TEXT,
 status TEXT NOT NULL DEFAULT 'ativo' CHECK(status IN ('ativo','vendido','inativo')),
 is_demo INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS records (
 id INTEGER PRIMARY KEY, vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
 kind TEXT NOT NULL CHECK(kind IN ('manutencao','pagamento','seguro','documento','abastecimento','despesa')),
 category TEXT NOT NULL, description TEXT NOT NULL, due_date TEXT, performed_on TEXT,
 amount REAL NOT NULL DEFAULT 0 CHECK(amount >= 0), status TEXT NOT NULL DEFAULT 'pendente'
   CHECK(status IN ('pendente','pago','atrasado','concluido','ativo')),
 odometer_km REAL, details TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_records_vehicle ON records(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_records_due ON records(due_date);
"""

def connect() -> sqlite3.Connection:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def rows(conn, sql, params=()):
    return [dict(row) for row in conn.execute(sql, params).fetchall()]

def load_home_page() -> str:
    return (PROJECT_DIR / "dashboard.html").read_text(encoding="utf-8")

def init_database() -> None:
    with closing(connect()) as conn:
        conn.executescript(SCHEMA)
        if conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0] == 0:
            demo = [
                ("carro", "Toyota", "Corolla", "XEi", 2022, "ABC1D23", "Flex", 32450, "branco"),
                ("carro", "Honda", "Civic", "EXL", 2020, "DEF4G56", "Flex", 56230, "preto"),
                ("moto", "Honda", "CG 160", "Titan", 2023, "HIJ7K89", "Gasolina", 18920, "preto"),
            ]
            conn.executemany("""INSERT INTO vehicles
              (type,brand,model,version,year,plate,fuel,odometer_km,color,is_demo)
              VALUES (?,?,?,?,?,?,?,?,?,1)""", demo)
            conn.execute("""INSERT INTO records(vehicle_id,kind,category,description,due_date,amount,status)
              VALUES (1,'manutencao','Revisao','Revisao de 40.000 km','2026-11-10',480,'pendente')""")
        conn.commit()

def vehicle_payload(data: dict, creating: bool = True) -> tuple | None:
    required = ("type", "brand", "model", "year", "plate")
    if creating and any(not str(data.get(key, "")).strip() for key in required):
        raise ValueError("Campos obrigatorios: type, brand, model, year e plate.")
    if "type" in data and data["type"] not in ("carro", "moto"):
        raise ValueError("type deve ser carro ou moto.")
    if "plate" in data:
        data["plate"] = str(data["plate"]).upper().replace("-", "")
        if not PLATE_RE.fullmatch(data["plate"]):
            raise ValueError("Placa invalida. Use o formato ABC1D23.")
    if "year" in data and (not isinstance(data["year"], int) or not 1886 <= data["year"] <= date.today().year + 2):
        raise ValueError("Ano invalido.")
    if "odometer_km" in data and (not isinstance(data["odometer_km"], (int, float)) or data["odometer_km"] < 0):
        raise ValueError("Quilometragem invalida.")
    allowed = ("type","brand","model","version","year","plate","renavam","chassis","color","fuel","odometer_km","acquired_on","acquisition_value","photo_path","notes","status")
    return {key: data[key] for key in allowed if key in data}

class ApiHandler(BaseHTTPRequestHandler):
    server_version = "MinhaFrota/1.0"

    def log_message(self, fmt, *args):
        # URLs can contain sensitive identifiers; no request logging by default.
        return

    def send_json(self, status, payload):
        encoded = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:3001")
        self.end_headers(); self.wfile.write(encoded)

    def send_html(self, status, content):
        encoded = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers(); self.wfile.write(encoded)

    def send_asset(self, asset_name):
        if asset_name not in {"sedan.png", "motorcycle.png"}:
            return self.send_json(404, {"error": {"code":"not_found", "message":"Arquivo não encontrado."}})
        content = (ASSETS_DIR / asset_name).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(asset_name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers(); self.wfile.write(content)

    def body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000: raise ValueError("Corpo da requisicao excede 1 MB.")
        try: return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError: raise ValueError("JSON invalido.")

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:3001")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self): self.dispatch("GET")
    def do_POST(self): self.dispatch("POST")
    def do_PUT(self): self.dispatch("PUT")
    def do_DELETE(self): self.dispatch("DELETE")

    def dispatch(self, method):
        try:
            parsed = urlparse(self.path); path = parsed.path.rstrip("/") or "/"; query = parse_qs(parsed.query)
            if method == "GET" and path == "/":
                return self.send_html(200, load_home_page())
            if method == "GET" and path.startswith("/assets/"):
                return self.send_asset(path.removeprefix("/assets/"))
            if not path.startswith("/api/"):
                return self.send_json(404, {"error": {"code":"not_found", "message":"Rota nao encontrada."}})
            with closing(connect()) as conn:
                if method == "GET" and path == "/api/health":
                    return self.send_json(200, {"status":"ok", "database":str(DB_PATH), "host":HOST})
                if method == "GET" and path == "/api/vehicles":
                    sql, args = "SELECT * FROM vehicles", []
                    if query.get("type"):
                        sql += " WHERE type=?"; args.append(query["type"][0])
                    sql += " ORDER BY status='ativo' DESC, id"
                    return self.send_json(200, {"data":rows(conn, sql, args)})
                if method == "POST" and path == "/api/vehicles":
                    fields = vehicle_payload(self.body())
                    keys, vals = list(fields), list(fields.values())
                    cur = conn.execute(f"INSERT INTO vehicles ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})", vals); conn.commit()
                    return self.send_json(201, {"data":dict(conn.execute("SELECT * FROM vehicles WHERE id=?", (cur.lastrowid,)).fetchone())})
                match = re.fullmatch(r"/api/vehicles/(\d+)", path)
                if match:
                    ident = int(match.group(1))
                    if method == "GET":
                        row = conn.execute("SELECT * FROM vehicles WHERE id=?", (ident,)).fetchone()
                        return self.send_json(200, {"data":dict(row)}) if row else self.send_json(404, {"error":{"code":"not_found","message":"Veiculo nao encontrado."}})
                    if method == "PUT":
                        fields = vehicle_payload(self.body(), False)
                        if not fields: raise ValueError("Informe ao menos um campo para atualizar.")
                        cur = conn.execute(f"UPDATE vehicles SET {','.join(f'{k}=?' for k in fields)}, updated_at=CURRENT_TIMESTAMP WHERE id=?", [*fields.values(), ident]); conn.commit()
                        return self.send_json(200, {"data":dict(conn.execute("SELECT * FROM vehicles WHERE id=?", (ident,)).fetchone())}) if cur.rowcount else self.send_json(404, {"error":{"code":"not_found","message":"Veiculo nao encontrado."}})
                    if method == "DELETE":
                        dependent = conn.execute("SELECT COUNT(*) FROM records WHERE vehicle_id=?", (ident,)).fetchone()[0]
                        if query.get("confirm") != ["true"]:
                            return self.send_json(409, {"error":{"code":"confirmation_required","message":"Confirme a exclusao com ?confirm=true.","related_records":dependent}})
                        cur = conn.execute("DELETE FROM vehicles WHERE id=?", (ident,)); conn.commit()
                        return self.send_json(204, {}) if cur.rowcount else self.send_json(404, {"error":{"code":"not_found","message":"Veiculo nao encontrado."}})
                if method == "GET" and path == "/api/dashboard":
                    total = conn.execute("SELECT COUNT(*) FROM vehicles WHERE status='ativo'").fetchone()[0]
                    costs = conn.execute("SELECT COALESCE(SUM(amount),0) FROM records WHERE substr(COALESCE(performed_on,due_date),1,7)=?", (date.today().strftime("%Y-%m"),)).fetchone()[0]
                    due = rows(conn, """SELECT r.*, v.brand || ' ' || v.model AS vehicle_name, v.plate
                      FROM records r JOIN vehicles v ON v.id=r.vehicle_id WHERE r.status='pendente'
                      ORDER BY r.due_date LIMIT 10""")
                    return self.send_json(200, {"data":{"active_vehicles":total,"monthly_cost":costs,"upcoming":due}})
                if path == "/api/records" and method == "GET":
                    sql, args = "SELECT r.*, v.brand || ' ' || v.model AS vehicle_name FROM records r JOIN vehicles v ON v.id=r.vehicle_id", []
                    if query.get("vehicle_id"): sql += " WHERE r.vehicle_id=?"; args.append(query["vehicle_id"][0])
                    return self.send_json(200, {"data":rows(conn, sql + " ORDER BY r.due_date DESC, r.id DESC", args)})
                if path == "/api/records" and method == "POST":
                    data = self.body(); required = ("vehicle_id","kind","category","description")
                    if any(key not in data for key in required): raise ValueError("Campos obrigatorios: vehicle_id, kind, category, description.")
                    if data["kind"] not in ("manutencao","pagamento","seguro","documento","abastecimento","despesa"): raise ValueError("Tipo de registro invalido.")
                    cur = conn.execute("""INSERT INTO records(vehicle_id,kind,category,description,due_date,performed_on,amount,status,odometer_km,details)
                      VALUES (?,?,?,?,?,?,?,?,?,?)""", (data["vehicle_id"],data["kind"],data["category"],data["description"],data.get("due_date"),data.get("performed_on"),data.get("amount",0),data.get("status","pendente"),data.get("odometer_km"),data.get("details"))); conn.commit()
                    return self.send_json(201, {"data":dict(conn.execute("SELECT * FROM records WHERE id=?", (cur.lastrowid,)).fetchone())})
                record_match = re.fullmatch(r"/api/records/(\d+)", path)
                if record_match and method == "PUT":
                    data = self.body(); allowed = {"category", "description", "due_date", "performed_on", "amount", "status", "odometer_km", "details"}
                    fields = {key: value for key, value in data.items() if key in allowed}
                    if not fields: raise ValueError("Informe ao menos um campo válido para atualizar.")
                    if "status" in fields and fields["status"] not in ("pendente", "pago", "atrasado", "concluido", "ativo"):
                        raise ValueError("Situação do registro inválida.")
                    ident = int(record_match.group(1))
                    cur = conn.execute(f"UPDATE records SET {','.join(f'{key}=?' for key in fields)} WHERE id=?", [*fields.values(), ident]); conn.commit()
                    if not cur.rowcount: return self.send_json(404, {"error":{"code":"not_found","message":"Registro não encontrado."}})
                    return self.send_json(200, {"data":dict(conn.execute("SELECT * FROM records WHERE id=?", (ident,)).fetchone())})
                if method == "GET" and path == "/api/reports/costs":
                    return self.send_json(200, {"data":rows(conn, "SELECT kind, category, ROUND(SUM(amount),2) AS total FROM records GROUP BY kind,category ORDER BY total DESC")})
                return self.send_json(404, {"error":{"code":"not_found","message":"Rota nao encontrada."}})
        except sqlite3.IntegrityError as exc:
            self.send_json(409, {"error":{"code":"conflict","message":"Registro duplicado ou relacionamento invalido."}})
        except ValueError as exc:
            self.send_json(400, {"error":{"code":"validation_error","message":str(exc)}})
        except Exception:
            self.send_json(500, {"error":{"code":"internal_error","message":"Erro interno. Verifique os dados informados."}})

def main():
    init_database()
    httpd = ThreadingHTTPServer((HOST, PORT), ApiHandler)
    print(f"Minha Frota API em http://{HOST}:{PORT} (dados: {DB_PATH})")
    threading.Timer(0.4, lambda: webbrowser.open(f"http://{HOST}:{PORT}/")).start()
    try: httpd.serve_forever()
    except KeyboardInterrupt: pass
    finally: httpd.server_close()

if __name__ == "__main__": main()
