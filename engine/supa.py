"""Acesso ao Supabase (fila + storage) com a service/secret key."""
import json, os, urllib.request, urllib.parse

def _env():
    # GitHub Actions / VPS: via env var; local: arquivo
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY")
    if url and key:
        return url, key
    p = os.path.expanduser("~/.config/supabase-leads/.env")
    for line in open(p):
        if line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if k == "SUPABASE_URL":
            url = v
        elif k == "SUPABASE_SECRET_KEY":
            key = v
    return url, key

URL, KEY = _env()
TABLE = "scheduled_posts"
BUCKET = "post-videos"

def _req(method, path, body=None, extra_headers=None):
    headers = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(URL + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
        return json.loads(raw) if raw else None

def due_posts():
    """Posts 'scheduled' cujo horário já chegou."""
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    q = f"/rest/v1/{TABLE}?status=eq.scheduled&scheduled_at=lte.{urllib.parse.quote(now)}&order=scheduled_at.asc"
    return _req("GET", q) or []

def update(post_id, fields):
    return _req("PATCH", f"/rest/v1/{TABLE}?id=eq.{post_id}", fields,
                {"Prefer": "return=representation"})

def claim(post_id):
    """Marca como processing só se ainda estiver scheduled (evita corrida)."""
    res = _req("PATCH",
               f"/rest/v1/{TABLE}?id=eq.{post_id}&status=eq.scheduled",
               {"status": "processing"}, {"Prefer": "return=representation"})
    return bool(res)

def download_video(video_url, dest):
    """Baixa o vídeo (URL pública do storage ou externa) pra um arquivo local."""
    urllib.request.urlretrieve(video_url, dest)
    return dest
