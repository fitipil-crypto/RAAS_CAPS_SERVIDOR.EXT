// Eventos — lançamento múltiplo de atendimentos RAAS
const MAX_PROC = 5;
const MAX_PROF = 10;

function changeMonth() {
    window.location.href = '/eventos?month=' + document.getElementById('monthPicker').value;
}

function escapeHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}

/* A tela mostra a data em pt-BR; o YYYY-MM-DD fica só nos data-attributes
   dos cards e nos campos <input type="date">. */
function dataBr(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || '');
    return m ? `${m[3]}/${m[2]}/${m[1]}` : (iso || '');
}

async function apiJson(url, options) {
    const resp = await fetch(url, options);
    let corpo = null;
    try { corpo = await resp.json(); } catch (e) { /* resposta sem JSON */ }
    if (!resp.ok) {
        const detalhe = corpo && typeof corpo.detail === 'string' ? corpo.detail : 'Falha na operação';
        throw new Error(detalhe);
    }
    return corpo;
}

// ─── Criar / editar evento ──────────────────────────────────────────

function openEventoModal() {
    document.getElementById('eventoModal').style.display = 'flex';
    document.getElementById('eventoModalTitle').textContent = 'Novo Evento';
    document.getElementById('eventoForm').reset();
    document.getElementById('evento-id').value = '';
    // Já abre dentro da competência que está sendo olhada.
    document.getElementById('evento-date').value = document.getElementById('monthPicker').value + '-01';
    document.getElementById('evento-name').focus();
}

function closeEventoModal() {
    document.getElementById('eventoModal').style.display = 'none';
}

function editEvento(eventoId) {
    const card = document.querySelector(`.evento-card[data-evento-id="${CSS.escape(eventoId)}"]`);
    if (!card) return;
    document.getElementById('eventoModal').style.display = 'flex';
    document.getElementById('eventoModalTitle').textContent = 'Editar Evento';
    document.getElementById('evento-id').value = eventoId;
    document.getElementById('evento-name').value = card.dataset.eventoNome;
    document.getElementById('evento-date').value = card.dataset.eventoData;
    document.getElementById('evento-notes').value = '';
    document.getElementById('evento-name').focus();
}

