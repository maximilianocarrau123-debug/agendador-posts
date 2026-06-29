import { createClient } from '@supabase/supabase-js'

const supa = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SECRET_KEY)

export default async function handler(req, res) {
  if ((req.headers['x-app-pass'] || '') !== process.env.APP_PASS)
    return res.status(401).json({ error: 'senha inválida' })

  if (req.method === 'GET') {
    const { data, error } = await supa.from('scheduled_posts')
      .select('*').order('scheduled_at', { ascending: false }).limit(50)
    return error ? res.status(500).json({ error: error.message }) : res.json(data)
  }
  if (req.method === 'POST') {
    const { data, error } = await supa.from('scheduled_posts').insert(req.body).select()
    return error ? res.status(500).json({ error: error.message }) : res.json(data)
  }
  res.status(405).end()
}
