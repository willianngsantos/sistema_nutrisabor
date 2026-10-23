"""
Lançamentos diários de quantidades por cliente.

Antes, o controle de "quantos por dia" ficava fora do sistema e a fatura
recebia só o total do período, digitado à mão. Aqui:

- Quantidade padrão por produto e dia da semana: só SUGERE o número de cada
  dia. Mudar o padrão não altera dias já lançados (cada dia guarda o seu).
- Lançamento diário: o que foi efetivamente servido. É a referência da
  fatura — dia sem lançamento não entra na soma. Feriado = dia lançado com 0.
- A fatura busca a soma dos dias lançados no período (botão "Preencher com
  lançamentos"), sem listar os dias.

Produtos considerados: os da tabela de preços individual do cliente.
Acesso: só admin.
"""
from calendar import monthrange
from datetime import date, datetime, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user

from database import get_db_connection
from utils.permissions import admin_only
from utils.audit import log_action

lancamentos_bp = Blueprint('lancamentos', __name__)

DIAS_ABREV = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']   # = date.weekday()
DOMINGO = 6


# ── Helpers ──────────────────────────────────────────────────────────────────
def _quinzena(ref):
    """(início, fim) da quinzena que contém a data: 1–15 ou 16–fim do mês,
    o mesmo corte do faturamento."""
    if ref.day <= 15:
        return ref.replace(day=1), ref.replace(day=15)
    return ref.replace(day=16), ref.replace(day=monthrange(ref.year, ref.month)[1])


def _data(txt, padrao=None):
    try:
        return datetime.strptime((txt or '').strip(), '%Y-%m-%d').date()
    except ValueError:
        return padrao


def _qtd(valor):
    """Quantidade digitada → inteiro >= 0 (vazio vira 0)."""
    try:
        return max(0, int(str(valor or '').strip() or 0))
    except ValueError:
        return 0


def _cliente(cur, id_cliente):
    cur.execute("SELECT id, nome_empresa, apelido FROM clientes WHERE id = %s", (id_cliente,))
    return cur.fetchone()


def _produtos(cur, id_cliente, inicio=None, fim=None):
    """Produtos da tabela de preços individual do cliente (preço > 0) e, se for
    passado um período, também os que já têm lançamento nele — assim um item
    retirado da tabela não some do histórico."""
    params = [id_cliente]
    extra = ""
    if inicio and fim:
        extra = """ OR p.id IN (SELECT id_produto FROM lancamentos_diarios
                                WHERE id_cliente = %s AND data BETWEEN %s AND %s)"""
        params += [id_cliente, inicio, fim]
    cur.execute(f"""
        SELECT p.id, p.nome FROM produtos p
        WHERE p.id IN (SELECT id_produto FROM tabela_precos
                       WHERE id_cliente = %s AND preco_venda > 0){extra}
        ORDER BY p.nome
    """, params)
    return cur.fetchall()


def _padrao(cur, id_cliente):
    cur.execute("SELECT id_produto, dia_semana, quantidade FROM qtd_padrao_cliente "
                "WHERE id_cliente = %s", (id_cliente,))
    return {(r['id_produto'], r['dia_semana']): r['quantidade'] for r in cur.fetchall()}


def _nome(cliente):
    return cliente['apelido'] or cliente['nome_empresa']


# ── Quantidades padrão ───────────────────────────────────────────────────────
@lancamentos_bp.route('/lancamentos/<int:id_cliente>/padrao', methods=['GET', 'POST'])
@login_required
@admin_only
def padrao(id_cliente):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cliente = _cliente(cur, id_cliente)
    if not cliente:
        flash("Cliente não encontrado.", "warning")
        return redirect(url_for('cadastros.clientes'))
    produtos = _produtos(cur, id_cliente)

    if request.method == 'POST':
        resumo = []
        for p in produtos:
            qtds = [_qtd(request.form.get(f"q_{p['id']}_{d}")) for d in range(7)]
            for d, q in enumerate(qtds):
                cur.execute("""
                    INSERT INTO qtd_padrao_cliente (id_cliente, id_produto, dia_semana, quantidade)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE quantidade = %s
                """, (id_cliente, p['id'], d, q, q))
            resumo.append(f"{p['nome']} {'/'.join(map(str, qtds))}")
        conn.commit()
        log_action('update', entity_type='qtd_padrao_cliente', entity_id=id_cliente,
                   descricao=f"Quantidades padrão de '{_nome(cliente)}' (seg..dom): " + "; ".join(resumo))
        flash("Quantidades padrão salvas. Elas só sugerem os números — dias já lançados não mudam.", "success")
        return redirect(url_for('lancamentos.lancamentos', id_cliente=id_cliente))

    return render_template('lancamentos_padrao.html', cliente=cliente, produtos=produtos,
                           padrao=_padrao(cur, id_cliente), dias=DIAS_ABREV)


