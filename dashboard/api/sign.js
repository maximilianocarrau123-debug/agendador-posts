import { createClient } from '@supabase/supabase-js'

const supa = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SECRET_KEY)

// Gera uma URL assinada de upload (a chave nunca sai do servidor).
export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).end()
  if ((req.headers['x-app-pass'] || '') !== process.env.APP_PASS)
    return res.status(401).json({ error: 'senha inválida' })

  const { filename } = req.body || {}
  const path = `${Date.now()}-${String(filename || 'video').replace(/[^a-zA-Z0-9.]/g, '_')}`
  const { data, error } = await supa.storage.from('post-videos').createSignedUploadUrl(path)
  if (error) return res.status(500).json({ error: error.message })
  const publicUrl = `${process.env.SUPABASE_URL}/storage/v1/object/public/post-videos/${path}`
  res.json({ path: data.path, token: data.token, publicUrl })
}