async function saveEvento(e) {
    e.preventDefault();
    const id = document.getElementById('evento-id').value;
    const payload = {
        name: document.getElementById('evento-name').value.trim(),
        event_date: document.getElementById('evento-date').value,
        notes: document.getElementById('evento-notes').value.trim() || null,
    };
    if (!payload.name || !payload.event_date) {
        showToast('Informe o nome e a data do evento', 'error');
        return;
    }
    try {
        await apiJson(id ? `/api/eventos/${id}` : '/api/eventos/', {
            method: id ? 'PUT' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        showToast(id ? 'Evento atualizado' : 'Evento criado');
        irParaCompetencia(payload.event_date.slice(0, 7));
    } catch (erro) {
        showToast(erro.message, 'error');
    }
}

/* Recarrega já na competência do evento — criar um evento de outro mês
   mandaria o usuário para uma tela onde ele não apareceria. */
function irParaCompetencia(month) {
    const atual = document.getElementById('monthPicker').value;
    setTimeout(() => {
        window.location.href = month === atual ? window.location.href : `/eventos?month=${month}`;
    }, 600);
}

/* A exclusão oferece apagar junto os atendimentos lançados pelo evento.
   Vem desmarcado: apagar registros RAAS já computados é irreversível. */
function deleteEvento(eventoId) {
    const card = document.querySelector(`.evento-card[data-evento-id="${CSS.escape(eventoId)}"]`);
    const registros = EVENTOS_REGISTROS[eventoId] || 0;

    document.getElementById('excluir-evento-id').value = eventoId;
    document.getElementById('excluirResumo').innerHTML =
        `Excluir o evento <strong>${escapeHtml(card.dataset.eventoNome)}</strong> (${dataBr(card.dataset.eventoData)})?`;

    // A opção de apagar os atendimentos só existe para o administrador.
    const opcao = document.getElementById('excluirOpcao');
    const checkbox = document.getElementById('excluir-registros');
    if (checkbox) checkbox.checked = false;
    if (opcao) {
        opcao.hidden = registros === 0;
        document.getElementById('excluirOpcaoTexto').innerHTML =
            `Apagar também os <strong>${registros}</strong> atendimento(s) que este evento lançou.`;
    }
    atualizarAvisoExclusao();
    document.getElementById('btnExcluir').disabled = false;
    document.getElementById('excluirModal').style.display = 'flex';
}

function closeExcluirModal() {
    document.getElementById('excluirModal').style.display = 'none';
}

function atualizarAvisoExclusao() {
    const aviso = document.getElementById('excluirAviso');
    const checkbox = document.getElementById('excluir-registros');
    const marcado = !!checkbox && checkbox.checked;
    aviso.hidden = !marcado;
    if (marcado) {
        aviso.innerHTML = '⚠️ Os atendimentos saem do RAAS dos pacientes e não podem ser recuperados. '
            + 'Registros que já existiam antes do lançamento não são apagados.';
    }
}

async function confirmarExclusao() {
    const eventoId = document.getElementById('excluir-evento-id').value;
    const checkbox = document.getElementById('excluir-registros');
    const removerRegistros = !!checkbox && checkbox.checked;
    const btn = document.getElementById('btnExcluir');
    btn.disabled = true;
    try {
        const r = await apiJson(`/api/eventos/${eventoId}?remover_registros=${removerRegistros}`, { method: 'DELETE' });
        showToast(r.mensagem || 'Evento excluído');
        setTimeout(() => location.reload(), 800);
    } catch (erro) {
        showToast(erro.message, 'error');
        btn.disabled = false;
    }
}

// ─── Pacientes do evento ────────────────────────────────────────────

function openPacientesModal(eventoId) {
    document.getElementById('pacientes-evento-id').value = eventoId;
    document.getElementById('pacienteFiltro').value = '';
    const jaNaLista = new Set(EVENTOS_PACIENTES[eventoId] || []);

    document.getElementById('pacientesLista').innerHTML = PACIENTES_DATA
        .slice()
        .sort((a, b) => a.name.localeCompare(b.name, 'pt-BR'))
        .map(p => {
            const dentro = jaNaLista.has(p.id);
            return `<label data-busca="${escapeHtml((p.name + ' ' + (p.prontuario || '')).toLowerCase())}"${dentro ? ' class="ja-na-lista"' : ''}>
                <input type="checkbox" value="${escapeHtml(p.id)}"${dentro ? ' checked disabled' : ''} onchange="atualizarContagem()">
                <span><strong>${escapeHtml(p.name)}</strong> <span style="color:var(--muted);">— Pront: ${escapeHtml(p.prontuario) || '—'}</span>${dentro ? ' <em style="color:var(--muted);">(já na lista)</em>' : ''}</span>
            </label>`;
        }).join('');

    atualizarContagem();
    document.getElementById('pacientesModal').style.display = 'flex';
    document.getElementById('pacienteFiltro').focus();
}

function closePacientesModal() {
    document.getElementById('pacientesModal').style.display = 'none';
}

function filtrarPacientes() {
    const q = document.getElementById('pacienteFiltro').value.toLowerCase().trim();
    document.querySelectorAll('#pacientesLista label').forEach(l => {
        l.style.display = !q || l.dataset.busca.includes(q) ? '' : 'none';
    });
}

function marcarTodosVisiveis(marcar) {
    document.querySelectorAll('#pacientesLista label').forEach(l => {
        const cb = l.querySelector('input');
        if (cb.disabled) return;
        if (marcar && l.style.display === 'none') return;
        cb.checked = marcar;
    });
    atualizarContagem();
}

function selecionadosPacientes() {
    return Array.from(document.querySelectorAll('#pacientesLista input:checked:not(:disabled)')).map(cb => cb.value);
}

function atualizarContagem() {
    const n = selecionadosPacientes().length;
    document.getElementById('pacientesSelecionados').textContent = `${n} selecionado(s)`;
}

async function salvarPacientes() {
    const eventoId = document.getElementById('pacientes-evento-id').value;
    const patient_ids = selecionadosPacientes();
    if (patient_ids.length === 0) {
        showToast('Selecione ao menos um paciente', 'error');
        return;
    }
    try {
        const r = await apiJson(`/api/eventos/${eventoId}/pacientes`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ patient_ids }),
        });
        showToast(`${r.adicionados} paciente(s) adicionado(s) à lista`);
        setTimeout(() => location.reload(), 700);
    } catch (erro) {
        showToast(erro.message, 'error');
    }
}

async function removerPaciente(eventoId, patientId) {
    if (!confirm('Tirar este paciente da lista do evento?')) return;
    try {
        await apiJson(`/api/eventos/${eventoId}/pacientes/${patientId}`, { method: 'DELETE' });
        showToast('Paciente removido da lista');
        setTimeout(() => location.reload(), 500);
    } catch (erro) {
        showToast(erro.message, 'error');
    }
}

// ─── Lançamento em lote ─────────────────────────────────────────────