# ── Lançamentos da quinzena ──────────────────────────────────────────────────
@lancamentos_bp.route('/lancamentos/<int:id_cliente>')
@login_required
@admin_only
def lancamentos(id_cliente):
    hoje = date.today()
    inicio, fim = _quinzena(_data(request.args.get('ref'), hoje))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cliente = _cliente(cur, id_cliente)
    if not cliente:
        flash("Cliente não encontrado.", "warning")
        return redirect(url_for('cadastros.clientes'))

    produtos = _produtos(cur, id_cliente, inicio, fim)
    padrao = _padrao(cur, id_cliente)

    cur.execute("""
        SELECT id_produto, data, quantidade FROM lancamentos_diarios
        WHERE id_cliente = %s AND data BETWEEN %s AND %s
    """, (id_cliente, inicio, fim))
    lancado = {}
    for r in cur.fetchall():
        lancado.setdefault(r['data'], {})[r['id_produto']] = r['quantidade']

    # Domingo só aparece se houver padrão para domingo ou algo já lançado nele
    usa_domingo = any(padrao.get((p['id'], DOMINGO), 0) for p in produtos)

    dias = []
    d = inicio
    while d <= fim:
        ja = d in lancado
        if d.weekday() != DOMINGO or ja or usa_domingo:
            if ja:
                qtds = {p['id']: lancado[d].get(p['id'], 0) for p in produtos}
            else:
                qtds = {p['id']: padrao.get((p['id'], d.weekday()), 0) for p in produtos}
            dias.append({
                'iso': d.isoformat(),
                'rotulo': f"{DIAS_ABREV[d.weekday()]} {d:%d/%m}",
                'lancado': ja,
                'sem_servico': ja and not any(qtds.values()),
                'futuro': d > hoje,
                'hoje': d == hoje,
                'qtds': qtds,
            })
        d += timedelta(days=1)

    totais = {p['id']: sum(v.get(p['id'], 0) for v in lancado.values()) for p in produtos}

    return render_template(
        'lancamentos.html',
        cliente=cliente, produtos=produtos, dias=dias, totais=totais,
        inicio=inicio, fim=fim,
        ref_anterior=(inicio - timedelta(days=1)).isoformat(),
        ref_proxima=(fim + timedelta(days=1)).isoformat(),
        pendentes=sum(1 for x in dias if not x['lancado'] and not x['futuro']),
        dias_lancados=len(lancado),
        tem_padrao=any(padrao.values()),
    )


