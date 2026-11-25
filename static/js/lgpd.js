// LGPD — painel de conformidade, solicitações de titulares e incidentes
const TIPOS = {
    confirmacao: 'Confirmação de tratamento', acesso: 'Acesso aos dados', correcao: 'Correção de dados',
    anonimizacao: 'Anonimização/eliminação', portabilidade: 'Portabilidade',
    compartilhamento: 'Compartilhamento', revogacao: 'Revogação de consentimento', oposicao: 'Oposição',
};

function celula(tr, texto) {
    const td = document.createElement('td');
    td.textContent = texto ?? '';
    tr.appendChild(td);
    return td;
}

function fmtData(iso) {
    return iso ? new Date(iso).toLocaleDateString('pt-BR') : '';
}

async function carregarSolicitacoes() {
    const resp = await fetch('/api/lgpd/solicitacoes');
    if (!resp.ok) return;
    const tb = document.getElementById('tbSolicitacoes');
    tb.replaceChildren();
    for (const s of await resp.json()) {
        const tr = document.createElement('tr');
        celula(tr, s.titular_nome);
        celula(tr, TIPOS[s.tipo] || s.tipo);
        celula(tr, fmtData(s.prazo_em) + (s.atrasada ? ' ⚠️ atrasada' : ''));
        celula(tr, s.status);
        const acoes = document.createElement('td');
        if (s.status === 'aberta') {
            for (const [rotulo, status] of [['Atendida', 'atendida'], ['Negada', 'negada']]) {
                const b = document.createElement('button');
                b.className = 'btn btn-outline btn-sm';
                b.textContent = rotulo;
                b.onclick = () => resolverSolicitacao(s.id, status);
                acoes.appendChild(b);
            }
        }
        tr.appendChild(acoes);
        tb.appendChild(tr);
    }
}

async function resolverSolicitacao(id, status) {
    const resposta = prompt('Resposta ao titular (opcional):') ?? '';
    const resp = await fetch(`/api/lgpd/solicitacoes/${id}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status, resposta }),
    });
    if (resp.ok) { showToast('Solicitação atualizada'); carregarSolicitacoes(); }
    else showToast('Erro ao atualizar', 'error');
}

async function criarSolicitacao(e) {
    e.preventDefault();
    const dados = Object.fromEntries(new FormData(e.target));
    const resp = await fetch('/api/lgpd/solicitacoes', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(dados),
    });
    if (resp.ok) { showToast('Solicitação registrada'); e.target.reset(); carregarSolicitacoes(); }
    else showToast('Erro ao registrar', 'error');
}

async function carregarIncidentes() {
    const resp = await fetch('/api/lgpd/incidentes');
    if (!resp.ok) return;
    const tb = document.getElementById('tbIncidentes');
    tb.replaceChildren();
    for (const i of await resp.json()) {
        const tr = document.createElement('tr');
        celula(tr, i.ocorrido_em.split('-').reverse().join('/'));
        celula(tr, i.descricao);
        celula(tr, i.risco);
        celula(tr, i.comunicado_anpd ? 'Sim' : 'Não');
        celula(tr, i.titulares_afetados || '—');
        tb.appendChild(tr);
    }
}

async function criarIncidente(e) {
    e.preventDefault();
    const f = e.target;
    const dados = Object.fromEntries(new FormData(f));
    dados.comunicado_anpd = f.comunicado_anpd.checked;
    dados.comunicado_titulares = f.comunicado_titulares.checked;
    const resp = await fetch('/api/lgpd/incidentes', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(dados),
    });
    if (resp.ok) { showToast('Incidente registrado'); f.reset(); carregarIncidentes(); }
    else showToast('Erro ao registrar', 'error');
}

async function salvarConfig(e) {
    e.preventDefault();
    const resp = await fetch('/api/lgpd/config', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Object.fromEntries(new FormData(e.target))),
    });
    if (resp.ok) { showToast('Dados salvos'); setTimeout(() => location.reload(), 600); }
    else showToast('Erro ao salvar', 'error');
}

carregarSolicitacoes();
carregarIncidentes();