function openLancamentoModal(eventoId) {
    const card = document.querySelector(`.evento-card[data-evento-id="${CSS.escape(eventoId)}"]`);
    const total = (EVENTOS_PACIENTES[eventoId] || []).length;
    if (total === 0) {
        showToast('Adicione pacientes à lista antes de lançar os registros', 'error');
        return;
    }
    document.getElementById('lancamento-evento-id').value = eventoId;
    document.getElementById('lancamento-data').value = dataBr(card.dataset.eventoData);
    document.getElementById('lancamentoResumo').innerHTML =
        `🎉 <strong>${escapeHtml(card.dataset.eventoNome)}</strong> · ${dataBr(card.dataset.eventoData)} · <strong>${total}</strong> paciente(s) na lista`;

    document.getElementById('evtProcRows').innerHTML = '';
    document.getElementById('evtProfRows').innerHTML = '';
    addEvtProcRow();
    addEvtProfRow();
    document.getElementById('evtNotice').hidden = true;
    document.getElementById('btnLancar').disabled = false;
    document.getElementById('lancamentoModal').style.display = 'flex';
}

function closeLancamentoModal() {
    document.getElementById('lancamentoModal').style.display = 'none';
}

function addEvtProcRow() {
    const rows = document.getElementById('evtProcRows');
    if (rows.children.length >= MAX_PROC) return;
    const div = document.createElement('div');
    div.className = 'evt-row evt-proc-row';
    div.innerHTML = `
        <div class="form-group evt-select-group">
            <select class="evt-proc-select" onchange="atualizarPrevisao()">
                <option value="">— Escolher procedimento —</option>
                ${PROCEDIMENTOS_DATA.map(p => `<option value="${escapeHtml(p.id)}">${escapeHtml(p.label)}</option>`).join('')}
            </select>
        </div>
        <div class="form-group evt-qty-group">
            <input type="number" class="evt-proc-qty" min="1" value="1" title="Quantidade">
        </div>
        <button type="button" class="btn btn-ghost btn-sm evt-remove-btn" onclick="removeEvtRow(this)" title="Remover">🗑</button>
    `;
    rows.appendChild(div);
    atualizarRemocao('evtProcRows');
    atualizarPrevisao();
}

function addEvtProfRow() {
    const rows = document.getElementById('evtProfRows');
    if (rows.children.length >= MAX_PROF) return;
    const div = document.createElement('div');
    div.className = 'evt-row evt-prof-row';
    div.innerHTML = `
        <div class="form-group evt-select-group">
            <select class="evt-prof-select" onchange="mostrarCbo(this); atualizarPrevisao();">
                <option value="">— Escolher profissional —</option>
                ${PROFISSIONAIS_DATA.map(p => `<option value="${escapeHtml(p.id)}" data-cbo="${escapeHtml(p.cbo)}">${escapeHtml(p.name)}</option>`).join('')}
            </select>
        </div>
        <span class="evt-cbo"></span>
        <button type="button" class="btn btn-ghost btn-sm evt-remove-btn" onclick="removeEvtRow(this)" title="Remover">🗑</button>
    `;
    rows.appendChild(div);
    atualizarRemocao('evtProfRows');
    atualizarPrevisao();
}

function mostrarCbo(select) {
    const cbo = select.selectedOptions[0]?.dataset.cbo || '';
    select.closest('.evt-row').querySelector('.evt-cbo').textContent = cbo ? `CBO ${cbo}` : '';
}

function removeEvtRow(btn) {
    const container = btn.closest('#evtProcRows, #evtProfRows');
    btn.closest('.evt-row').remove();
    atualizarRemocao(container.id);
    atualizarPrevisao();
}

/* Com uma linha só não há o que remover. */
function atualizarRemocao(containerId) {
    const linhas = document.querySelectorAll(`#${containerId} .evt-row`);
    linhas.forEach(l => {
        l.querySelector('.evt-remove-btn').style.visibility = linhas.length > 1 ? 'visible' : 'hidden';
    });
}

function procedimentosEscolhidos() {
    return Array.from(document.querySelectorAll('#evtProcRows .evt-proc-row'))
        .map(row => ({
            procedure_id: row.querySelector('.evt-proc-select').value,
            quantity: parseInt(row.querySelector('.evt-proc-qty').value, 10) || 1,
        }))
        .filter(p => p.procedure_id);
}

function profissionaisEscolhidos() {
    const ids = Array.from(document.querySelectorAll('#evtProfRows .evt-prof-select'))
        .map(s => s.value)
        .filter(Boolean);
    return [...new Set(ids)];  // o mesmo profissional duas vezes geraria duplicata
}

/* Mostra quantos registros o lançamento vai gerar antes de confirmar —
   o cruzamento procedimento × profissional × paciente cresce rápido. */
function atualizarPrevisao() {
    const eventoId = document.getElementById('lancamento-evento-id').value;
    const pacientes = (EVENTOS_PACIENTES[eventoId] || []).length;
    const procs = procedimentosEscolhidos().length;
    const profs = profissionaisEscolhidos().length;
    const total = pacientes * procs * profs;
    const el = document.getElementById('lancamentoPrevisao');
    el.innerHTML = total
        ? `Serão gerados <strong>${total}</strong> registro(s): ${pacientes} paciente(s) × ${procs} procedimento(s) × ${profs} profissional(is). Combinações já existentes são ignoradas.`
        : 'Escolha ao menos um procedimento e um profissional.';
}