@lancamentos_bp.route('/lancamentos/<int:id_cliente>/salvar', methods=['POST'])
@login_required
@admin_only
def salvar(id_cliente):
    acao = (request.form.get('acao') or '').strip()
    inicio = _data(request.form.get('inicio'))
    fim = _data(request.form.get('fim'))
    voltar = redirect(url_for('lancamentos.lancamentos', id_cliente=id_cliente,
                              ref=inicio.isoformat() if inicio else None))
    if not inicio or not fim:
        flash("Período inválido.", "danger")
        return voltar

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cliente = _cliente(cur, id_cliente)
    if not cliente:
        flash("Cliente não encontrado.", "warning")
        return redirect(url_for('cadastros.clientes'))
    produtos = _produtos(cur, id_cliente, inicio, fim)

    tipo, _, txt = acao.partition(':')
    zerar = False

    if tipo in ('dia', 'feriado', 'limpar'):
        dia = _data(txt)
        if not dia or not (inicio <= dia <= fim):
            flash("Dia inválido.", "danger")
            return voltar
        if tipo == 'limpar':
            cur.execute("DELETE FROM lancamentos_diarios WHERE id_cliente = %s AND data = %s",
                        (id_cliente, dia))
            conn.commit()
            log_action('delete', entity_type='lancamento_diario', entity_id=id_cliente,
                       descricao=f"Desfez o lançamento de {dia:%d/%m/%Y} de '{_nome(cliente)}'")
            flash(f"Lançamento de {dia:%d/%m} desfeito — o dia voltou a ser só sugestão.", "info")
            return voltar
        datas, zerar = [dia], (tipo == 'feriado')

    elif tipo == 'sugestoes':
        # Todos os dias ainda não lançados do período, até hoje, que estão na
        # tela — com os números como estão na tela (o usuário pode ter ajustado).
        cur.execute("SELECT DISTINCT data FROM lancamentos_diarios "
                    "WHERE id_cliente = %s AND data BETWEEN %s AND %s", (id_cliente, inicio, fim))
        ja = {r['data'] for r in cur.fetchall()}
        limite = min(fim, date.today())
        datas, d = [], inicio
        while d <= limite:
            if d not in ja and produtos and request.form.get(f"q_{d.isoformat()}_{produtos[0]['id']}") is not None:
                datas.append(d)
            d += timedelta(days=1)
        if not datas:
            flash("Não há dias pendentes até hoje nesta quinzena.", "info")
            return voltar
    else:
        flash("Ação inválida.", "danger")
        return voltar

    for dia in datas:
        for p in produtos:
            q = 0 if zerar else _qtd(request.form.get(f"q_{dia.isoformat()}_{p['id']}"))
            cur.execute("""
                INSERT INTO lancamentos_diarios (id_cliente, id_produto, data, quantidade, lancado_por)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE quantidade = %s, lancado_por = %s
            """, (id_cliente, p['id'], dia, q, current_user.nome, q, current_user.nome))
    conn.commit()

    if zerar:
        msg = f"{datas[0]:%d/%m} lançado como feriado / sem serviço."
    elif len(datas) == 1:
        msg = f"{datas[0]:%d/%m} lançado."
    else:
        msg = f"{len(datas)} dias lançados ({datas[0]:%d/%m} a {datas[-1]:%d/%m})."
    log_action('update', entity_type='lancamento_diario', entity_id=id_cliente,
               descricao=f"Lançamentos de '{_nome(cliente)}': {msg}")
    flash(msg, "success")
    return voltar


# ── Totais para a fatura ─────────────────────────────────────────────────────
@lancamentos_bp.route('/lancamentos/<int:id_cliente>/totais')
@login_required
@admin_only
def totais(id_cliente):
    """Soma dos dias lançados no período, por produto. Devolve também quais
    produtos estão sob controle diário (têm padrão ou lançamento): a fatura só
    mexe nesses, para não zerar um item avulso lançado à mão (ex.: um bolo)."""
    inicio = _data(request.args.get('inicio'))
    fim = _data(request.args.get('fim'))
    if not inicio or not fim or fim < inicio:
        return jsonify({'erro': 'Período inválido.'}), 400

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id_produto, SUM(quantidade) AS total, COUNT(DISTINCT data) AS dias
        FROM lancamentos_diarios
        WHERE id_cliente = %s AND data BETWEEN %s AND %s
        GROUP BY id_produto
    """, (id_cliente, inicio, fim))
    somas = {r['id_produto']: int(r['total'] or 0) for r in cur.fetchall()}

    cur.execute("SELECT COUNT(DISTINCT data) AS n FROM lancamentos_diarios "
                "WHERE id_cliente = %s AND data BETWEEN %s AND %s", (id_cliente, inicio, fim))
    n_dias = cur.fetchone()['n']

    cur.execute("""
        SELECT DISTINCT id_produto FROM qtd_padrao_cliente
        WHERE id_cliente = %s AND quantidade > 0
    """, (id_cliente,))
    controlados = {r['id_produto'] for r in cur.fetchall()} | set(somas)

    return jsonify({
        'dias': n_dias,
        'totais': {str(pid): somas.get(pid, 0) for pid in sorted(controlados)},
    })
