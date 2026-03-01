import streamlit as st
import requests
import json
import smtplib
import secrets
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date, timedelta, datetime, timezone
import time

# ══════════════════════════════════════════════════════
# CONFIGURAÇÃO
# ══════════════════════════════════════════════════════

st.set_page_config(page_title="Admin — DocCorretor IA", page_icon="🛡️", layout="wide")

st.markdown("""
<style>
    #MainMenu { visibility: hidden !important; display: none !important; }
    header { visibility: hidden !important; }
    header[data-testid="stHeader"] { visibility: hidden !important; display: none !important; }
    footer { visibility: hidden !important; display: none !important; }
    .stDeployButton { display: none !important; }
    [data-testid="stToolbar"] { display: none !important; visibility: hidden !important; }
    [data-testid="stDecoration"] { display: none !important; visibility: hidden !important; }
    [data-testid="stStatusWidget"] { display: none !important; }
    [data-testid="manage-app-button"] { display: none !important; }
    .st-emotion-cache-zq5wmm { display: none !important; }
    .st-emotion-cache-1dp5vir { display: none !important; }
    .viewerBadge_container__r5tak { display: none !important; }
    .styles_viewerBadge__CvC9N { display: none !important; }
    #stDecoration { display: none !important; }
    div[data-testid="collapsedControl"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

SUPABASE_URL  = "https://ryvgqesflxbtqbdhspdy.supabase.co"
SUPABASE_KEY  = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJ5dmdxZXNmbHhidHFiZGhzcGR5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzIyOTIyMjMsImV4cCI6MjA4Nzg2ODIyM30.HhW3_bSQ8fZvY17XTwerhXdW7hF2uf3gKUSYm9ixkys"
ADMIN_SENHA   = "admin@docorretor2025"   # ← troque pela sua senha master
ADMIN_EMAIL   = "compracertavip@gmail.com"  # email do admin master
EMAIL_REMETENTE = "daniellaandrade1989@gmail.com"  # gmail que envia os emails
EMAIL_SENHA_APP = "fpupijekoocowhcl"              # senha de app desse gmail
APP_URL_ADMIN   = "https://doc-corretor-admin.streamlit.app"  # ← URL do seu painel admin
APP_URL_CLIENTE = "https://doc-corretor-ia.streamlit.app"     # ← URL do app do cliente

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

VALORES_PLANO = {"mensal": 97.0, "semestral": 497.0, "anual": 897.0}

# ══════════════════════════════════════════════════════
# SUPABASE HELPERS
# ══════════════════════════════════════════════════════

ORDEM_TABELA = {
    "clientes":   "criado_em.desc",
    "acessos":    "acessado_em.desc",
    "usos":       "usado_em.desc",
    "pagamentos": "pago_em.desc",
    "tokens_recuperacao": "criado_em.desc",
}

def sb_get(tabela, filtro=""):
    ordem = ORDEM_TABELA.get(tabela, "criado_em.desc")
    url = f"{SUPABASE_URL}/rest/v1/{tabela}?{filtro}&order={ordem}"
    r = requests.get(url, headers=HEADERS)
    if r.status_code == 200:
        return r.json()
    return []

def sb_post(tabela, dados):
    url = f"{SUPABASE_URL}/rest/v1/{tabela}"
    r = requests.post(url, headers=HEADERS, json=dados)
    return r.status_code in (200, 201), r.json()

def sb_patch(tabela, filtro, dados):
    url = f"{SUPABASE_URL}/rest/v1/{tabela}?{filtro}"
    r = requests.patch(url, headers=HEADERS, json=dados)
    return r.status_code in (200, 204)

def sb_delete(tabela, filtro):
    url = f"{SUPABASE_URL}/rest/v1/{tabela}?{filtro}"
    r = requests.delete(url, headers=HEADERS)
    return r.status_code in (200, 204)

def calcular_vencimento(plano, inicio=None):
    d = inicio or date.today()
    if plano == "mensal":    return d + timedelta(days=30)
    if plano == "semestral": return d + timedelta(days=180)
    if plano == "anual":     return d + timedelta(days=365)
    return d + timedelta(days=30)

# ══════════════════════════════════════════════════════
# EMAIL
# ══════════════════════════════════════════════════════

def enviar_email_recuperacao(destinatario, assunto, corpo_html):
    msg = MIMEMultipart("alternative")
    msg["From"]    = EMAIL_REMETENTE
    msg["To"]      = destinatario
    msg["Subject"] = assunto
    msg.attach(MIMEText(corpo_html, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(EMAIL_REMETENTE, EMAIL_SENHA_APP)
        s.sendmail(EMAIL_REMETENTE, destinatario, msg.as_bytes())

# ══════════════════════════════════════════════════════
# RECUPERAÇÃO DE SENHA
# ══════════════════════════════════════════════════════

def criar_token(tipo, referencia):
    """Cria token de recuperação válido por 30 min e salva no Supabase."""
    token  = secrets.token_urlsafe(32)
    expira = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    sb_post("tokens_recuperacao", {
        "tipo": tipo,
        "referencia": referencia,
        "token": token,
        "usado": False,
        "expira_em": expira
    })
    return token

def validar_token(token):
    """Verifica se o token é válido, não usado e não expirado."""
    url = f"{SUPABASE_URL}/rest/v1/tokens_recuperacao?token=eq.{token}&usado=eq.false&select=*"
    r   = requests.get(url, headers=HEADERS)
    if r.status_code != 200: return None
    dados = r.json()
    if not dados: return None
    rec = dados[0]
    expira = datetime.fromisoformat(rec["expira_em"])
    if expira.tzinfo is None:
        expira = expira.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expira:
        return None
    return rec

def marcar_token_usado(token_id):
    sb_patch("tokens_recuperacao", f"id=eq.{token_id}", {"usado": True})

# ══════════════════════════════════════════════════════
# LOGIN ADMIN + RECUPERAÇÃO DE SENHA
# ══════════════════════════════════════════════════════

SESSAO_ADMIN_TOKEN = "sessao_admin_ativa_2025"  # token fixo de sessão

def check_admin():
    params    = st.query_params
    token_url = params.get("token", "")
    sessao    = params.get("s", "")

    # ── Restaura sessão via query param após F5 ──
    if sessao == SESSAO_ADMIN_TOKEN and not st.session_state.get("admin_ok"):
        st.session_state["admin_ok"] = True

    # ── Fluxo de redefinição via token ──
    if token_url and not st.session_state.get("admin_ok"):
        col1, col2, col3 = st.columns([1,1.2,1])
        with col2:
            st.markdown("## 🛡️ DocCorretor IA")
            st.markdown("#### Redefinir senha master")
            st.divider()
            rec = validar_token(token_url)
            if not rec or rec.get("tipo") != "admin":
                st.error("❌ Link inválido ou expirado. Solicite um novo.")
                st.stop()
            nova1 = st.text_input("Nova senha", type="password")
            nova2 = st.text_input("Confirme a nova senha", type="password")
            if st.button("✅ Salvar nova senha", use_container_width=True, type="primary"):
                if not nova1 or len(nova1) < 6:
                    st.error("Senha deve ter pelo menos 6 caracteres.")
                elif nova1 != nova2:
                    st.error("As senhas não coincidem.")
                else:
                    marcar_token_usado(rec["id"])
                    st.success("✅ Token validado! Atualize a variável ADMIN_SENHA no código com:")
                    st.code(nova1)
                    st.info("Copie a senha acima, atualize no admin.py e faça novo deploy.")
            st.stop()

    # ── Tela de login normal ──
    if not st.session_state.get("admin_ok", False):
        col1, col2, col3 = st.columns([1,1.2,1])
        with col2:
            st.markdown("## 🛡️ DocCorretor IA")
            st.markdown("#### Painel Administrador")
            st.divider()
            tela = st.radio("", ["🔑 Entrar", "🔓 Esqueci minha senha"], horizontal=True, label_visibility="collapsed")

            if tela == "🔑 Entrar":
                senha = st.text_input("Senha master", type="password")
                if st.button("Entrar", use_container_width=True, type="primary"):
                    if senha == ADMIN_SENHA:
                        st.session_state["admin_ok"] = True
                        st.query_params["s"] = SESSAO_ADMIN_TOKEN
                        st.rerun()
                    else:
                        st.error("Senha incorreta.")

            else:
                st.info(f"Um link de redefinição será enviado para **{ADMIN_EMAIL}**")
                if st.button("📧 Enviar link de recuperação", use_container_width=True, type="primary"):
                    try:
                        token = criar_token("admin", "master")
                        link  = f"{APP_URL_ADMIN}?token={token}"
                        html  = f"""
                        <h2>DocCorretor IA — Recuperação de Senha</h2>
                        <p>Clique no link abaixo para redefinir sua senha master.<br>
                        O link expira em <strong>30 minutos</strong>.</p>
                        <a href="{link}" style="background:#1976d2;color:#fff;padding:12px 24px;border-radius:6px;text-decoration:none;font-size:16px;">
                        🔑 Redefinir Senha</a>
                        <p style="color:#888;font-size:12px;">Se não solicitou, ignore este email.</p>
                        """
                        enviar_email_recuperacao(ADMIN_EMAIL, "DocCorretor IA — Recuperação de Senha Master", html)
                        st.success(f"✅ Link enviado para {ADMIN_EMAIL}! Verifique sua caixa de entrada.")
                    except Exception as e:
                        st.error(f"❌ Erro ao enviar email: {e}")
        st.stop()

check_admin()

# ══════════════════════════════════════════════════════
# CABEÇALHO
# ══════════════════════════════════════════════════════

col_titulo, col_sair = st.columns([5,1])
with col_titulo:
    st.markdown("# 🛡️ Painel Admin — DocCorretor IA")
with col_sair:
    st.write("")
    if st.button("🚪 Sair", use_container_width=True):
        st.session_state["admin_ok"] = False
        st.query_params.clear()
        st.rerun()

st.divider()

# ── Auto-refresh a cada 30 segundos ──
import streamlit.components.v1 as components
components.html("<script>setTimeout(function(){window.location.reload();}, 30000);</script>", height=0)

# ── Dados sempre frescos do banco ──
clientes_db   = sb_get("clientes",   "select=*")
pagamentos_db = sb_get("pagamentos", "select=*")
usos_db       = sb_get("usos",       "select=*")
acessos_db    = sb_get("acessos",    "select=*")

dados_globais = {
    "clientes":   clientes_db,
    "pagamentos": pagamentos_db,
    "usos":       usos_db,
    "acessos":    acessos_db,
}

# ══════════════════════════════════════════════════════
# ABAS
# ══════════════════════════════════════════════════════

aba1, aba2, aba3, aba4, aba5 = st.tabs([
    "📊 Dashboard",
    "👥 Clientes",
    "➕ Cadastrar",
    "💰 Pagamentos",
    "📈 Métricas de Uso"
])

# ══════════════════════════════════════════════════════
# ABA 1 — DASHBOARD
# ══════════════════════════════════════════════════════

with aba1:
    st.subheader("📊 Visão Geral do Negócio")

    clientes   = dados_globais["clientes"]
    pagamentos = dados_globais["pagamentos"]
    usos       = dados_globais["usos"]
    acessos    = dados_globais["acessos"]

    hoje = date.today()

    # Métricas principais
    total       = len(clientes)
    ativos      = sum(1 for c in clientes if c.get("ativo") and date.fromisoformat(c["data_vencimento"]) >= hoje)
    vencidos    = sum(1 for c in clientes if date.fromisoformat(c["data_vencimento"]) < hoje)
    inativos    = sum(1 for c in clientes if not c.get("ativo"))
    imobs       = sum(1 for c in clientes if c.get("tipo") == "imobiliaria")
    corretores  = sum(1 for c in clientes if c.get("tipo") == "corretor")

    faturamento = sum(float(p.get("valor", 0) or 0) for p in pagamentos if p.get("status") == "pago")
    pendente    = sum(float(p.get("valor", 0) or 0) for p in pagamentos if p.get("status") == "pendente")

    # Este mês
    mes_atual = hoje.strftime("%Y-%m")
    fat_mes   = sum(float(p.get("valor", 0) or 0) for p in pagamentos
                    if p.get("status") == "pago" and (p.get("pago_em","") or "")[:7] == mes_atual)
    usos_mes  = sum(1 for u in usos if (u.get("usado_em","") or "")[:7] == mes_atual)

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("👥 Clientes Ativos",   ativos)
    c2.metric("🚨 Vencidos/Inativos", vencidos + inativos)
    c3.metric("💰 Faturamento Total", f"R$ {faturamento:,.2f}")
    c4.metric("📅 Receita Este Mês",  f"R$ {fat_mes:,.2f}")

    st.divider()

    c5,c6,c7,c8 = st.columns(4)
    c5.metric("🏢 Imobiliárias",          imobs)
    c6.metric("👤 Corretores Indep.",      corretores)
    c7.metric("📄 Dossiês Este Mês",       usos_mes)
    c8.metric("⏳ Receita Pendente",       f"R$ {pendente:,.2f}")

    st.divider()

    # Clientes prestes a vencer (próximos 10 dias)
    prox_vencer = [
        c for c in clientes
        if c.get("ativo") and 0 <= (date.fromisoformat(c["data_vencimento"]) - hoje).days <= 10
    ]
    if prox_vencer:
        st.warning(f"⚠️ {len(prox_vencer)} cliente(s) vencem nos próximos 10 dias!")
        for c in prox_vencer:
            dias = (date.fromisoformat(c["data_vencimento"]) - hoje).days
            st.markdown(f"- **{c['nome']}** ({c['login']}) — vence em **{dias} dia(s)** — {c['plano']}")
        st.divider()

    # Últimos acessos
    st.subheader("🕐 Últimos Acessos")
    acs = sorted(dados_globais["acessos"], key=lambda x: x.get("acessado_em",""), reverse=True)[:10]
    if acs:
        for a in acs[:10]:
            dt = (a.get("acessado_em","") or "")[:16].replace("T"," ")
            st.markdown(f"- `{dt}` — **{a.get('cliente_nome','')}** ({a.get('cliente_login','')})")
    else:
        st.info("Nenhum acesso registrado ainda.")

# ══════════════════════════════════════════════════════
# ABA 2 — CLIENTES
# ══════════════════════════════════════════════════════

with aba2:
    st.subheader("👥 Gerenciar Clientes")

    clientes = dados_globais["clientes"]
    hoje = date.today()

    # Filtros
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        filtro_tipo   = st.selectbox("Tipo", ["Todos","imobiliaria","corretor"])
    with col_f2:
        filtro_status = st.selectbox("Status", ["Todos","Ativo","Vencido","Inativo"])
    with col_f3:
        filtro_plano  = st.selectbox("Plano", ["Todos","mensal","semestral","anual"])

    # Aplica filtros
    lista = clientes
    if filtro_tipo   != "Todos": lista = [c for c in lista if c.get("tipo")  == filtro_tipo]
    if filtro_plano  != "Todos": lista = [c for c in lista if c.get("plano") == filtro_plano]
    if filtro_status == "Ativo":   lista = [c for c in lista if c.get("ativo") and date.fromisoformat(c["data_vencimento"]) >= hoje]
    if filtro_status == "Vencido": lista = [c for c in lista if date.fromisoformat(c["data_vencimento"]) < hoje]
    if filtro_status == "Inativo": lista = [c for c in lista if not c.get("ativo")]

    st.caption(f"{len(lista)} cliente(s) encontrado(s)")
    st.divider()

    for c in lista:
        venc  = date.fromisoformat(c["data_vencimento"])
        dias  = (venc - hoje).days
        ativo = c.get("ativo") and venc >= hoje

        if ativo and dias <= 5:   icone = "🟡"
        elif ativo:               icone = "🟢"
        else:                     icone = "🔴"

        tipo_label = "🏢 Imobiliária" if c.get("tipo") == "imobiliaria" else "👤 Corretor"

        with st.expander(f"{icone} {c['nome']} | {tipo_label} | {c['plano'].capitalize()} | Login: {c['login']}"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Responsável:** {c.get('responsavel','—')}")
                st.markdown(f"**Email:** {c.get('email','—')}")
                st.markdown(f"**Telefone:** {c.get('telefone','—')}")
                st.markdown(f"**CPF/CNPJ:** {c.get('cnpj_cpf','—')}")
                st.markdown(f"**Gmail remetente:** {c.get('gmail_remetente','—')}")
            with col2:
                st.markdown(f"**Plano:** {c['plano'].capitalize()} — R$ {c.get('valor_plano',0):.2f}")
                st.markdown(f"**Início:** {c['data_inicio']}")
                st.markdown(f"**Vencimento:** {c['data_vencimento']}")
                status_txt = f"✅ Ativo ({dias} dias restantes)" if ativo else f"❌ {'Vencido' if venc < hoje else 'Inativo'}"
                st.markdown(f"**Status:** {status_txt}")
                st.markdown(f"**Obs:** {c.get('observacoes','—')}")

            st.divider()
            ca, cb, cc, cd = st.columns(4)

            with ca:
                novo_plano = st.selectbox("Renovar plano", ["mensal","semestral","anual"], key=f"rp_{c['id']}")
                if st.button("🔄 Renovar", key=f"renovar_{c['id']}"):
                    nova_venc = calcular_vencimento(novo_plano)
                    ok = sb_patch("clientes", f"id=eq.{c['id']}", {
                        "plano": novo_plano,
                        "valor_plano": VALORES_PLANO[novo_plano],
                        "data_vencimento": str(nova_venc),
                        "ativo": True,
                        "atualizado_em": datetime.now().isoformat()
                    })
                    if ok:
                        sb_post("pagamentos", {
                            "cliente_id": c['id'],
                            "cliente_nome": c['nome'],
                            "plano": novo_plano,
                            "valor": VALORES_PLANO[novo_plano],
                            "status": "pago",
                            "referencia": f"Renovação {novo_plano} — {date.today()}"
                        })
                        st.success("✅ Renovado!")
                        time.sleep(1); st.rerun()

            with cb:
                nova_senha = st.text_input("Nova senha", key=f"ns_{c['id']}", placeholder="deixe vazio para não alterar")
                if st.button("🔑 Alterar senha", key=f"senha_{c['id']}"):
                    if nova_senha:
                        sb_patch("clientes", f"id=eq.{c['id']}", {"senha": nova_senha})
                        st.success("✅ Senha alterada!")
                        time.sleep(1); st.rerun()

            with cc:
                if c.get("ativo"):
                    if st.button("⛔ Bloquear", key=f"bloquear_{c['id']}"):
                        sb_patch("clientes", f"id=eq.{c['id']}", {"ativo": False})
                        st.warning("Cliente bloqueado.")
                        time.sleep(1); st.rerun()
                else:
                    if st.button("✅ Reativar", key=f"reativar_{c['id']}"):
                        nova_venc = calcular_vencimento(c['plano'])
                        sb_patch("clientes", f"id=eq.{c['id']}", {
                            "ativo": True,
                            "data_vencimento": str(nova_venc)
                        })
                        st.success("Cliente reativado!")
                        time.sleep(1); st.rerun()

            with cd:
                if st.button("🗑️ Excluir", key=f"excluir_{c['id']}"):
                    # Registra estorno para subtrair do faturamento
                    sb_post("pagamentos", {
                        "cliente_id": c['id'],
                        "cliente_nome": c['nome'],
                        "plano": c.get('plano',''),
                        "valor": -float(c.get('valor_plano', 0)),
                        "status": "cancelado",
                        "referencia": f"Exclusão do cliente — {date.today()}"
                    })
                    sb_delete("clientes", f"id=eq.{c['id']}")
                    st.error(f"Cliente {c['nome']} excluído e faturamento atualizado.")
                    time.sleep(1); st.rerun()

# ══════════════════════════════════════════════════════
# ABA 3 — CADASTRAR CLIENTE
# ══════════════════════════════════════════════════════

with aba3:
    st.subheader("➕ Cadastrar Novo Cliente")

    with st.form("form_cadastro"):
        col1, col2 = st.columns(2)
        with col1:
            tipo        = st.selectbox("Tipo de cliente *", ["imobiliaria", "corretor"],
                                       format_func=lambda x: "🏢 Imobiliária" if x=="imobiliaria" else "👤 Corretor Independente")
            nome        = st.text_input("Nome da empresa/corretor *")
            responsavel = st.text_input("Nome do responsável")
            email       = st.text_input("Email *")
            telefone    = st.text_input("Telefone")
            cnpj_cpf    = st.text_input("CNPJ / CPF")
        with col2:
            login       = st.text_input("Login de acesso * (único)")
            senha       = st.text_input("Senha de acesso *", type="password")
            plano       = st.selectbox("Plano *", ["mensal","semestral","anual"],
                                       format_func=lambda x: f"{x.capitalize()} — R$ {VALORES_PLANO[x]:.2f}")
            valor_custom = st.number_input("Valor personalizado (R$)", min_value=0.0,
                                           value=float(VALORES_PLANO[plano]), step=10.0)
            gmail_rem   = st.text_input("Gmail remetente do cliente (opcional)")
            gmail_senha = st.text_input("Senha de app Gmail (opcional)", type="password")
            obs         = st.text_input("Observações")

        st.divider()
        submitted = st.form_submit_button("✅ Cadastrar Cliente", type="primary", use_container_width=True)

        if submitted:
            erros = []
            if not nome:    erros.append("Nome obrigatório")
            if not email:   erros.append("Email obrigatório")
            if not login:   erros.append("Login obrigatório")
            if not senha:   erros.append("Senha obrigatória")

            if erros:
                for e in erros: st.error(e)
            else:
                venc = calcular_vencimento(plano)
                ok, resp = sb_post("clientes", {
                    "nome": nome,
                    "tipo": tipo,
                    "responsavel": responsavel,
                    "email": email,
                    "telefone": telefone,
                    "cnpj_cpf": cnpj_cpf,
                    "login": login,
                    "senha": senha,
                    "plano": plano,
                    "valor_plano": valor_custom,
                    "data_inicio": str(date.today()),
                    "data_vencimento": str(venc),
                    "ativo": True,
                    "gmail_remetente": gmail_rem,
                    "gmail_senha_app": gmail_senha,
                    "observacoes": obs
                })
                if ok:
                    cliente_id = resp[0]["id"] if isinstance(resp, list) else resp.get("id")
                    sb_post("pagamentos", {
                        "cliente_id": cliente_id,
                        "cliente_nome": nome,
                        "plano": plano,
                        "valor": valor_custom,
                        "status": "pago",
                        "referencia": f"Cadastro inicial — {date.today()}"
                    })
                    st.success(f"✅ Cliente **{nome}** cadastrado! Vencimento: {venc}")
                    st.info(f"🔑 Login: `{login}` | Senha: `{senha}`")
                    time.sleep(2)
                    st.rerun()
                else:
                    msg = str(resp)
                    if "duplicate" in msg.lower():
                        st.error("❌ Login ou email já cadastrado.")
                    else:
                        st.error(f"❌ Erro: {msg}")

# ══════════════════════════════════════════════════════
# ABA 4 — PAGAMENTOS / FATURAMENTO
# ══════════════════════════════════════════════════════

with aba4:
    st.subheader("💰 Faturamento e Pagamentos")

    pagamentos = dados_globais["pagamentos"]
    hoje = date.today()
    mes_atual = hoje.strftime("%Y-%m")

    fat_total  = sum(float(p.get("valor",0) or 0) for p in pagamentos if p.get("status")=="pago")
    fat_mes    = sum(float(p.get("valor",0) or 0) for p in pagamentos if p.get("status")=="pago" and (p.get("pago_em","") or "")[:7]==mes_atual)
    pendente   = sum(float(p.get("valor",0) or 0) for p in pagamentos if p.get("status")=="pendente")
    cancelado  = sum(float(p.get("valor",0) or 0) for p in pagamentos if p.get("status")=="cancelado")

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("💰 Total Recebido",   f"R$ {fat_total:,.2f}")
    c2.metric("📅 Receita do Mês",   f"R$ {fat_mes:,.2f}")
    c3.metric("⏳ Pendente",          f"R$ {pendente:,.2f}")
    c4.metric("❌ Cancelado",         f"R$ {cancelado:,.2f}")

    st.divider()

    # Faturamento por plano
    st.markdown("**Receita por plano:**")
    for plano in ["mensal","semestral","anual"]:
        val = sum(float(p.get("valor",0) or 0) for p in pagamentos if p.get("status")=="pago" and p.get("plano")==plano)
        qtd = sum(1 for p in pagamentos if p.get("status")=="pago" and p.get("plano")==plano)
        if qtd:
            st.markdown(f"- **{plano.capitalize()}:** {qtd} pagamento(s) — R$ {val:,.2f}")

    st.divider()

    # Adicionar pagamento manual
    with st.expander("➕ Registrar pagamento manual"):
        clientes_lista = dados_globais["clientes"]
        if clientes_lista:
            nomes_map = {c["nome"]: c["id"] for c in clientes_lista}
            cl_sel    = st.selectbox("Cliente", list(nomes_map.keys()))
            pl_sel    = st.selectbox("Plano", ["mensal","semestral","anual"])
            vl_sel    = st.number_input("Valor (R$)", min_value=0.0, value=float(VALORES_PLANO[pl_sel]), step=10.0)
            st_sel    = st.selectbox("Status", ["pago","pendente","cancelado"])
            ref_sel   = st.text_input("Referência", placeholder="Ex: Renovação março 2026")
            if st.button("💾 Registrar pagamento"):
                sb_post("pagamentos", {
                    "cliente_id": nomes_map[cl_sel],
                    "cliente_nome": cl_sel,
                    "plano": pl_sel,
                    "valor": vl_sel,
                    "status": st_sel,
                    "referencia": ref_sel
                })
                st.success("✅ Pagamento registrado!")
                time.sleep(1); st.rerun()

    st.divider()
    st.markdown("**Histórico de pagamentos:**")
    for p in pagamentos[:30]:
        dt = (p.get("pago_em","") or "")[:10]
        status_icon = "✅" if p.get("status")=="pago" else ("⏳" if p.get("status")=="pendente" else "❌")
        st.markdown(f"{status_icon} `{dt}` — **{p.get('cliente_nome','')}** — {p.get('plano','').capitalize()} — R$ {p.get('valor',0):.2f} — {p.get('referencia','')}")

# ══════════════════════════════════════════════════════
# ABA 5 — MÉTRICAS DE USO
# ══════════════════════════════════════════════════════

with aba5:
    st.subheader("📈 Métricas de Uso do Sistema")

    usos    = dados_globais["usos"]
    acessos = dados_globais["acessos"]
    hoje    = date.today()
    mes_atual = hoje.strftime("%Y-%m")

    total_usos    = len(usos)
    usos_mes      = sum(1 for u in usos if (u.get("usado_em","") or "")[:7] == mes_atual)
    emails_env    = sum(1 for u in usos if u.get("email_enviado"))
    total_acessos = len(acessos)
    acessos_mes   = sum(1 for a in acessos if (a.get("acessado_em","") or "")[:7] == mes_atual)

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("📄 Dossiês Gerados",     total_usos)
    c2.metric("📄 Dossiês Este Mês",    usos_mes)
    c3.metric("📧 Emails Enviados",     emails_env)
    c4.metric("🔑 Acessos Totais",      total_acessos)
    c5.metric("🔑 Acessos Este Mês",    acessos_mes)

    st.divider()

    # Ranking de uso por cliente
    st.markdown("**🏆 Clientes que mais usam o sistema:**")
    uso_por_cliente = {}
    for u in usos:
        nome = u.get("cliente_nome","—")
        uso_por_cliente[nome] = uso_por_cliente.get(nome, 0) + 1
    ranking = sorted(uso_por_cliente.items(), key=lambda x: x[1], reverse=True)
    for i, (nome, qtd) in enumerate(ranking[:10], 1):
        barra = "█" * min(qtd, 20)
        st.markdown(f"{i}. **{nome}** — {qtd} dossiê(s) `{barra}`")

    st.divider()

    # Clientes que nunca usaram
    clientes_uso = {u.get("cliente_login") for u in usos}
    clientes_todos = dados_globais["clientes"]
    nunca_usaram = [c for c in clientes_todos if c.get("login") not in clientes_uso and c.get("ativo")]
    if nunca_usaram:
        st.markdown(f"**😴 Clientes ativos que nunca geraram um dossiê ({len(nunca_usaram)}):**")
        for c in nunca_usaram:
            st.markdown(f"- {c.get('nome','')} (`{c.get('login','')}`)")
    else:
        st.success("🎉 Todos os clientes ativos já usaram o sistema!")

    st.divider()

    # Últimos usos
    st.markdown("**📋 Últimos dossiês gerados:**")
    for u in usos[:20]:
        dt     = (u.get("usado_em","") or "")[:16].replace("T"," ")
        email  = "📧" if u.get("email_enviado") else ""
        arqs   = u.get("qtd_arquivos", 0)
        st.markdown(f"- `{dt}` — **{u.get('cliente_nome','')}** — {arqs} arquivo(s) {email}")