async function lancarRegistros() {
    const eventoId = document.getElementById('lancamento-evento-id').value;
    const procedures = procedimentosEscolhidos();
    const professional_ids = profissionaisEscolhidos();

    if (procedures.length === 0) { showToast('Escolher uma opção de procedimento', 'error'); return; }
    if (professional_ids.length === 0) { showToast('Escolher uma opção de profissional', 'error'); return; }

    const pacientes = (EVENTOS_PACIENTES[eventoId] || []).length;
    const total = pacientes * procedures.length * professional_ids.length;
    if (!confirm(`Confirmar o lançamento de até ${total} registro(s) RAAS para os ${pacientes} paciente(s) do evento?`)) return;

    const btn = document.getElementById('btnLancar');
    btn.disabled = true;
    try {
        const r = await apiJson(`/api/eventos/${eventoId}/registros`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                procedures,
                professional_ids,
                local_realizacao: document.getElementById('lancamento-local').value,
                srv: document.getElementById('lancamento-srv').value,
                cls: document.getElementById('lancamento-cls').value,
            }),
        });
        mostrarResultado(r);
    } catch (erro) {
        mostrarAvisoEvento(
            `<span class="notice-titulo">⚠️ Nenhum registro foi efetivado</span>${escapeHtml(erro.message)}`,
            'error');
        btn.disabled = false;
    }
}

/* Caixa de aviso centralizada no modal, no mesmo padrão do "Novo Registro
   RAAS". Fica até ser fechada, porque o motivo de um registro não ter sido
   efetivado precisa ser lido, não piscar por 3 segundos. */
function mostrarAvisoEvento(html, tipo = 'success') {
    const wrap = document.getElementById('evtNotice');
    const box = document.getElementById('evtNoticeBox');
    box.className = `reg-notice-box reg-notice-${tipo} reg-notice-detalhe`;
    box.innerHTML = html + `<div class="notice-acoes">
        <button type="button" class="btn btn-primary" onclick="fecharAvisoEvento()">Fechar</button>
    </div>`;
    wrap.hidden = false;
    posicionarAvisoSobreModal(wrap, document.querySelector('#lancamentoModal .modal'));
}

function fecharAvisoEvento() {
    document.getElementById('evtNotice').hidden = true;
    location.reload();
}

window.addEventListener('resize', () => posicionarAvisoSobreModal(
    document.getElementById('evtNotice'), document.querySelector('#lancamentoModal .modal')));

function listaDeIgnorados(detalhe) {
    const itens = (detalhe || []).slice(0, 10)
        .map(d => `<li>${escapeHtml(d.paciente)} — ${escapeHtml(d.procedimento)} / ${escapeHtml(d.profissional)}</li>`)
        .join('');
    const resto = (detalhe || []).length - 10;
    return `<ul>${itens}</ul>` + (resto > 0 ? `<em>… e mais ${resto}.</em>` : '');
}

/* O total lançado quase nunca bate com a prévia: combinações que já existem
   são puladas para não duplicar linha na exportação RAAS. */
function mostrarResultado(r) {
    const naoEfetivados = r.ignorados + (r.pulados ? r.pulados.length : 0);
    const tipo = r.criados === 0 ? 'error' : 'success';

    let html = `<span class="notice-titulo">${r.criados === 0 ? '⚠️' : '✓'} `
             + `${r.criados} registro(s) lançado(s)</span>`
             + `Evento com ${r.pacientes} paciente(s) na lista.`;

    if (naoEfetivados === 0) {
        mostrarAvisoEvento(html, tipo);
        return;
    }

    if (r.ignorados) {
        html += `<span class="notice-bloco"><strong>${r.ignorados} não foi(ram) efetivado(s): o atendimento já existia.</strong><br>`
             + `Mesma data, paciente, profissional e procedimento. O paciente continua com esse atendimento — `
             + `lançar de novo criaria linha duplicada na exportação RAAS.`
             + listaDeIgnorados(r.ignorados_detalhe) + `</span>`;
    }
    if (r.pulados && r.pulados.length) {
        html += `<span class="notice-bloco"><strong>${r.pulados.length} paciente(s) pulado(s): admissão posterior à data do evento.</strong><br>`
             + `O RAAS não aceita atendimento anterior à admissão do paciente.<ul>`
             + r.pulados.slice(0, 10).map(n => `<li>${escapeHtml(n)}</li>`).join('') + `</ul></span>`;
    }
    mostrarAvisoEvento(html, tipo);
}
