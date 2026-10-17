# JARVIS Cloud — Vercel

Arquivos devem ficar diretamente na raiz do repositório.

## Vercel
Não configure uma subpasta como Root Directory.

Configure em Settings > Environment Variables:
- `JARVIS_TOKEN`
- `GROQ_API_KEY`
- `GROQ_MODEL`
- `GROQ_STT_MODEL`

Faça um novo deploy depois de substituir os arquivos.

## Testes
- `/` deve retornar `JARVIS Cloud`
- `/api/health` mostra o estado da configuração
- `/docs` abre o Swagger do FastAPI

O `vercel.json` usa Vercel Services com `app.py` / objeto `app` explicitamente como `app:app`.
