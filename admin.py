import streamlit as st
import requests
import json
import smtplib
import secrets
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date, timedelta, datetime, timezone
import time

st.set_page_config(page_title="Admin — ImobFlow", page_icon="🛡️", layout="wide")

st.markdown("""
<style>
    #MainMenu { visibility: hidden !important; display: none !important; }
    header { visibility: hidden !important; display: none !important; }
    footer { visibility: hidden !important; display: none !important; }
    .stDeployButton { display: none !important; }
    [data-testid="stToolbar"] { display: none !important; }
    [data-testid="stDecoration"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

import streamlit.components.v1 as components
components.html("""
<script>
    function hideMenu() {
        const doc = window.parent.document;
        ['header','#MainMenu','footer','[data-testid="stToolbar"]','[data-testid="stDecoration"]',
         '.stDeployButton'].forEach(s =>
            doc.querySelectorAll(s).forEach(el => {
                el.style.setProperty('display','none','important');
            })
        );
    }
    hideMenu();
    new MutationObserver(hideMenu).observe(window.parent.document.body,{childList:true,subtree:true});
</script>
""", height=0)

SUPABASE_URL    = "https://ryvgqesflxbtqbdhspdy.supabase.co"
SUPABASE_KEY    = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJ5dmdxZXNmbHhidHFiZGhzcGR5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzIyOTIyMjMsImV4cCI6MjA4Nzg2ODIyM30.HhW3_bSQ8fZvY17XTwerhXdW7hF2uf3gKUSYm9ixkys"
ADMIN_SENHA     = "admin@docorretor2025"
ADMIN_EMAIL     = "compracertavip@gmail.com"
EMAIL_REMETENTE = "daniellaandrade1989@gmail.com"
EMAIL_SENHA_APP = "fpupijekoocowhcl"
APP_URL_ADMIN   = "https://docorretor-painel.streamlit.app"
APP_URL_CLIENTE = "https://doc-corretor-ia.streamlit.app"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}
# Headers sem Prefer — usado no PATCH para evitar erro 406 no Supabase
HEADERS_PATCH = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

PLANOS = {
    "free":      {"label": "🆓 Free — sem envio de email", "valor": 0.0,   "pro": False},
    "mensal":    {"label": "📅 Mensal — R$ 97,00",         "valor": 97.0,  "pro": True},
    "semestral": {"label": "📆 Semestral — R$ 497,00",     "valor": 497.0, "pro": True},
    "anual":     {"label": "🏆 Anual — R$ 897,00",         "valor": 897.0, "pro": True},
}
VALORES_PLANO = {k: v["valor"] for k,v in PLANOS.items()}

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
    return r.json() if r.status_code == 200 else []

def sb_post(tabela, dados):
    url = f"{SUPABASE_URL}/rest/v1/{tabela}"
    r = requests.post(url, headers=HEADERS, json=dados)
    return r.status_code in (200, 201), r.json()

def sb_patch(tabela, filtro, dados):
    """PATCH sem Prefer:return=representation — evita erro 406 no Supabase"""
    url = f"{SUPABASE_URL}/rest/v1/{tabela}?{filtro}"
    r = requests.patch(url, headers=HEADERS_PATCH, json=dados)
    return r.status_code in (200, 201, 204)

def sb_delete(tabela, filtro):
    url = f"{SUPABASE_URL}/rest/v1/{tabela}?{filtro}"
    r = requests.delete(url, headers=HEADERS)
    return r.status_code in (200, 204)

def calcular_vencimento(plano, inicio=None):
    d = inicio or date.today()
    if plano == "mensal":    return d + timedelta(days=30)
    if plano == "semestral": return d + timedelta(days=180)
    if plano == "anual":     return d + timedelta(days=365)
    if plano == "free":      return date.today() + timedelta(days=7)
    return d + timedelta(days=30)

def is_pro(plano):
    return PLANOS.get(plano, {}).get("pro", False)

def enviar_email_recuperacao(destinatario, assunto, corpo_html):
    msg = MIMEMultipart("alternative")
    msg["From"] = EMAIL_REMETENTE; msg["To"] = destinatario; msg["Subject"] = assunto
    msg.attach(MIMEText(corpo_html, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(EMAIL_REMETENTE, EMAIL_SENHA_APP)
        s.sendmail(EMAIL_REMETENTE, destinatario, msg.as_bytes())

def criar_token(tipo, referencia):
    token  = secrets.token_urlsafe(32)
    expira = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    sb_post("tokens_recuperacao", {"tipo": tipo, "referencia": referencia,
                                    "token": token, "usado": False, "expira_em": expira})
    return token

def validar_token(token):
    url = f"{SUPABASE_URL}/rest/v1/tokens_recuperacao?token=eq.{token}&usado=eq.false&select=*"
    r   = requests.get(url, headers=HEADERS)
    if r.status_code != 200: return None
    dados = r.json()
    if not dados: return None
    rec = dados[0]
    expira = datetime.fromisoformat(rec["expira_em"])
    if expira.tzinfo is None: expira = expira.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expira: return None
    return rec

def marcar_token_usado(token_id):
    sb_patch("tokens_recuperacao", f"id=eq.{token_id}", {"usado": True})

# ══ LOGIN ══
SESSAO_ADMIN_TOKEN = "sessao_admin_ativa_2025"

def check_admin():
    params    = st.query_params
    token_url = params.get("token", "")
    sessao    = params.get("s", "")

    if sessao == SESSAO_ADMIN_TOKEN and not st.session_state.get("admin_ok"):
        st.session_state["admin_ok"] = True

    if token_url and not st.session_state.get("admin_ok"):
        col1, col2, col3 = st.columns([1,1.2,1])
        with col2:
            st.markdown("## 🛡️ ImobFlow"); st.markdown("#### Redefinir senha master"); st.divider()
            rec = validar_token(token_url)
            if not rec or rec.get("tipo") != "admin":
                st.error("❌ Link inválido ou expirado."); st.stop()
            nova1 = st.text_input("Nova senha", type="password")
            nova2 = st.text_input("Confirme", type="password")
            if st.button("✅ Salvar", use_container_width=True, type="primary"):
                if not nova1 or len(nova1) < 6: st.error("Mínimo 6 caracteres.")
                elif nova1 != nova2: st.error("Senhas não coincidem.")
                else:
                    marcar_token_usado(rec["id"])
                    st.success("✅ Atualize ADMIN_SENHA no código:")
                    st.code(nova1)
        st.stop()

    if not st.session_state.get("admin_ok", False):
        col1, col2, col3 = st.columns([1,1.2,1])
        with col2:
            st.markdown("## 🛡️ ImobFlow"); st.markdown("#### Painel Administrador"); st.divider()
            tela = st.radio("", ["🔑 Entrar","🔓 Esqueci minha senha"], horizontal=True, label_visibility="collapsed")
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
                st.info(f"Link enviado para **{ADMIN_EMAIL}**")
                if st.button("📧 Enviar link", use_container_width=True, type="primary"):
                    try:
                        token = criar_token("admin", "master")
                        link  = f"{APP_URL_ADMIN}?token={token}"
                        html  = f'<h2>ImobFlow</h2><p>Redefina sua senha:</p><a href="{link}" style="background:#1976d2;color:#fff;padding:12px 24px;border-radius:6px;text-decoration:none;">🔑 Redefinir Senha</a>'
                        enviar_email_recuperacao(ADMIN_EMAIL, "ImobFlow — Recuperação Senha Master", html)
                        st.success("✅ Link enviado!")
                    except Exception as e:
                        st.error(f"❌ Erro: {e}")
        st.stop()

check_admin()

# ══ CABEÇALHO ══
col_titulo, col_sair = st.columns([5,1])
with col_titulo: st.markdown("# 🛡️ Painel Admin — ImobFlow")
with col_sair:
    st.write("")
    if st.button("🚪 Sair", use_container_width=True):
        st.session_state["admin_ok"] = False; st.query_params.clear(); st.rerun()
st.divider()

components.html("<script>setTimeout(function(){window.location.reload();}, 30000);</script>", height=0)

clientes_db   = sb_get("clientes",   "select=*")
pagamentos_db = sb_get("pagamentos", "select=*")
usos_db       = sb_get("usos",       "select=*")
acessos_db    = sb_get("acessos",    "select=*")
dados_globais = {"clientes": clientes_db, "pagamentos": pagamentos_db,
                 "usos": usos_db, "acessos": acessos_db}

aba1, aba2, aba3, aba4, aba5 = st.tabs([
    "📊 Dashboard","👥 Clientes","➕ Cadastrar","💰 Pagamentos","📈 Métricas de Uso"])

# ══ ABA 1 — DASHBOARD ══
with aba1:
    st.subheader("📊 Visão Geral do Negócio")
    clientes = dados_globais["clientes"]; pagamentos = dados_globais["pagamentos"]
    usos = dados_globais["usos"]; acessos = dados_globais["acessos"]
    hoje = date.today(); mes_atual = hoje.strftime("%Y-%m")

    total      = len(clientes)
    ativos     = sum(1 for c in clientes if c.get("ativo") and date.fromisoformat(c["data_vencimento"]) >= hoje)
    vencidos   = sum(1 for c in clientes if date.fromisoformat(c["data_vencimento"]) < hoje)
    inativos   = sum(1 for c in clientes if not c.get("ativo"))
    free_count = sum(1 for c in clientes if c.get("plano") == "free")
    pro_count  = sum(1 for c in clientes if is_pro(c.get("plano","")))
    imobs      = sum(1 for c in clientes if c.get("tipo") == "imobiliaria")
    corretores = sum(1 for c in clientes if c.get("tipo") == "corretor")

    faturamento = sum(float(p.get("valor",0) or 0) for p in pagamentos if p.get("status")=="pago")
    fat_mes     = sum(float(p.get("valor",0) or 0) for p in pagamentos
                      if p.get("status")=="pago" and (p.get("pago_em","") or "")[:7]==mes_atual)
    pendente    = sum(float(p.get("valor",0) or 0) for p in pagamentos if p.get("status")=="pendente")
    usos_mes    = sum(1 for u in usos if (u.get("usado_em","") or "")[:7]==mes_atual)

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("👥 Clientes Ativos",   ativos)
    c2.metric("🚨 Vencidos/Inativos", vencidos+inativos)
    c3.metric("💰 Faturamento Total", f"R$ {faturamento:,.2f}")
    c4.metric("📅 Receita Este Mês",  f"R$ {fat_mes:,.2f}")
    st.divider()
    c5,c6,c7,c8 = st.columns(4)
    c5.metric("🆓 Clientes Free",    free_count)
    c6.metric("⭐ Clientes PRO",     pro_count)
    c7.metric("📄 Dossiês Este Mês", usos_mes)
    c8.metric("⏳ Receita Pendente", f"R$ {pendente:,.2f}")
    st.divider()

    prox_vencer = [c for c in clientes if c.get("ativo") and c.get("plano") != "free"
                   and 0 <= (date.fromisoformat(c["data_vencimento"])-hoje).days <= 10]
    if prox_vencer:
        st.warning(f"⚠️ {len(prox_vencer)} cliente(s) PRO vencem nos próximos 10 dias!")
        for c in prox_vencer:
            dias = (date.fromisoformat(c["data_vencimento"])-hoje).days
            st.markdown(f"- **{c['nome']}** ({c['login']}) — vence em **{dias} dia(s)** — {c['plano']}")
        st.divider()

    st.subheader("🕐 Últimos Acessos")
    acs = sorted(dados_globais["acessos"], key=lambda x: x.get("acessado_em",""), reverse=True)[:10]
    for a in acs:
        dt = (a.get("acessado_em","") or "")[:16].replace("T"," ")
        plano_c = next((c.get("plano","") for c in clientes if c.get("login")==a.get("cliente_login")), "")
        badge = "⭐" if is_pro(plano_c) else "🆓"
        st.markdown(f"- `{dt}` — {badge} **{a.get('cliente_nome','')}** ({a.get('cliente_login','')})")
    if not acs: st.info("Nenhum acesso registrado ainda.")

# ══ ABA 2 — CLIENTES ══
with aba2:
    st.subheader("👥 Gerenciar Clientes")
    clientes = dados_globais["clientes"]; hoje = date.today()

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1: filtro_tipo   = st.selectbox("Tipo",   ["Todos","imobiliaria","corretor"])
    with col_f2: filtro_status = st.selectbox("Status", ["Todos","Ativo","Vencido","Inativo"])
    with col_f3: filtro_plano  = st.selectbox("Plano",  ["Todos","free","mensal","semestral","anual"])

    lista = clientes
    if filtro_tipo   != "Todos": lista = [c for c in lista if c.get("tipo")  == filtro_tipo]
    if filtro_plano  != "Todos": lista = [c for c in lista if c.get("plano") == filtro_plano]
    if filtro_status == "Ativo":   lista = [c for c in lista if c.get("ativo") and date.fromisoformat(c["data_vencimento"]) >= hoje]
    if filtro_status == "Vencido": lista = [c for c in lista if date.fromisoformat(c["data_vencimento"]) < hoje]
    if filtro_status == "Inativo": lista = [c for c in lista if not c.get("ativo")]

    st.caption(f"{len(lista)} cliente(s) encontrado(s)"); st.divider()

    for c in lista:
        venc  = date.fromisoformat(c["data_vencimento"])
        dias  = (venc - hoje).days
        ativo = c.get("ativo") and venc >= hoje
        plano_c = c.get("plano","")
        badge = "⭐ PRO" if is_pro(plano_c) else "🆓 Free"

        if ativo and dias <= 5: icone = "🟡"
        elif ativo:             icone = "🟢"
        else:                   icone = "🔴"
        tipo_label = "🏢 Imobiliária" if c.get("tipo")=="imobiliaria" else "👤 Corretor"

        with st.expander(f"{icone} {c['nome']} | {tipo_label} | {badge} | {plano_c.capitalize()} | Login: {c['login']}"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Responsável:** {c.get('responsavel','—')}")
                st.markdown(f"**Email:** {c.get('email','—')}")
                st.markdown(f"**Telefone:** {c.get('telefone','—')}")
                st.markdown(f"**CPF/CNPJ:** {c.get('cnpj_cpf','—')}")
                st.markdown(f"**Gmail remetente:** {c.get('gmail_remetente','—')}")
            with col2:
                st.markdown(f"**Plano:** {badge} — {plano_c.capitalize()} — R$ {c.get('valor_plano',0):.2f}")
                st.markdown(f"**Início:** {c['data_inicio']}")
                st.markdown(f"**Vencimento:** {c['data_vencimento']}")
                status_txt = f"✅ Ativo ({dias} dias restantes)" if ativo else f"❌ {'Vencido' if venc < hoje else 'Inativo'}"
                st.markdown(f"**Status:** {status_txt}")
                st.markdown(f"**Obs:** {c.get('observacoes','—')}")

            st.divider()
            ca, cb, cc, cd = st.columns(4)

            with ca:
                novo_plano = st.selectbox(
                    "Alterar plano", list(PLANOS.keys()),
                    format_func=lambda x: PLANOS[x]["label"],
                    key=f"rp_{c['id']}"
                )
                if st.button("🔄 Atualizar plano", key=f"renovar_{c['id']}"):
                    nova_venc = calcular_vencimento(novo_plano)
                    payload = {
                        "plano": novo_plano,
                        "valor_plano": VALORES_PLANO[novo_plano],
                        "data_vencimento": str(nova_venc),
                        "ativo": True,
                    }
                    ok = sb_patch("clientes", f"id=eq.{c['id']}", payload)
                    if ok:
                        # Registra pagamento só para planos pagos
                        if VALORES_PLANO[novo_plano] > 0:
                            sb_post("pagamentos", {
                                "cliente_id": c['id'], "cliente_nome": c['nome'],
                                "plano": novo_plano, "valor": VALORES_PLANO[novo_plano],
                                "status": "pago", "referencia": f"Plano {novo_plano} — {date.today()}"
                            })
                        badge_novo = "🆓 Free" if novo_plano == "free" else "⭐ PRO"
                        st.success(f"✅ Plano atualizado para {badge_novo} — {novo_plano.capitalize()}! Vence em: {nova_venc}")
                        time.sleep(1); st.rerun()
                    else:
                        st.error("❌ Falha ao atualizar. Tente novamente.")

            with cb:
                nova_senha = st.text_input("Nova senha", key=f"ns_{c['id']}", placeholder="deixe vazio para não alterar")
                if st.button("🔑 Alterar senha", key=f"senha_{c['id']}"):
                    if nova_senha:
                        ok = sb_patch("clientes", f"id=eq.{c['id']}", {"senha": nova_senha})
                        if ok: st.success("✅ Senha alterada!")
                        else: st.error("❌ Falha ao alterar senha.")
                        time.sleep(1); st.rerun()

            with cc:
                if c.get("ativo"):
                    if st.button("⛔ Bloquear", key=f"bloquear_{c['id']}"):
                        sb_patch("clientes", f"id=eq.{c['id']}", {"ativo": False})
                        st.warning("Cliente bloqueado."); time.sleep(1); st.rerun()
                else:
                    if st.button("✅ Reativar", key=f"reativar_{c['id']}"):
                        nova_venc = calcular_vencimento(c['plano'])
                        sb_patch("clientes", f"id=eq.{c['id']}", {"ativo": True, "data_vencimento": str(nova_venc)})
                        st.success("Cliente reativado!"); time.sleep(1); st.rerun()

            with cd:
                if st.button("🗑️ Excluir", key=f"excluir_{c['id']}"):
                    if VALORES_PLANO.get(c.get("plano",""), 0) > 0:
                        sb_post("pagamentos", {
                            "cliente_id": c['id'], "cliente_nome": c['nome'],
                            "plano": c.get('plano',''), "valor": -float(c.get('valor_plano',0)),
                            "status": "cancelado", "referencia": f"Exclusão — {date.today()}"
                        })
                    sb_delete("clientes", f"id=eq.{c['id']}")
                    st.error(f"Cliente {c['nome']} excluído."); time.sleep(1); st.rerun()

# ══ ABA 3 — CADASTRAR ══
with aba3:
    st.subheader("➕ Cadastrar Novo Cliente")
    with st.form("form_cadastro"):
        col1, col2 = st.columns(2)
        with col1:
            tipo        = st.selectbox("Tipo de cliente *", ["imobiliaria","corretor"],
                                       format_func=lambda x: "🏢 Imobiliária" if x=="imobiliaria" else "👤 Corretor Independente")
            nome        = st.text_input("Nome da empresa/corretor *")
            responsavel = st.text_input("Nome do responsável")
            email       = st.text_input("Email *")
            telefone    = st.text_input("Telefone")
            cnpj_cpf    = st.text_input("CNPJ / CPF")
        with col2:
            login       = st.text_input("Login de acesso * (único)")
            senha       = st.text_input("Senha de acesso *", type="password")
            plano       = st.selectbox("Plano *", list(PLANOS.keys()),
                                       format_func=lambda x: PLANOS[x]["label"])
            valor_custom = st.number_input("Valor personalizado (R$)", min_value=0.0,
                                           value=float(VALORES_PLANO[plano]), step=10.0)
            gmail_rem   = st.text_input("Gmail remetente do cliente (opcional)")
            gmail_senha = st.text_input("Senha de app Gmail (opcional)", type="password")
            obs         = st.text_input("Observações")

        st.divider()
        submitted = st.form_submit_button("✅ Cadastrar Cliente", type="primary", use_container_width=True)

        if submitted:
            erros = []
            if not nome:  erros.append("Nome obrigatório")
            if not email: erros.append("Email obrigatório")
            if not login: erros.append("Login obrigatório")
            if not senha: erros.append("Senha obrigatória")
            if erros:
                for e in erros: st.error(e)
            else:
                venc = calcular_vencimento(plano)
                ok, resp = sb_post("clientes", {
                    "nome": nome, "tipo": tipo, "responsavel": responsavel,
                    "email": email, "telefone": telefone, "cnpj_cpf": cnpj_cpf,
                    "login": login, "senha": senha, "plano": plano,
                    "valor_plano": valor_custom, "data_inicio": str(date.today()),
                    "data_vencimento": str(venc), "ativo": True,
                    "gmail_remetente": gmail_rem, "gmail_senha_app": gmail_senha, "observacoes": obs
                })
                if ok:
                    cliente_id = resp[0]["id"] if isinstance(resp, list) else resp.get("id")
                    if valor_custom > 0:
                        sb_post("pagamentos", {
                            "cliente_id": cliente_id, "cliente_nome": nome,
                            "plano": plano, "valor": valor_custom,
                            "status": "pago", "referencia": f"Cadastro inicial — {date.today()}"
                        })
                    tipo_badge = "🆓 Free" if plano == "free" else "⭐ PRO"
                    st.success(f"✅ Cliente **{nome}** cadastrado! Plano: {tipo_badge} | Vencimento: {venc}")
                    st.info(f"🔑 Login: `{login}` | Senha: `{senha}`")
                    time.sleep(2); st.rerun()
                else:
                    msg = str(resp)
                    if "duplicate" in msg.lower(): st.error("❌ Login ou email já cadastrado.")
                    else: st.error(f"❌ Erro: {msg}")

# ══ ABA 4 — PAGAMENTOS ══
with aba4:
    st.subheader("💰 Faturamento e Pagamentos")
    pagamentos = dados_globais["pagamentos"]; hoje = date.today(); mes_atual = hoje.strftime("%Y-%m")

    fat_total = sum(float(p.get("valor",0) or 0) for p in pagamentos if p.get("status")=="pago")
    fat_mes   = sum(float(p.get("valor",0) or 0) for p in pagamentos
                    if p.get("status")=="pago" and (p.get("pago_em","") or "")[:7]==mes_atual)
    pendente  = sum(float(p.get("valor",0) or 0) for p in pagamentos if p.get("status")=="pendente")

    c1,c2,c3 = st.columns(3)
    c1.metric("💰 Total Recebido", f"R$ {fat_total:,.2f}")
    c2.metric("📅 Receita do Mês", f"R$ {fat_mes:,.2f}")
    c3.metric("⏳ Pendente",        f"R$ {pendente:,.2f}")
    st.divider()

    st.markdown("**Receita por plano:**")
    for plano in ["mensal","semestral","anual"]:
        val = sum(float(p.get("valor",0) or 0) for p in pagamentos if p.get("status")=="pago" and p.get("plano")==plano)
        qtd = sum(1 for p in pagamentos if p.get("status")=="pago" and p.get("plano")==plano)
        if qtd: st.markdown(f"- **{plano.capitalize()}:** {qtd} pagamento(s) — R$ {val:,.2f}")
    st.divider()

    with st.expander("➕ Registrar pagamento manual"):
        clientes_lista = dados_globais["clientes"]
        if clientes_lista:
            nomes_map = {c["nome"]: c["id"] for c in clientes_lista}
            cl_sel  = st.selectbox("Cliente", list(nomes_map.keys()))
            pl_sel  = st.selectbox("Plano", ["mensal","semestral","anual"])
            vl_sel  = st.number_input("Valor (R$)", min_value=0.0, value=float(VALORES_PLANO[pl_sel]), step=10.0)
            st_sel  = st.selectbox("Status", ["pago","pendente","cancelado"])
            ref_sel = st.text_input("Referência", placeholder="Ex: Renovação março 2026")
            if st.button("💾 Registrar pagamento"):
                sb_post("pagamentos", {"cliente_id": nomes_map[cl_sel], "cliente_nome": cl_sel,
                    "plano": pl_sel, "valor": vl_sel, "status": st_sel, "referencia": ref_sel})
                st.success("✅ Pagamento registrado!"); time.sleep(1); st.rerun()
    st.divider()

    st.markdown("**Histórico de pagamentos:**")
    for p in pagamentos[:30]:
        dt = (p.get("pago_em","") or "")[:10]
        icon = "✅" if p.get("status")=="pago" else ("⏳" if p.get("status")=="pendente" else "❌")
        st.markdown(f"{icon} `{dt}` — **{p.get('cliente_nome','')}** — {p.get('plano','').capitalize()} — R$ {p.get('valor',0):.2f} — {p.get('referencia','')}")

# ══ ABA 5 — MÉTRICAS ══
with aba5:
    st.subheader("📈 Métricas de Uso do Sistema")
    usos = dados_globais["usos"]; acessos = dados_globais["acessos"]
    hoje = date.today(); mes_atual = hoje.strftime("%Y-%m")

    total_usos    = len(usos)
    usos_mes      = sum(1 for u in usos if (u.get("usado_em","") or "")[:7]==mes_atual)
    emails_env    = sum(1 for u in usos if u.get("email_enviado"))
    total_acessos = len(acessos)
    acessos_mes   = sum(1 for a in acessos if (a.get("acessado_em","") or "")[:7]==mes_atual)

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("📄 Dossiês Gerados",  total_usos)
    c2.metric("📄 Dossiês Este Mês", usos_mes)
    c3.metric("📧 Emails Enviados",  emails_env)
    c4.metric("🔑 Acessos Totais",   total_acessos)
    c5.metric("🔑 Acessos Este Mês", acessos_mes)
    st.divider()

    st.markdown("**🏆 Clientes que mais usam:**")
    uso_por_cliente = {}
    for u in usos:
        nome = u.get("cliente_nome","—")
        uso_por_cliente[nome] = uso_por_cliente.get(nome,0) + 1
    for i,(nome,qtd) in enumerate(sorted(uso_por_cliente.items(), key=lambda x:x[1], reverse=True)[:10],1):
        st.markdown(f"{i}. **{nome}** — {qtd} dossiê(s) `{'█'*min(qtd,20)}`")
    st.divider()

    clientes_uso  = {u.get("cliente_login") for u in usos}
    nunca_usaram  = [c for c in dados_globais["clientes"] if c.get("login") not in clientes_uso and c.get("ativo")]
    if nunca_usaram:
        st.markdown(f"**😴 Nunca usaram ({len(nunca_usaram)}):**")
        for c in nunca_usaram:
            badge = "⭐" if is_pro(c.get("plano","")) else "🆓"
            st.markdown(f"- {badge} {c.get('nome','')} (`{c.get('login','')}`)")
    else:
        st.success("🎉 Todos os clientes ativos já usaram!")
    st.divider()

    st.markdown("**📋 Últimos dossiês:**")
    for u in usos[:20]:
        dt   = (u.get("usado_em","") or "")[:16].replace("T"," ")
        mail = "📧" if u.get("email_enviado") else ""
        st.markdown(f"- `{dt}` — **{u.get('cliente_nome','')}** — {u.get('qtd_arquivos',0)} arquivo(s) {mail}")
