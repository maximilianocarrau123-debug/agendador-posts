"""
Publica o card da isca na Central de Iscas (central-iscas.vercel.app).
Gera src/iscas/<slug>.tsx de um template, registra no registry.ts, copia a capa,
faz build e deploy. Mantém o mesmo estilo dos cards artesanais.
"""
import os, re, subprocess, shutil

CENTRAL = os.path.expanduser("~/projects/central-iscas")

CARD_TMPL = '''/* ISCA: {slug} — gerada pelo Agendador */
import {{ Secao, StepHeader, Box, LinkRow }} from '../components/blocks'

const LINK = {link!r}

export const ISCA = {{
  eyebrow: 'Max Carrau · IA na prática',
  titulo: <>{titulo}</>,
  subtitulo: {subtitulo!r},
  pitch: <>{pitch}</>,
  indice: ['O que é', 'Como pegar'],
}}

export function Conteudo() {{
  return (
    <>
      <Secao>
        <StepHeader n={{1}} titulo="O que é" sub={oque_sub!r} />
        <Box titulo="O que é:">{oque}</Box>
      </Secao>
      <Secao>
        <StepHeader n={{2}} titulo="Como pegar" sub="Pega aqui — corre que isso voa" />
        <LinkRow label={link_label!r} tag="Pega aqui" href={{LINK}} />
        <Box variante="note" titulo="Quer ir além?">
          Na Claude Society a gente monta isso ao vivo toda semana — pro seu caso real.
          Entra no grupo que eu te mostro como começar. ↓
        </Box>
      </Secao>
    </>
  )
}}
'''

def publish_card(slug, keyword, card_title, card_subtitle, card_oque, link,
                 cover_path=None, aliases=None):
    aliases = aliases or []
    # 1) escreve o card .tsx
    card = CARD_TMPL.format(
        slug=slug, link=link,
        titulo=card_title, subtitulo=card_subtitle,
        pitch=card_subtitle, oque_sub=card_subtitle, oque=card_oque,
        link_label=f"Link oficial — {card_title}", link_label2="",
    )
    with open(f"{CENTRAL}/src/iscas/{slug}.tsx", "w") as f:
        f.write(card)

    # 2) registra no registry.ts (import + entrada), se ainda não houver
    reg_path = f"{CENTRAL}/src/iscas/registry.ts"
    reg = open(reg_path).read()
    var = re.sub(r"[^a-zA-Z0-9]", "", slug.title())
    var = var[0].lower() + var[1:]
    if f"./{slug}'" not in reg:
        reg = reg.replace("export type Isca",
                          f"import * as {var} from './{slug}'\n\nexport type Isca", 1)
        alias_list = ", ".join(repr(a) for a in ([keyword.lower()] + aliases))
        entry = (f"  {{\n    slug: {slug!r},\n    palavra: {keyword.upper()!r},\n"
                 f"    aliases: [{alias_list}],\n    card: {card_title!r},\n"
                 f"    tagline: {card_subtitle!r},\n    capa: '/capas/{slug}.jpg',\n"
                 f"    titulo: {var}.ISCA.titulo,\n    Conteudo: {var}.Conteudo,\n  }},\n]")
        reg = reg.rstrip().rstrip("]").rstrip().rstrip(",") + ",\n" + entry
        # normaliza fechamento
        if not reg.rstrip().endswith("]"):
            reg = reg.rstrip() + "\n]"
        open(reg_path, "w").write(reg)

    # 3) copia a capa
    if cover_path and os.path.exists(cover_path):
        os.makedirs(f"{CENTRAL}/public/capas", exist_ok=True)
        shutil.copy(cover_path, f"{CENTRAL}/public/capas/{slug}.jpg")

    # 4) build + deploy
    env = dict(os.environ, PATH="/usr/local/bin:" + os.environ.get("PATH", ""))
    subprocess.run(["npm", "run", "build"], cwd=CENTRAL, check=True, env=env,
                   capture_output=True)
    subprocess.run(["npx", "vercel", "--prod", "--yes"], cwd=CENTRAL, check=True, env=env,
                   capture_output=True)
    return f"https://central-iscas.vercel.app (card {slug})"
