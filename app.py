import json
import mimetypes
import os
import shutil
import socket
import sqlite3
from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "public"
DATA_DIR = BASE_DIR / "data"
JSON_DATA_FILE = DATA_DIR / "tracker.json"
DB_FILE = DATA_DIR / "tracker.db"
MAX_BODY_BYTES = 2 * 1024 * 1024


def pad2(value: int) -> str:
    return str(value).zfill(2)


def format_local_date_iso(value: date) -> str:
    return f"{value.year}-{pad2(value.month)}-{pad2(value.day)}"


def parse_iso_date(value: str) -> date:
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def get_week_start_iso(date_str: str) -> str:
    current = parse_iso_date(date_str)
    diff = -6 if current.weekday() == 6 else -current.weekday()
    return format_local_date_iso(current + timedelta(days=diff))


def create_default_state() -> dict:
    today = format_local_date_iso(date.today())
    week_start = get_week_start_iso(today)
    return {
        "contract": {
            "owner": "Yara",
            "createdAt": today,
            "schoolChoice": "Escola tradicional no Brasil (Único)",
            "socialLimitMinutes": 55,
        },
        "activities": [
            {"id": "programacao", "nome": "Programação", "tipo": "min_weekly", "unidade": "h", "meta": 5, "ordem": 1},
            {"id": "ingles", "nome": "Inglês", "tipo": "min_weekly", "unidade": "h", "meta": 4, "ordem": 2},
            {"id": "frances", "nome": "Francês", "tipo": "min_weekly", "unidade": "h", "meta": 4, "ordem": 3},
            {"id": "sono", "nome": "Sono", "tipo": "min_weekly", "unidade": "h", "meta": 56, "ordem": 4},
            {"id": "academia", "nome": "Academia", "tipo": "min_weekly", "unidade": "sessão", "meta": 4, "ordem": 5},
            {"id": "ortodontia", "nome": "Invisalign", "tipo": "min_weekly", "unidade": "h", "meta": 140, "ordem": 6},
            {"id": "medicina", "nome": "Estudo", "tipo": "min_weekly", "unidade": "h", "meta": 20, "ordem": 7},
            {"id": "redes", "nome": "Redes Sociais", "tipo": "max_daily_minutes", "unidade": "min", "meta": 55, "ordem": 8},
            {"id": "casa", "nome": "Casa e Gatos", "tipo": "min_weekly", "unidade": "dia", "meta": 7, "ordem": 9},
        ],
        "weeks": {
            week_start: {
                "exception": {"ativa": False, "motivo": "", "reposicao": ""},
                "rewards": [],
                "measures": [],
                "entries": [],
            }
        },
        "predefined": {
            "rewards": [
                "Atividade social extra no fim de semana",
                "Flexibilização pontual de horário de lazer no sábado",
                "Escolha de atividade em família",
            ],
            "measures": [
                "Redução de 15 minutos no teto diário de redes por 7 dias",
                "Suspensão de 1 atividade de lazer digital por 7 dias",
                "Reorganização obrigatória da agenda com prioridade de estudos",
            ],
        },
    }


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    ensure_data_dir()
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS contract (
              singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
              owner TEXT NOT NULL,
              created_at TEXT NOT NULL,
              school_choice TEXT NOT NULL,
              social_limit_minutes REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS activities (
              id TEXT PRIMARY KEY,
              nome TEXT NOT NULL,
              tipo TEXT NOT NULL,
              unidade TEXT NOT NULL,
              meta REAL NOT NULL,
              ordem INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS predefined_rewards (
              position INTEGER PRIMARY KEY,
              value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS predefined_measures (
              position INTEGER PRIMARY KEY,
              value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS weeks (
              week_start TEXT PRIMARY KEY,
              exception_ativa INTEGER NOT NULL DEFAULT 0,
              exception_motivo TEXT NOT NULL DEFAULT '',
              exception_reposicao TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS week_rewards (
              week_start TEXT NOT NULL REFERENCES weeks(week_start) ON DELETE CASCADE,
              position INTEGER NOT NULL,
              reward TEXT NOT NULL,
              PRIMARY KEY (week_start, position)
            );

            CREATE TABLE IF NOT EXISTS week_measures (
              week_start TEXT NOT NULL REFERENCES weeks(week_start) ON DELETE CASCADE,
              position INTEGER NOT NULL,
              measure TEXT NOT NULL,
              PRIMARY KEY (week_start, position)
            );

            CREATE TABLE IF NOT EXISTS entries (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              week_start TEXT NOT NULL REFERENCES weeks(week_start) ON DELETE CASCADE,
              position INTEGER NOT NULL,
              entry_date TEXT NOT NULL,
              activity_id TEXT NOT NULL,
              value REAL NOT NULL,
              notes TEXT NOT NULL DEFAULT ''
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_entries_week_position
              ON entries (week_start, position);
            """
        )


def validate_state_payload(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Estrutura de dados inválida.")
    if not isinstance(payload.get("activities"), list):
        raise ValueError("Estrutura de dados inválida: activities ausente.")
    if not isinstance(payload.get("weeks"), dict):
        raise ValueError("Estrutura de dados inválida: weeks ausente.")


def replace_state(conn: sqlite3.Connection, state: dict) -> None:
    validate_state_payload(state)
    contract = state.get("contract") or {}
    predefined = state.get("predefined") or {}

    with conn:
        conn.execute("DELETE FROM entries")
        conn.execute("DELETE FROM week_rewards")
        conn.execute("DELETE FROM week_measures")
        conn.execute("DELETE FROM weeks")
        conn.execute("DELETE FROM predefined_rewards")
        conn.execute("DELETE FROM predefined_measures")
        conn.execute("DELETE FROM activities")
        conn.execute("DELETE FROM contract")

        conn.execute(
            """
            INSERT INTO contract (singleton_id, owner, created_at, school_choice, social_limit_minutes)
            VALUES (1, ?, ?, ?, ?)
            """,
            (
                str(contract.get("owner", "Yara")),
                str(contract.get("createdAt", format_local_date_iso(date.today()))),
                str(contract.get("schoolChoice", "")),
                float(contract.get("socialLimitMinutes", 0) or 0),
            ),
        )

        for activity in state.get("activities", []):
            conn.execute(
                """
                INSERT INTO activities (id, nome, tipo, unidade, meta, ordem)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(activity.get("id", "")),
                    str(activity.get("nome", "")),
                    str(activity.get("tipo", "")),
                    str(activity.get("unidade", "")),
                    float(activity.get("meta", 0) or 0),
                    int(activity.get("ordem", 0) or 0),
                ),
            )

        for position, reward in enumerate(predefined.get("rewards", [])):
            conn.execute(
                "INSERT INTO predefined_rewards (position, value) VALUES (?, ?)",
                (position, str(reward)),
            )

        for position, measure in enumerate(predefined.get("measures", [])):
            conn.execute(
                "INSERT INTO predefined_measures (position, value) VALUES (?, ?)",
                (position, str(measure)),
            )

        for week_start, week in state.get("weeks", {}).items():
            exception = week.get("exception") or {}
            conn.execute(
                """
                INSERT INTO weeks (week_start, exception_ativa, exception_motivo, exception_reposicao)
                VALUES (?, ?, ?, ?)
                """,
                (
                    str(week_start),
                    1 if exception.get("ativa") else 0,
                    str(exception.get("motivo", "")),
                    str(exception.get("reposicao", "")),
                ),
            )

            for position, reward in enumerate(week.get("rewards", [])):
                conn.execute(
                    "INSERT INTO week_rewards (week_start, position, reward) VALUES (?, ?, ?)",
                    (str(week_start), position, str(reward)),
                )

            for position, measure in enumerate(week.get("measures", [])):
                conn.execute(
                    "INSERT INTO week_measures (week_start, position, measure) VALUES (?, ?, ?)",
                    (str(week_start), position, str(measure)),
                )

            for position, entry in enumerate(week.get("entries", [])):
                conn.execute(
                    """
                    INSERT INTO entries (week_start, position, entry_date, activity_id, value, notes)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(week_start),
                        position,
                        str(entry.get("date", "")),
                        str(entry.get("activityId", "")),
                        float(entry.get("value", 0) or 0),
                        str(entry.get("notes", "")),
                    ),
                )


def db_has_state(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT COUNT(*) AS total FROM activities").fetchone()
    return bool(row["total"])


def read_state(conn: sqlite3.Connection) -> dict:
    contract_row = conn.execute(
        """
        SELECT owner, created_at, school_choice, social_limit_minutes
        FROM contract
        WHERE singleton_id = 1
        """
    ).fetchone()

    activities = [
        {
            "id": row["id"],
            "nome": row["nome"],
            "tipo": row["tipo"],
            "unidade": row["unidade"],
            "meta": row["meta"],
            "ordem": row["ordem"],
        }
        for row in conn.execute(
            "SELECT id, nome, tipo, unidade, meta, ordem FROM activities ORDER BY ordem, id"
        ).fetchall()
    ]

    predefined_rewards = [
        row["value"]
        for row in conn.execute(
            "SELECT value FROM predefined_rewards ORDER BY position"
        ).fetchall()
    ]
    predefined_measures = [
        row["value"]
        for row in conn.execute(
            "SELECT value FROM predefined_measures ORDER BY position"
        ).fetchall()
    ]

    rewards_by_week = {}
    for row in conn.execute(
        "SELECT week_start, reward FROM week_rewards ORDER BY week_start, position"
    ).fetchall():
        rewards_by_week.setdefault(row["week_start"], []).append(row["reward"])

    measures_by_week = {}
    for row in conn.execute(
        "SELECT week_start, measure FROM week_measures ORDER BY week_start, position"
    ).fetchall():
        measures_by_week.setdefault(row["week_start"], []).append(row["measure"])

    entries_by_week = {}
    for row in conn.execute(
        """
        SELECT week_start, entry_date, activity_id, value, notes
        FROM entries
        ORDER BY week_start, position
        """
    ).fetchall():
        entries_by_week.setdefault(row["week_start"], []).append(
            {
                "date": row["entry_date"],
                "activityId": row["activity_id"],
                "value": row["value"],
                "notes": row["notes"],
            }
        )

    weeks = {}
    for row in conn.execute(
        """
        SELECT week_start, exception_ativa, exception_motivo, exception_reposicao
        FROM weeks
        ORDER BY week_start
        """
    ).fetchall():
        week_start = row["week_start"]
        weeks[week_start] = {
            "exception": {
                "ativa": bool(row["exception_ativa"]),
                "motivo": row["exception_motivo"],
                "reposicao": row["exception_reposicao"],
            },
            "rewards": rewards_by_week.get(week_start, []),
            "measures": measures_by_week.get(week_start, []),
            "entries": entries_by_week.get(week_start, []),
        }

    return {
        "contract": {
            "owner": contract_row["owner"] if contract_row else "Yara",
            "createdAt": contract_row["created_at"] if contract_row else format_local_date_iso(date.today()),
            "schoolChoice": contract_row["school_choice"] if contract_row else "",
            "socialLimitMinutes": contract_row["social_limit_minutes"] if contract_row else 0,
        },
        "activities": activities,
        "weeks": weeks,
        "predefined": {
            "rewards": predefined_rewards,
            "measures": predefined_measures,
        },
    }


def bootstrap_state() -> None:
    init_db()
    with get_connection() as conn:
        if db_has_state(conn):
            return

        if JSON_DATA_FILE.exists():
            with JSON_DATA_FILE.open("r", encoding="utf-8") as fh:
                replace_state(conn, json.load(fh))
            return

        replace_state(conn, create_default_state())


class YarionHandler(BaseHTTPRequestHandler):
    server_version = "YarionPython/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            with get_connection() as conn:
                self.send_json(HTTPStatus.OK, read_state(conn))
            return

        self.serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/state":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Rota não encontrada."})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Content-Length inválido."})
            return

        if content_length > MAX_BODY_BYTES:
            self.send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "Payload muito grande."})
            return

        body = self.rfile.read(content_length)
        try:
            payload = json.loads(body.decode("utf-8") if body else "{}")
            with get_connection() as conn:
                replace_state(conn, payload)
        except json.JSONDecodeError:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "JSON inválido."})
            return
        except ValueError as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except sqlite3.DatabaseError as exc:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"Falha no banco: {exc}"})
            return

        self.send_json(HTTPStatus.OK, {"ok": True})

    def serve_static(self, raw_path: str) -> None:
        rel_path = raw_path or "/"
        if rel_path == "/":
            rel_path = "/index.html"

        target = (PUBLIC_DIR / rel_path.lstrip("/")).resolve()
        if PUBLIC_DIR.resolve() not in target.parents and target != PUBLIC_DIR.resolve():
            self.send_json(HTTPStatus.FORBIDDEN, {"error": "Acesso negado."})
            return

        if not target.exists() or not target.is_file():
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Arquivo não encontrado."})
            return

        mime_type, _ = mimetypes.guess_type(str(target))
        mime_type = mime_type or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with target.open("rb") as fh:
            shutil.copyfileobj(fh, self.wfile)

    def send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return


def detect_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "localhost"


def create_server(port: int, configured_host: str) -> tuple[ThreadingHTTPServer, str]:
    candidate_hosts = []
    for host in [configured_host, "127.0.0.1", "0.0.0.0"]:
        if host and host not in candidate_hosts:
            candidate_hosts.append(host)

    last_error = None
    for host in candidate_hosts:
        try:
            return ThreadingHTTPServer((host, port), YarionHandler), host
        except OSError as exc:
            last_error = exc

    raise last_error or OSError("Não foi possível iniciar o servidor.")


def main() -> None:
    bootstrap_state()
    port = int(os.environ.get("PORT", "3080"))
    host = os.environ.get("HOST", "0.0.0.0")
    server, bound_host = create_server(port, host)
    sample_ip = detect_local_ip()
    print(f"App de acompanhamento rodando em http://{bound_host}:{port}")
    print(f"Acesso na rede local: http://{sample_ip}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
