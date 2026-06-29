-- =========================================================
-- Agendador de Posts do Max — schema da fila
-- Rodar 1x no SQL Editor do Supabase (projeto de leads).
-- =========================================================

-- 1) Tabela da fila de posts agendados
create table if not exists public.scheduled_posts (
  id            uuid primary key default gen_random_uuid(),
  created_at    timestamptz not null default now(),
  scheduled_at  timestamptz not null,                 -- quando publicar
  status        text not null default 'scheduled',    -- scheduled | processing | published | failed
  -- conteúdo do post
  video_url     text,                                 -- URL pública do vídeo (storage ou catbox)
  caption       text not null,                        -- legenda completa (com hashtags)
  keyword       text not null,                        -- palavra da isca (ex: CORPS)
  oferta        text not null,                        -- 1 frase do que a pessoa pega na DM
  link          text,                                 -- link de inscrição/material (Central)
  caption_keywords jsonb,                             -- frases únicas da legenda (casa o post no Inrō)
  -- campos do card da Central (opcionais)
  card_title    text,
  card_subtitle text,
  card_oque     text,
  -- resultado do processamento
  media_id      text,
  scenario_id   text,
  cover_url     text,
  run_at        timestamptz,
  error         text,
  log           text
);

create index if not exists idx_scheduled_posts_due
  on public.scheduled_posts (status, scheduled_at);

-- 2) Bucket de vídeos (privado; o worker baixa com a service key)
insert into storage.buckets (id, name, public)
values ('post-videos', 'post-videos', false)
on conflict (id) do nothing;

-- 3) RLS: a tabela é operada pela secret key (service role) no worker.
--    Pro dashboard ler/escrever com a anon key, habilite policies conforme o login.
alter table public.scheduled_posts enable row level security;

-- Policy permissiva pro MVP (dashboard sem auth, só você usa). Ajustar depois.
drop policy if exists "agendador_all" on public.scheduled_posts;
create policy "agendador_all" on public.scheduled_posts
  for all using (true) with check (true);
