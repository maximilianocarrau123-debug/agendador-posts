#!/usr/bin/env python3
"""
Motor do Agendador de Posts do Max.
Recebe um "job" (vídeo + legenda + keyword + link) e executa o pipeline PADRÃO:
  1. garante o vídeo numa URL pública (converte HEVC→H.264 se preciso + sobe catbox)
  2. publica o Reel no @maxcarrau.ia (Instagram Graph API)
  3. cria a automação Inrō no post exato (comment→DM follow-gate, A/B 2x, casa pela legenda)
  4. baixa a capa real do reel
  (a publicação do card na Central é feita pelo módulo central.py)

Reutiliza exatamente as chamadas validadas em 29/06/2026.
Sem dependências externas — só stdlib (urllib, subprocess, json).
"""
import json, os, sys, time, subprocess, urllib.request, urllib.parse, mimetypes, ssl

HOME = os.path.expanduser("~")
CFG = os.path.join(HOME, ".config", "meta-ads")

IG_USER_ID = "17841479947331244"           # @maxcarrau.ia
GRAPH = "https://graph.facebook.com/v21.0"
INRO_MCP = "https://api.inro.social/mcp"
def _inro_token():
    env = os.environ.get("INRO_TOKEN")
    if env:
        return env.strip()
    p = os.path.join(CFG, "inro_token.txt")
    return open(p).read().strip() if os.path.exists(p) else ""
INRO_TOKEN = _inro_token()
LEADS_FOLDER_DEFAULT = None                 # criado por keyword se ausente

def _tok():
    # GitHub Actions / VPS: token via env var; local: arquivo
    env = os.environ.get("INSTA_TOKEN")
    if env:
        return env.strip()
    return open(os.path.join(CFG, "token_perm.txt")).read().strip()

def log(msg):
    print(f"[engine] {msg}", flush=True)

# ---------- HTTP helpers ----------
def _graph_get(path, **params):
    params["access_token"] = _tok()
    url = f"{GRAPH}/{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)

def _graph_post(path, **params):
    params["access_token"] = _tok()
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(f"{GRAPH}/{path}", data=data, timeout=120) as r:
        return json.load(r)

