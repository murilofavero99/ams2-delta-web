# Setup do Supabase

Esse guia tem passos curtos pra ativar o Supabase como backend de armazenamento.

> **Sem fazer esses passos**, a app continua funcionando do jeito antigo (arquivos no Railway).
> A transição é opcional e reversível.

---

## 1. Criar conta + projeto (5 min)

1. Vai em [supabase.com](https://supabase.com) e clica em **Start your project**
2. Faz login com GitHub
3. Cria um **novo projeto**:
   - Nome: `ams2-delta` (ou outro)
   - Senha do banco: escolhe uma e **guarda**
   - Região: `South America (São Paulo)` (mais perto = mais rápido)
4. Espera ~2 min o projeto ficar pronto

---

## 2. Aplicar o schema SQL

1. No dashboard do projeto → **SQL Editor**
2. Clica em **New query**
3. Cola o conteúdo de [`backend/app/db/schema.sql`](backend/app/db/schema.sql)
4. Clica **Run** (canto inferior direito)
5. Deve aparecer "Success. No rows returned"

---

## 3. Criar o bucket de Storage

1. Menu lateral → **Storage**
2. Clica em **New bucket**
3. Nome: `telemetry`
4. **Public bucket**: marca como público (mais simples) — ou deixa privado e configure RLS depois
5. Clica **Create bucket**

---

## 4. Pegar credenciais

1. Menu lateral → **Project Settings** (ícone de engrenagem)
2. → **API**
3. Copia:
   - **Project URL** (`https://xxxxx.supabase.co`)
   - **service_role** key (NÃO a `anon` — a service_role tem permissão completa, ideal pro backend)

⚠️ **Não compartilhe a service_role key publicamente** — ela dá acesso total.

---

## 5. Configurar as variáveis de ambiente

### Railway (backend de produção)

1. Dashboard do Railway → seu serviço `ams2-delta-web`
2. Aba **Variables**
3. Adiciona:
   - `SUPABASE_URL` = `https://xxxxx.supabase.co`
   - `SUPABASE_KEY` = `eyJhbGciOi...` (service_role)
   - `SUPABASE_BUCKET` = `telemetry` (opcional, é o default)
4. O Railway vai redeployar automaticamente

### PC local (para upload direto + script de migração)

**Windows CMD (temporário, só na sessão atual):**
```cmd
set SUPABASE_URL=https://xxxxx.supabase.co
set SUPABASE_KEY=eyJhbGciOi...
```

**Windows PowerShell (temporário):**
```powershell
$env:SUPABASE_URL = "https://xxxxx.supabase.co"
$env:SUPABASE_KEY = "eyJhbGciOi..."
```

**Permanente (Windows):** Painel de Controle → Variáveis de Ambiente do Usuário.

---

## 6. Migrar sessões existentes

Depois de setar as env vars no PC local:

```bash
cd backend
pip install supabase   # se ainda não tiver
python -m scripts.migrate_to_supabase
```

Isso pega todas as sessões em `backend/sessions/` e sobe pro Supabase
(metadata vai pra tabela `sessions`/`laps`, parquet vai pro bucket Storage).

Para evitar reupload de sessões já migradas:
```bash
python -m scripts.migrate_to_supabase --skip-existing
```

---

## 7. Validar

1. Abre [`ams2-delta-web.vercel.app`](https://ams2-delta-web.vercel.app)
2. As sessões devem aparecer normalmente
3. No Supabase Dashboard → **Table Editor** → `sessions` deve mostrar suas linhas
4. → **Storage** → `telemetry` deve listar os `*.parquet`

Se algo der errado, **as env vars desativam-se simplesmente removendo elas do Railway** — a app cai automaticamente no modo legacy (disco).

---

## Como funciona depois disso

- Você roda `python -m ams2_delta.udp.listener --name X` localmente
- Termina com Ctrl+C
- O listener:
  1. Salva local em `backend/sessions/`
  2. Detecta as env vars Supabase no seu PC e faz **upload direto** (sem passar pelo Railway)
  3. Se as vars não estão setadas no PC, faz o upload via HTTP pro Railway, que detecta o Supabase no servidor e repassa
- Sessão fica disponível imediatamente em `ams2-delta-web.vercel.app`

---

## Dúvidas comuns

**Q: Preciso pagar?**  
A: Não. Free tier do Supabase = 500MB Postgres + 1GB Storage + 2GB bandwidth/mês. Mais que suficiente pra uso pessoal (cada sessão tem ~1-2MB).

**Q: Posso voltar atrás?**  
A: Sim. Remove `SUPABASE_URL`/`SUPABASE_KEY` do Railway e ele volta a usar disco. Os arquivos no disco continuam intactos.

**Q: Os parquets ficam onde no Supabase?**  
A: No bucket `telemetry`, com path `<session_id>/telemetry.parquet`.

**Q: O Railway volume ainda é necessário?**  
A: Não, depois que o Supabase estiver ativo. Pode até desativar o volume no Railway pra economizar.
