#!/usr/bin/env python3
"""
Worker do Agendador — roda a cada minuto (LaunchAgent).
Lê a fila do Supabase, e pra cada post cujo horário chegou executa o pipeline
padrão (post + automação Inrō + capa + card na Central) e atualiza o status.
"""
import os, sys, json, time, datetime, traceback, tempfile
sys.path.insert(0, os.path.dirname(__file__))
import supa, engine, central

LOGDIR = os.path.expanduser("~/.config/meta-ads/staging")
os.makedirs(LOGDIR, exist_ok=True)

def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def process(post):
    pid = post["id"]
    buf = []
    def step(m):
        buf.append(f"{time.strftime('%H:%M:%S')} {m}")
        print(f"[worker:{pid[:8]}] {m}", flush=True)
    try:
        # baixa o vídeo do storage pra local (engine converte → H.264 garantido)
        vtmp = os.path.join(tempfile.gettempdir(), f"post-{pid}.src")
        step("baixando vídeo…")
        supa.download_video(post["video_url"], vtmp)

        caption_keywords = post.get("caption_keywords") or _auto_caption_kw(post["caption"])
        job = {
            "video": vtmp,
            "caption": post["caption"],
            "keyword": post["keyword"],
            "oferta": post["oferta"],
            "caption_keywords": caption_keywords,
            "cover_dest": os.path.join(LOGDIR, f"cover-{post['keyword'].lower()}.jpg"),
            "title": f"{post['keyword'].upper()} · comment→DM (follow-gate)",
        }
        step("publicando + automação Inrō…")
        result = engine.process_job(job)

        central_url = None
        if post.get("link") and os.path.isdir(central.CENTRAL) and not os.environ.get("SKIP_CENTRAL"):
            step("publicando card na Central…")
            titulo, subtitulo = _auto_card(post["caption"], post["oferta"], post.get("card_title"), post.get("card_subtitle"))
            central_url = central.publish_card(
                slug=post["keyword"].lower(),
                keyword=post["keyword"],
                card_title=titulo,
                card_subtitle=subtitulo,
                card_oque=subtitulo,
                link=post["link"],
                cover_path=result.get("cover"),
            )

        supa.update(pid, {
            "status": "published",
            "media_id": result["media_id"],
            "scenario_id": str(result.get("scenario_id") or ""),
            "cover_url": result.get("cover") or "",
            "run_at": now_iso(),
            "log": "\n".join(buf) + (f"\ncentral: {central_url}" if central_url else ""),
            "error": None,
        })
        step("OK ✅")
    except Exception as e:
        err = f"{e}\n{traceback.format_exc()}"
        step(f"FALHOU: {e}")
        supa.update(pid, {"status": "failed", "run_at": now_iso(),
                          "error": err[:4000], "log": "\n".join(buf)})

def _auto_card(caption, oferta, titulo=None, subtitulo=None):
    """Gera título e subtítulo do card a partir da legenda + oferta (se não vierem prontos)."""
    linhas = [l.strip() for l in caption.split("\n")
              if l.strip() and not l.strip().startswith("#") and "comenta" not in l.lower()]
    promessa = linhas[0] if linhas else (oferta or "")
    t = titulo or promessa.split(".")[0].strip()
    if len(t) > 65:
        t = t[:62].rstrip() + "…"
    s = subtitulo or (oferta[:1].upper() + oferta[1:] if oferta else promessa)
    return t, s

def _auto_caption_kw(caption):
    """Se não vierem caption_keywords, usa 3 frases longas da legenda pra casar o post."""
    frases = [l.strip() for l in caption.replace("\n", " ").split(".") if len(l.strip()) > 35]
    return frases[:3] if frases else [caption[:60]]

def main():
    due = supa.due_posts()
    if not due:
        return
    print(f"[worker] {len(due)} post(s) na fila", flush=True)
    for post in due:
        if supa.claim(post["id"]):
            process(post)

if __name__ == "__main__":
    main()