def _inro_call(tool, arguments):
    """Chama uma tool do MCP do Inrō via JSON-RPC (stateless)."""
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": tool, "arguments": arguments}}).encode()
    req = urllib.request.Request(INRO_MCP, data=body, headers={
        "Authorization": f"Bearer {INRO_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read().decode()
    # resposta pode vir como JSON puro ou SSE — extrai o objeto result
    obj = json.loads(raw[raw.index("{"):])
    inner = obj["result"]["content"][0]["text"]
    return json.loads(inner)

# ---------- 1) vídeo público ----------
def ensure_public_video(source):
    """source: URL http(s) (usa direto) OU caminho local (converte + sobe catbox)."""
    if source.startswith("http"):
        log(f"vídeo já é URL pública: {source}")
        return source
    src = os.path.expanduser(source)
    mp4 = os.path.join(CFG, "staging", "engine-" + str(int(os.path.getmtime(src))) + ".mp4")
    os.makedirs(os.path.dirname(mp4), exist_ok=True)
    log("convertendo vídeo → H.264 1080x1920…")
    subprocess.run(["ffmpeg", "-y", "-i", src, "-c:v", "libx264", "-profile:v", "high",
                    "-pix_fmt", "yuv420p", "-vf", "scale=1080:1920", "-r", "30",
                    "-b:v", "9M", "-maxrate", "12M", "-bufsize", "18M",
                    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", mp4],
                   check=True, capture_output=True)
    log("subindo pro catbox…")
    out = subprocess.run(["curl", "-s", "-F", "reqtype=fileupload",
                          "-F", f"fileToUpload=@{mp4}", "https://catbox.moe/user/api.php"],
                         check=True, capture_output=True, text=True).stdout.strip()
    if not out.startswith("http"):
        raise RuntimeError(f"falha no upload catbox: {out}")
    log(f"vídeo público: {out}")
    return out

# ---------- 2) publica reel ----------
def publish_reel(video_url, caption):
    log("criando container REELS…")
    c = _graph_post(f"{IG_USER_ID}/media", media_type="REELS",
                    video_url=video_url, caption=caption)
    cid = c.get("id")
    if not cid:
        raise RuntimeError(f"falha no container: {c}")
    for i in range(1, 31):
        st = _graph_get(cid, fields="status_code").get("status_code")
        log(f"status[{i}]: {st}")
        if st == "FINISHED":
            break
        if st == "ERROR":
            raise RuntimeError("container deu ERROR")
        time.sleep(10)
    pub = _graph_post(f"{IG_USER_ID}/media_publish", creation_id=cid)
    mid = pub.get("id")
    if not mid:
        raise RuntimeError(f"falha ao publicar: {pub}")
    log(f"PUBLICADO media_id={mid}")
    return mid

# ---------- 2b) publica carrossel (imagens) ----------
def publish_carousel(image_urls, caption):
    log(f"criando {len(image_urls)} itens de carrossel…")
    children = []
    for i, u in enumerate(image_urls, 1):
        c = _graph_post(f"{IG_USER_ID}/media", is_carousel_item="true", image_url=u)
        cid = c.get("id")
        if not cid:
            raise RuntimeError(f"falha item {i}: {c}")
        children.append(cid)
        log(f"item {i}/{len(image_urls)} ok")
    log("criando container CAROUSEL…")
    cont = _graph_post(f"{IG_USER_ID}/media", media_type="CAROUSEL",
                       children=",".join(children), caption=caption)
    cid = cont.get("id")
    if not cid:
        raise RuntimeError(f"falha no container carousel: {cont}")
    for i in range(1, 31):
        st = _graph_get(cid, fields="status_code").get("status_code")
        log(f"status[{i}]: {st}")
        if st == "FINISHED":
            break
        if st == "ERROR":
            raise RuntimeError("container carousel deu ERROR")
        time.sleep(8)
    pub = _graph_post(f"{IG_USER_ID}/media_publish", creation_id=cid)
    mid = pub.get("id")
    if not mid:
        raise RuntimeError(f"falha ao publicar carrossel: {pub}")
    log(f"CARROSSEL PUBLICADO media_id={mid}")
    return mid

# ---------- 3) automação Inrō padrão ----------
def ensure_leads_folder(keyword):
    name = f"Leads · {keyword.upper()}"
    folders = _inro_call("folders", {"action": "list", "action_params": {"per_page": 100}})
    for f in folders.get("folders", folders.get("data", [])):
        if f.get("name") == name:
            return f["id"]
    created = _inro_call("folders", {"action": "create", "action_params": {"name": name}})
    return created["id"]

def _dm_variants(keyword, oferta):
    """4 variações da DM follow-gate (A/B 2x). `oferta` = 1 frase do que a pessoa pega."""
    base = lambda abre, fecho: (
        f"{abre}\n\nPra eu te mandar {oferta} é rapidinho: me segue aqui 👉 só libero "
        f"pra quem segue.\n\nDepois é só ir na minha BIO 👆, clicar no link e entrar no "
        f"grupo — é lá dentro que vai o material + coisa nova toda semana.\n\n{fecho}\n\n"
        f"⚠️ Importante: SEM ME SEGUIR, não libero.")
    return [
        base("Eaí! 🙌 Você já tá me seguindo?", "Corre que isso voa! 🚀"),
        base("Opa! 🔥 Antes de tudo: já me segue?", "Bora, não perde! 🚀"),
        base("Salve! 👋 Você já me segue por aqui?", "Pega logo! ✨"),
        base("Eaí! 😄 Bora garantir o seu?", "Corre! 🔥"),
    ]

def create_inro_automation(title, caption_keywords, keyword, oferta, aliases=None):
    folder_id = ensure_leads_folder(keyword)
    kw = keyword.upper()
    variants = [keyword.upper(), keyword.lower(), keyword.capitalize(),
                keyword.upper()+"!", keyword.lower()+"!", keyword.capitalize()+"!"]
    m = _dm_variants(keyword, oferta)
    actions = [
        {"action_type": "comment", "action_key": "reply",
         "options": {"comment_limiting": True,
                     "comment_variants": ["Te respondi no direct 👀", "Olha teu direct 🔥", "Te chamei no direct 👀"]}},
        {"action_type": "folder", "action_key": "fo",
         "options": {"folder_ids": [folder_id], "folder_action": "add"}, "parent_key": "reply"},
        {"action_type": "update_property", "action_key": "po", "content": keyword.lower(),
         "options": {"contact_property": "origem_isca"}, "parent_key": "fo"},
        {"action_type": "ab_testing", "action_key": "ab1", "options": {"ratio": 50}, "parent_key": "po"},
        {"action_type": "ab_testing", "action_key": "ab2", "options": {"ratio": 50}, "parent_key": "ab1", "parent_branch": "option_a"},
        {"action_type": "ab_testing", "action_key": "ab3", "options": {"ratio": 50}, "parent_key": "ab1", "parent_branch": "option_b"},
        {"action_type": "message", "action_key": "m1", "content": m[0], "parent_key": "ab2", "parent_branch": "option_a"},
        {"action_type": "message", "action_key": "m2", "content": m[1], "parent_key": "ab2", "parent_branch": "option_b"},
        {"action_type": "message", "action_key": "m3", "content": m[2], "parent_key": "ab3", "parent_branch": "option_a"},
        {"action_type": "message", "action_key": "m4", "content": m[3], "parent_key": "ab3", "parent_branch": "option_b"},
    ]
    args = {"action": "create", "action_params": {
        "title": title, "scenario_type": "comment_to_dm", "active": True,
        "triggers": [{"trigger_type": "comment", "options": {"comment_options": {
            "post_type": "caption_keywords", "comment_type": "comment_keywords",
            "allow_replies": True, "caption_keywords": caption_keywords,
            "comment_keywords": variants}}}],
        "actions": actions}}
    res = _inro_call("scenarios", args)
    sid = res.get("scenario", {}).get("id")
    log(f"automação Inrō criada: scenario {sid}")
    return sid

# ---------- 4) capa real ----------
def fetch_cover(media_id, dest):
    for i in range(1, 13):
        thumb = _graph_get(media_id, fields="thumbnail_url").get("thumbnail_url")
        if thumb:
            urllib.request.urlretrieve(thumb, dest)
            log(f"capa salva: {dest}")
            return dest
        time.sleep(10)
    log("capa (thumbnail) não ficou disponível a tempo")
    return None

# ---------- pipeline ----------
def process_job(job):
    """job: dict com video, caption, keyword, oferta, caption_keywords, [title].
    'video' = URL/caminho de vídeo (Reel) OU um JSON array de URLs de imagem (carrossel)."""
    log(f"=== JOB {job.get('keyword')} @ {time.strftime('%H:%M:%S')} ===")
    v = (job["video"] or "").strip()
    if v.startswith("["):                       # carrossel de imagens
        image_urls = json.loads(v)
        media_id = publish_carousel(image_urls, job["caption"])
        video_url = v
    else:                                       # Reel (vídeo)
        video_url = ensure_public_video(job["video"])
        media_id = publish_reel(video_url, job["caption"])
    title = job.get("title") or f"{job['keyword'].upper()} · comment→DM (follow-gate)"
    sid = create_inro_automation(title, job["caption_keywords"], job["keyword"], job["oferta"])
    cover = None
    if job.get("cover_dest"):
        cover = fetch_cover(media_id, os.path.expanduser(job["cover_dest"]))
    return {"media_id": media_id, "scenario_id": sid, "cover": cover, "video_url": video_url}

if __name__ == "__main__":
    # uso: engine.py job.json
    job = json.load(open(sys.argv[1]))
    print(json.dumps(process_job(job), ensure_ascii=False, indent=2))
