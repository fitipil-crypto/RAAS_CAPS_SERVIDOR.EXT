// Registros RAAS — CRUD
function changeMonth() {
    const m = document.getElementById('monthPicker').value;
    window.location.href = '/registros?month=' + m;
}

function toggleGrupo(header) {
    const body = header.nextElementSibling;
    const chevron = header.querySelector('.grupo-chevron');
    const isOpen = body.style.display !== 'none';
    body.style.display = isOpen ? 'none' : '';
    if (chevron) chevron.textContent = isOpen ? '▸' : '▾';
}

function clearRegistroDateSearch() {
    const dateInput = document.getElementById('registroDateSearch');
    if (!dateInput) return;
    dateInput.value = '';
    filterRegistros();
}

function filterRegistros() {
    const nameQ = (document.getElementById('registroSearch')?.value || '').toLowerCase().trim();
    const dateQ = document.getElementById('registroDateSearch')?.value || '';
    const groups = document.querySelectorAll('.registro-group');
    const noMatch = document.getElementById('registroNoMatch');
    let firstMatch = null;
    let matchCount = 0;

    groups.forEach(group => {
        const name = group.dataset.patientName || '';
        const prontuario = group.dataset.patientProntuario || '';
        const nameMatches = !nameQ || name.includes(nameQ) || prontuario.includes(nameQ);

        let dateMatches = !dateQ;
        const rows = group.querySelectorAll('tbody tr');
        rows.forEach(row => {
            const rowMatches = !dateQ || row.dataset.date === dateQ;
            row.style.display = rowMatches ? '' : 'none';
            if (dateQ && row.dataset.date === dateQ) dateMatches = true;
        });

        const isolado = !pacienteIsolado || group.dataset.patientId === pacienteIsolado;
        const matches = nameMatches && dateMatches && isolado;
        group.style.display = matches ? '' : 'none';
        if (matches) {
            matchCount++;
            if (!firstMatch) firstMatch = group;
            if (dateQ) {
                const header = group.querySelector('.registro-group-header');
                const body = header.nextElementSibling;
                const chevron = header.querySelector('.grupo-chevron');
                body.style.display = '';
                if (chevron) chevron.textContent = '▾';
            }
        }
    });

    if (noMatch) noMatch.style.display = ((nameQ || dateQ) && matchCount === 0) ? '' : 'none';

    if (firstMatch && nameQ && !dateQ) {
        const header = firstMatch.querySelector('.registro-group-header');
        const body = header.nextElementSibling;
        const chevron = header.querySelector('.grupo-chevron');
        if (body.style.display === 'none') {
            body.style.display = '';
            if (chevron) chevron.textContent = '▾';
        }
        firstMatch.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}

function searchPatient(query) {
    const results = document.getElementById('patientResults');
    const hidden = document.getElementById('form-patient-id');
    const q = (query || '').toLowerCase().trim();

    // A new search invalidates the previously selected patient.
    hidden.value = '';
    if (!q) {
        results.style.display = 'none';
        return;
    }

    const prontuarioMatches = PACIENTES_DATA.filter(p =>
        p.prontuario && String(p.prontuario).toLowerCase() === q
    );
    const matches = prontuarioMatches.length > 0
        ? prontuarioMatches
        : PACIENTES_DATA.filter(p =>
            p.name.toLowerCase().includes(q) ||
            (p.cns && String(p.cns).toLowerCase().includes(q)) ||
            (p.prontuario && String(p.prontuario).toLowerCase().includes(q))
        ).sort((a, b) => {
            const aProntuario = String(a.prontuario || '').toLowerCase();
            const bProntuario = String(b.prontuario || '').toLowerCase();
            const aStarts = aProntuario.startsWith(q);
            const bStarts = bProntuario.startsWith(q);
            return Number(bStarts) - Number(aStarts);
        }).slice(0, 20);
    results._matches = matches;

    if (matches.length === 0) {
        hidden.value = '';
        results.innerHTML = '<div class="autocomplete-empty">Nenhum paciente encontrado</div>';
        results.style.display = 'block';
        return;
    }

    results.innerHTML = matches.map(p =>
        `<div class="autocomplete-item" data-patient-id="${escapeHtml(p.id)}" data-patient-name="${escapeHtml(p.name)}">
            <div class="item-name">${escapeHtml(p.name)}${p.prontuario ? ` <span style="color:var(--muted);font-weight:600;">- Pront: ${escapeHtml(p.prontuario)}</span>` : ''}</div>
            <div class="item-sub">CNS: ${escapeHtml(p.cns) || 's/doc'} · Mãe: ${escapeHtml(p.motherName) || 's/info'} · Nasc: ${formatBirthDate(p.birthDate)}</div>
        </div>`
    ).join('');
    results.style.display = 'block';
}

function formatBirthDate(iso) {
    if (!iso || iso.length !== 10) return 's/info';
    const [y, m, d] = iso.split('-');
    return `${d}/${m}/${y}`;
}

function clearPatient() {
    document.getElementById('patientSearch').value = '';
    document.getElementById('form-patient-id').value = '';
    document.getElementById('patientResults').style.display = 'none';
    isolarPaciente('');
    document.getElementById('patientSearch').focus();
}

function escapeHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}

function selectPatient(id, name) {
    const input = document.getElementById('patientSearch');
    input.value = name;
    document.getElementById('form-patient-id').value = id;
    document.getElementById('patientResults').style.display = 'none';
    limparErroSelecao(input);
    ultimoPaciente = id;
    isolarPaciente(id);
    posicionarGrupoNoTopo(grupoPorPaciente(id));
    posicionarModalAposTipo(grupoPorPaciente(id));
}

document.getElementById('patientResults').addEventListener('click', (e) => {
    const item = e.target.closest('.autocomplete-item');
    if (!item || !item.dataset.patientId) return;
    selectPatient(item.dataset.patientId, item.dataset.patientName);
});

document.querySelector('#regForm [name="service_date"]').addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    document.getElementById('patientSearch').focus();
});

document.getElementById('patientSearch').addEventListener('keydown', (e) => {
    const enter = e.key === 'Enter';
    if (!enter && (e.key !== 'Tab' || e.shiftKey)) return;
    const results = document.getElementById('patientResults');
    const matches = results.style.display === 'none' ? [] : (results._matches || []);
    if (matches.length > 0) selectPatient(matches[0].id, matches[0].name);
    if (enter) {
        e.preventDefault();
        document.getElementById('profSearch').focus();
    }
});

/* Seta esquerda percorre ao contrário a sequência do Enter:
   salvar → procedimentos → profissional → paciente → data do atendimento. */
document.getElementById('regForm').addEventListener('keydown', (e) => {
    if (!setaEsquerdaVolta(e)) return;
    const form = document.getElementById('regForm');
    const sequencia = [
        form.querySelector('[name="service_date"]'),
        document.getElementById('patientSearch'),
        document.getElementById('profSearch'),
        ...document.querySelectorAll('#procRows .proc-search-input'),
        form.querySelector('button[type="submit"]'),
    ].filter(Boolean);
    const i = sequencia.indexOf(e.target);
    if (i <= 0) return;
    e.preventDefault();
    const lista = e.target.closest('.form-group')?.querySelector('.autocomplete-results');
    if (lista) lista.style.display = 'none';
    sequencia[i - 1].focus();
});

function searchProf(query) {
    const results = document.getElementById('profResults');
    const hidden = document.getElementById('form-professional-id');
    const q = (query || '').toLowerCase().trim();

    if (!q) {
        hidden.value = '';
        results.style.display = 'none';
        return;
    }

    const matches = PROFISSIONAIS_DATA.filter(p => p.name.toLowerCase().includes(q)).slice(0, 20);
    results._matches = matches;

    if (matches.length === 0) {
        hidden.value = '';
        results.innerHTML = '<div class="autocomplete-empty">Nenhum profissional encontrado</div>';
        results.style.display = 'block';
        return;
    }

    results.innerHTML = matches.map(p =>
        `<div class="autocomplete-item" data-prof-id="${escapeHtml(p.id)}" data-prof-name="${escapeHtml(p.name)}" data-prof-cbo="${escapeHtml(p.cbo)}">
            <div class="item-name">${escapeHtml(p.name)}</div>
            <div class="item-sub">${escapeHtml(p.cbo) || 's/CBO'}</div>
        </div>`
    ).join('');
    results.style.display = 'block';
}

function selectProf(id, name, cbo) {
    limparErroSelecao(document.getElementById('profSearch'));
    document.getElementById('profSearch').value = name;
    document.getElementById('form-professional-id').value = id;
    document.getElementById('cboInput').value = cbo || '';
    document.getElementById('profResults').style.display = 'none';
}

function clearProf() {
    document.getElementById('profSearch').value = '';
    document.getElementById('form-professional-id').value = '';
    document.getElementById('cboInput').value = '';
    document.getElementById('profResults').style.display = 'none';
    document.getElementById('profSearch').focus();
}

document.getElementById('profResults').addEventListener('click', (e) => {
    const item = e.target.closest('.autocomplete-item');
    if (!item || !item.dataset.profId) return;
    selectProf(item.dataset.profId, item.dataset.profName, item.dataset.profCbo);
});

document.getElementById('profSearch').addEventListener('keydown', (e) => {
    const enter = e.key === 'Enter';
    if (!enter && (e.key !== 'Tab' || e.shiftKey)) return;
    const results = document.getElementById('profResults');
    const matches = results.style.display === 'none' ? [] : (results._matches || []);
    if (matches.length > 0) selectProf(matches[0].id, matches[0].name, matches[0].cbo);
    if (enter) {
        e.preventDefault();
        document.querySelector('#procRows .proc-search-input')?.focus();
    }
});

document.addEventListener('click', (e) => {
    if (!e.target.closest('#patientSearch') && !e.target.closest('#patientResults')) {
        document.getElementById('patientResults').style.display = 'none';
    }
    if (!e.target.closest('#profSearch') && !e.target.closest('#profResults')) {
        document.getElementById('profResults').style.display = 'none';
    }
    if (!e.target.closest('.proc-select-group')) {
        document.querySelectorAll('.proc-results').forEach(el => el.style.display = 'none');
    }
});

const MAX_PROC_ROWS = 5;

function searchProc(inputEl) {
    const row = inputEl.closest('.proc-row');
    const results = row.querySelector('.proc-results');
    const hidden = row.querySelector('.proc-hidden-id');
    const q = (inputEl.value || '').toLowerCase().trim();

    if (!q) {
        hidden.value = '';
        results.style.display = 'none';
        return;
    }

    const matches = PROCEDIMENTOS_DATA.filter(p => p.label.toLowerCase().includes(q)).slice(0, 20);
    results._matches = matches;

    if (matches.length === 0) {
        hidden.value = '';
        results.innerHTML = '<div class="autocomplete-empty">Nenhum procedimento encontrado</div>';
        results.style.display = 'block';
        return;
    }

    results.innerHTML = matches.map(p =>
        `<div class="autocomplete-item" data-proc-id="${escapeHtml(p.id)}" data-proc-label="${escapeHtml(p.label)}">
            <div class="item-name">${escapeHtml(p.label)}</div>
        </div>`
    ).join('');
    results.style.display = 'block';
}

// O procedimento de acompanhamento infanto-juvenil exige informar o número
// da autorização no RAAS — o campo fica oculto/desabilitado até ser escolhido.
const AUTH_REQUIRED_PROC_CODE = '03.01.08.038-0';

function updateCamposDoProcedimento() {
    updateAutorizacao();
}

function updateAutorizacao() {
    const row = document.getElementById('authorizationRow');
    const input = document.getElementById('authorizationInput');
    if (!row || !input) return;
    const selectedIds = Array.from(document.querySelectorAll('#procRows .proc-hidden-id'))
        .map((el) => el.value)
        .filter(Boolean);
    const needsAuth = selectedIds.some((id) => {
        const proc = PROCEDIMENTOS_DATA.find((p) => p.id === id);
        return proc && proc.code === AUTH_REQUIRED_PROC_CODE;
    });
    row.style.display = needsAuth ? '' : 'none';
    input.disabled = !needsAuth;
    if (!needsAuth) input.value = '';
}

function selectProc(row, id, label) {
    limparErroSelecao(row.querySelector('.proc-search-input'));
    row.querySelector('.proc-search-input').value = label;
    row.querySelector('.proc-hidden-id').value = id;
    row.querySelector('.proc-results').style.display = 'none';
    updateCamposDoProcedimento();
    focarPrimeiroCampoVazio();
}

function clearProc(btn) {
    const row = btn.closest('.proc-row');
    row.querySelector('.proc-search-input').value = '';
    row.querySelector('.proc-hidden-id').value = '';
    row.querySelector('.proc-results').style.display = 'none';
    row.querySelector('.proc-search-input').focus();
    updateCamposDoProcedimento();
}

document.getElementById('procRows').addEventListener('click', (e) => {
    const item = e.target.closest('.autocomplete-item');
    if (!item || !item.dataset.procId) return;
    const row = item.closest('.proc-row');
    selectProc(row, item.dataset.procId, item.dataset.procLabel);
});

document.getElementById('procRows').addEventListener('keydown', (e) => {
    const enter = e.key === 'Enter';
    if (!enter && (e.key !== 'Tab' || e.shiftKey)) return;
    const input = e.target.closest('.proc-search-input');
    if (!input) return;
    if (enter) e.preventDefault();
    const row = input.closest('.proc-row');
    const results = row.querySelector('.proc-results');
    const matches = results.style.display === 'none' ? [] : (results._matches || []);
    if (matches.length > 0) selectProc(row, matches[0].id, matches[0].label);
});

function addProcRow(selectedId = '', qty = 1) {
    const rows = document.getElementById('procRows');
    if (rows.children.length >= MAX_PROC_ROWS) return;
    const idx = rows.children.length;
    const selected = selectedId ? PROCEDIMENTOS_DATA.find(p => p.id === selectedId) : null;
    const div = document.createElement('div');
    div.className = 'proc-row';
    div.innerHTML = `
        <div class="form-group proc-select-group" style="position:relative;">
            <input type="text" class="proc-search-input autocomplete-input" placeholder="Buscar procedimento..." autocomplete="off"
                   value="${selected ? escapeHtml(selected.label) : ''}"
                   oninput="searchProc(this)" onfocus="searchProc(this)">
            <button type="button" class="input-clear-btn" tabindex="-1" onclick="clearProc(this)" title="Limpar seleção">✕</button>
            <input type="hidden" name="procedure_id_${idx}" class="proc-hidden-id" value="${escapeHtml(selectedId)}">
            <div class="proc-results autocomplete-results" style="display:none;"></div>
            <div class="reg-field-error"></div>
        </div>
        <div class="form-group proc-qty-group">
            <input type="number" name="quantity_${idx}" min="1" value="${qty}" placeholder="Qtd" tabindex="-1">
        </div>
        <button type="button" class="btn btn-ghost btn-sm proc-remove-btn" tabindex="-1" onclick="removeProcRow(this)" title="Remover procedimento">🗑</button>
    `;
    rows.appendChild(div);
    updateAddProcBtn();
    updateProcRemoveBtns();
}

/* Com um único procedimento não há o que remover; a partir do segundo, todas
   as linhas — inclusive a principal — ganham o 🗑. */
function updateProcRemoveBtns() {
    const rows = document.querySelectorAll('#procRows .proc-row');
    rows.forEach(row => {
        row.querySelector('.proc-remove-btn').style.visibility = rows.length > 1 ? 'visible' : 'hidden';
    });
}

function adicionarProcedimento() {
    addProcRow();
    focarPrimeiroCampoVazio();
}

function removeProcRow(btn) {
    btn.closest('.proc-row').remove();
    updateAddProcBtn();
    updateProcRemoveBtns();
    updateCamposDoProcedimento();
    focarPrimeiroCampoVazio();
}

function updateAddProcBtn() {
    const rows = document.getElementById('procRows');
    const btn = document.getElementById('addProcBtn');
    if (btn.dataset.forceHidden === '1') return;
    btn.style.display = rows.children.length >= MAX_PROC_ROWS ? 'none' : '';
}

function resetProcRows() {
    document.getElementById('procRows').innerHTML = '';
    addProcRow();
}

function todayIso() {
    const d = new Date();
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

let listRefreshPending = false;

function grupoPorPaciente(patientId) {
    if (!patientId) return null;
    return document.querySelector(`.registro-group[data-patient-id="${CSS.escape(patientId)}"]`);
}

function setGrupoAberto(group, aberto) {
    if (!group) return;
    const header = group.querySelector('.registro-group-header');
    const body = header.nextElementSibling;
    const chevron = header.querySelector('.grupo-chevron');
    body.style.display = aberto ? '' : 'none';
    if (chevron) chevron.textContent = aberto ? '▾' : '▸';
}

/* Pacientes cuja relação de atendimentos está expandida no momento. */
function gruposAbertos() {
    return Array.from(document.querySelectorAll('.registro-group'))
        .filter(g => {
            const body = g.querySelector('.registro-group-header')?.nextElementSibling;
            return body && body.style.display !== 'none';
        })
        .map(g => g.dataset.patientId)
        .filter(Boolean);
}

/* Recarrega a lista mantendo os grupos que já estavam abertos e os filtros de
   busca — recarregar a página inteira fecharia tudo. */
async function refreshRegistrosList(patientId, { scroll = true } = {}) {
    const response = await fetch(`/registros?month=${encodeURIComponent(selectedMonth())}`);
    if (!response.ok) throw new Error('Falha ao atualizar a lista de atendimentos');

    const html = await response.text();
    const parsed = new DOMParser().parseFromString(html, 'text/html');
    const currentCard = document.querySelector('.card');
    const updatedCard = parsed.querySelector('.card');
    if (!currentCard || !updatedCard) throw new Error('Lista de atendimentos não encontrada');

    const abertos = new Set(gruposAbertos());
    if (patientId) abertos.add(patientId);
    const buscaNome = document.getElementById('registroSearch')?.value || '';
    const buscaData = document.getElementById('registroDateSearch')?.value || '';

    currentCard.replaceWith(updatedCard);

    abertos.forEach(pid => setGrupoAberto(grupoPorPaciente(pid), true));
    aplicarIsolamento();

    const nomeInput = document.getElementById('registroSearch');
    const dataInput = document.getElementById('registroDateSearch');
    if (nomeInput) nomeInput.value = buscaNome;
    if (dataInput) dataInput.value = buscaData;
    if (buscaNome || buscaData) filterRegistros();

    const group = grupoPorPaciente(patientId);
    if (group && scroll) posicionarGrupoNoTopo(group);
}

/* Com "Manter dados" marcado, o próximo lançamento repete profissional,
   procedimentos e demais campos; só o paciente precisa ser trocado. */
function manterDadosMarcado() {
    return !!document.getElementById('keepData')?.checked;
}

function restaurarDadosMantidos(manter) {
    const form = document.getElementById('regForm');
    const { data, procRows } = manter;
    for (const nome of ['local_realizacao', 'srv', 'cls', 'cbo_code']) {
        const el = form.querySelector(`[name="${nome}"]`);
        if (el && data[nome] !== undefined) el.value = data[nome];
    }
    document.getElementById('form-professional-id').value = data.professional_id || '';
    const prof = PROFISSIONAIS_DATA.find(p => p.id === data.professional_id);
    document.getElementById('profSearch').value = prof ? prof.name : '';
    document.getElementById('procRows').innerHTML = '';
    procRows.forEach(r => addProcRow(r.procedure_id, r.quantity));
    updateCamposDoProcedimento();
    if (data.authorization) document.getElementById('authorizationInput').value = data.authorization;
}

function prepareNextRecord(serviceDate, manter = null) {
    const form = document.getElementById('regForm');
    const keep = manterDadosMarcado();
    form.reset();
    document.getElementById('keepData').checked = keep;
    document.getElementById('modalTitle').textContent = 'Novo Registro RAAS';
    document.getElementById('form-id').value = '';
    document.getElementById('form-month').value = selectedMonth();
    applyMonthLimits();
    document.querySelector('[name="service_date"]').value = serviceDate;
    document.getElementById('form-patient-id').value = '';
    document.getElementById('patientSearch').value = '';
    document.getElementById('patientResults').style.display = 'none';
    document.getElementById('form-professional-id').value = '';
    document.getElementById('profSearch').value = '';
    document.getElementById('profResults').style.display = 'none';
    resetProcRows();
    limparErrosSelecao();
    const addProcBtn = document.getElementById('addProcBtn');
    addProcBtn.dataset.forceHidden = '0';
    addProcBtn.style.display = '';
    updateCamposDoProcedimento();
    if (manter) restaurarDadosMantidos(manter);
    // A data se repete no próximo lançamento; o cursor já espera o paciente.
    document.getElementById('patientSearch').focus();
}

const MSG_ESCOLHER = 'Escolher uma opção';

function limparErroSelecao(input) {
    if (!input) return;
    input.classList.remove('input-invalid');
    const erro = input.closest('.form-group')?.querySelector('.reg-field-error');
    if (erro) { erro.textContent = ''; erro.classList.remove('show'); }
}

function limparErrosSelecao() {
    document.querySelectorAll('#regForm .autocomplete-input').forEach(limparErroSelecao);
}

function marcarErroSelecao(input) {
    input.classList.add('input-invalid');
    const erro = input.closest('.form-group')?.querySelector('.reg-field-error');
    if (erro) { erro.textContent = MSG_ESCOLHER; erro.classList.add('show'); }
}

/* Paciente, profissional e procedimento precisam ser ESCOLHIDOS na lista:
   digitar o texto não basta, pois o id só é preenchido ao selecionar. */
function validarSelecoes() {
    limparErrosSelecao();
    const pendentes = [];
    if (!document.getElementById('form-patient-id').value) {
        pendentes.push(document.getElementById('patientSearch'));
    }
    if (!document.getElementById('form-professional-id').value) {
        pendentes.push(document.getElementById('profSearch'));
    }
    document.querySelectorAll('#procRows .proc-row').forEach((row, i) => {
        const input = row.querySelector('.proc-search-input');
        // a primeira linha é obrigatória; as extras só cobram escolha se
        // o usuário digitou algo nelas
        if (!row.querySelector('.proc-hidden-id').value && (i === 0 || input.value.trim())) {
            pendentes.push(input);
        }
    });

    pendentes.forEach(marcarErroSelecao);
    if (pendentes.length === 0) return true;
    pendentes[0].focus();
    return false;
}

/* Põe o cursor no primeiro campo ainda em branco (paciente → profissional →
   procedimentos), na ordem em que o formulário é preenchido. Sem nenhum campo
   pendente — caso do último procedimento escolhido — o cursor para no Salvar. */
function focarPrimeiroCampoVazio() {
    const campos = [
        document.getElementById('patientSearch'),
        document.getElementById('profSearch'),
        ...document.querySelectorAll('#procRows .proc-search-input'),
    ].filter(el => el && !el.disabled);
    const vazio = campos.find(el => !el.value.trim());
    if (vazio) vazio.focus();
    else document.querySelector('#regForm button[type="submit"]')?.focus();
}

/* Enquanto se lança um atendimento, a lista atrás do modal mostra só o
   paciente escolhido. closeModal() devolve a lista completa. */
let pacienteIsolado = '';
/* Último paciente escolhido/lançado no modal: ao fechar a janela o grupo dele
   continua aberto na lista para conferir os lançamentos. */
let ultimoPaciente = '';
const CHAVE_PACIENTE_ABERTO = 'registros.pacienteAberto';

/* Rola a página para o paciente ficar logo abaixo da barra do topo, com os
   lançamentos visíveis à esquerda da janela "Novo Registro RAAS". */
function posicionarGrupoNoTopo(group) {
    if (!group || group.style.display === 'none') return;
    const topbar = document.querySelector('.topbar')?.offsetHeight || 0;
    const y = group.getBoundingClientRect().top + window.scrollY - topbar;
    window.scrollTo({ top: Math.max(0, y), behavior: 'auto' });
}

function mostrarPacienteNaLista(patientId) {
    const group = grupoPorPaciente(patientId);
    if (!group || group.style.display === 'none') return;
    setGrupoAberto(group, true);
    posicionarGrupoNoTopo(group);
}

function isolarPaciente(patientId) {
    pacienteIsolado = patientId || '';
    aplicarIsolamento();
}

function aplicarIsolamento() {
    document.querySelectorAll('.registro-group').forEach(g => {
        const alvo = !pacienteIsolado || g.dataset.patientId === pacienteIsolado;
        g.style.display = alvo ? '' : 'none';
        if (alvo && pacienteIsolado) setGrupoAberto(g, true);
    });
    const buscaNome = document.getElementById('registroSearch')?.value || '';
    const buscaData = document.getElementById('registroDateSearch')?.value || '';
    if (buscaNome || buscaData) filterRegistros();
}

let regNoticeTimer = null;

/* Aviso grande e centralizado dentro da caixa "Novo Registro RAAS".
   Fora do modal (ex.: exclusão na lista) continua usando o toast do topo. */
function showRegNotice(msg, type = 'success') {
    const modal = document.getElementById('regModal');
    const wrap = document.getElementById('regNotice');
    const box = document.getElementById('regNoticeBox');
    if (!modal || !wrap || !box || modal.style.display === 'none') {
        showToast(msg, type);
        return;
    }
    const tamanho = msg.length <= 24 ? 'curta' : (msg.length <= 48 ? 'media' : 'longa');
    box.textContent = msg;
    box.className = `reg-notice-box reg-notice-${type} reg-notice-${tamanho}`;
    wrap.hidden = false;
    positionRegNotice();
    clearTimeout(regNoticeTimer);
    regNoticeTimer = setTimeout(hideRegNotice, 3000);
}

/* Cola o aviso sobre o retângulo visível do modal, para ficar no centro do
   interior da caixa mesmo depois de arrastada. */
function positionRegNotice() {
    const wrap = document.getElementById('regNotice');
    const modal = document.querySelector('#regModal .modal');
    if (!wrap || !modal || wrap.hidden) return;
    posicionarAvisoSobreModal(wrap, modal);
}

window.addEventListener('resize', positionRegNotice);

function hideRegNotice() {
    clearTimeout(regNoticeTimer);
    const wrap = document.getElementById('regNotice');
    if (wrap) wrap.hidden = true;
}

function selectedMonth() {
    return document.getElementById('monthPicker').value;
}

/* Primeiro e último dia da competência selecionada (YYYY-MM). */
function monthBounds(month) {
    const [y, m] = month.split('-').map(Number);
    const lastDay = new Date(y, m, 0).getDate();
    return { first: `${month}-01`, last: `${month}-${String(lastDay).padStart(2, '0')}` };
}

/* Trava o campo de data na competência aberta, para não lançar o
   atendimento de um mês dentro de outro. */
function applyMonthLimits() {
    const month = selectedMonth();
    const input = document.querySelector('[name="service_date"]');
    if (!input || !month) return;
    const { first, last } = monthBounds(month);
    input.min = first;
    input.max = last;
    if (input.value && input.value.slice(0, 7) !== month) input.value = '';
}

/* Data inicial: hoje, se estiver dentro da competência; senão, o 1º dia dela. */
function defaultServiceDate() {
    const month = selectedMonth();
    const hoje = todayIso();
    return hoje.slice(0, 7) === month ? hoje : monthBounds(month).first;
}

let sidebarAutoCollapsed = false;

/* Devolve true quando recolheu a barra lateral no desktop — nesse caso a lista
   desliza junto, com a transição de .main-content. */
function collapseSidebarForModal() {
    const sidebar = document.getElementById('sidebar');
    const main = document.getElementById('mainContent');
    if (!sidebar) return false;
    if (window.innerWidth <= 768) {
        sidebarAutoCollapsed = sidebar.classList.contains('show');
        sidebar.classList.remove('show');
        return false;
    }
    if (sidebar.classList.contains('collapsed')) { sidebarAutoCollapsed = false; return false; }
    sidebarAutoCollapsed = true;
    sidebar.classList.add('collapsed');
    if (main) main.classList.add('expanded');
    return true;
}

function restoreSidebarAfterModal() {
    const sidebar = document.getElementById('sidebar');
    const main = document.getElementById('mainContent');
    if (!sidebar || !sidebarAutoCollapsed) { sidebarAutoCollapsed = false; return; }
    sidebarAutoCollapsed = false;
    if (window.innerWidth <= 768) {
        sidebar.classList.add('show');
    } else {
        sidebar.classList.remove('collapsed');
        if (main) main.classList.remove('expanded');
    }
}

/* repetir: abre um NOVO registro com os dados de um existente, sem o paciente. */
function repeatReg(id) {
    openModal(id, true);
}

function openModal(id = null, repetir = false) {
    const editando = !!id && !repetir;
    ultimoPaciente = '';
    // A lista desliza quando a barra lateral recolhe: medir a coluna "Tipo"
    // antes de ela assentar daria uma posição deslocada.
    if (collapseSidebarForModal()) aguardarLayoutDoModal();
    hideRegNotice();
    limparErrosSelecao();
    isolarPaciente('');
    document.getElementById('regModal').style.display = 'flex';
    document.body.classList.add('reg-modal-aberto');
    resetModalPosition();
    document.getElementById('modalTitle').textContent = editando ? 'Editar Registro' : (repetir ? 'Repetir Registro — escolha o paciente' : 'Novo Registro RAAS');
    document.getElementById('regForm').reset();
    document.getElementById('form-id').value = '';
    document.getElementById('form-patient-id').value = '';
    document.getElementById('patientSearch').value = '';
    document.getElementById('patientResults').style.display = 'none';
    document.getElementById('form-professional-id').value = '';
    document.getElementById('profSearch').value = '';
    document.getElementById('profResults').style.display = 'none';
    resetProcRows();
    updateCamposDoProcedimento();
    const addProcBtn = document.getElementById('addProcBtn');
    addProcBtn.dataset.forceHidden = editando ? '1' : '0';
    addProcBtn.style.display = editando ? 'none' : '';
    const month = document.getElementById('monthPicker').value;
    document.getElementById('form-month').value = month;
    applyMonthLimits();
    if (!id) {
        document.querySelector('[name="service_date"]').value = defaultServiceDate();
    }
    // Abre com o cursor no campo de data: no pt-BR o primeiro segmento é o
    // dia do mês, que fica selecionado em azul pronto para digitar.
    if (!id) document.querySelector('[name="service_date"]').focus();
    if (id) {
        fetch(`/api/registros/${id}`).then(r => r.json()).then(r => {
            for (const [k, v] of Object.entries(r)) {
                if (repetir && (k === 'id' || k === 'patient_id')) continue;
                if (k === 'patient_id') {
                    document.getElementById('form-patient-id').value = v;
                    ultimoPaciente = v;
                    posicionarModalAposTipo(grupoPorPaciente(v));
                    const p = PACIENTES_DATA.find(p => p.id === v);
                    if (p) document.getElementById('patientSearch').value = p.name;
                    continue;
                }
                if (k === 'professional_id') {
                    document.getElementById('form-professional-id').value = v;
                    const prof = PROFISSIONAIS_DATA.find(p => p.id === v);
                    if (prof) document.getElementById('profSearch').value = prof.name;
                    continue;
                }
                if (k === 'procedure_id') {
                    const row = document.querySelector('#procRows .proc-row');
                    const proc = PROCEDIMENTOS_DATA.find(p => p.id === v);
                    row.querySelector('.proc-hidden-id').value = v;
                    row.querySelector('.proc-search-input').value = proc ? proc.label : '';
                    continue;
                }
                if (k === 'quantity') {
                    document.querySelector('#procRows .proc-row input[type="number"]').value = v;
                    continue;
                }
                const el = document.querySelector(`[name="${k}"]`);
                if (el) el.value = v ?? '';
            }
            updateCamposDoProcedimento();
            if (repetir) document.getElementById('patientSearch').focus();
        });
    }
    // Sem paciente escolhido ainda, encosta a janela depois da coluna "Tipo" do
    // grupo que estiver aberto na lista.
    posicionarModalAposTipo();
}

function editReg(id) {
    openModal(id);
}

function closeModal() {
    hideRegNotice();
    limparErrosSelecao();
    const paciente = pacienteIsolado || ultimoPaciente;
    const grupo = grupoPorPaciente(paciente);
    const visivel = grupo && grupo.style.display !== 'none';
    const topoAntes = visivel ? grupo.getBoundingClientRect().top : null;
    isolarPaciente('');
    document.getElementById('regModal').style.display = 'none';
    document.body.classList.remove('reg-modal-aberto');
    restoreSidebarAfterModal();
    if (listRefreshPending) {
        listRefreshPending = false;
        try { if (paciente) sessionStorage.setItem(CHAVE_PACIENTE_ABERTO, paciente); } catch (e) { /* ignore */ }
        location.reload();
        return;
    }
    if (!paciente) return;
    if (topoAntes === null) { mostrarPacienteNaLista(paciente); return; }
    // Os outros pacientes voltam a aparecer acima; compensa a rolagem para o
    // paciente e seus lançamentos ficarem exatamente onde estavam.
    setGrupoAberto(grupo, true);
    window.scrollBy({ top: grupo.getBoundingClientRect().top - topoAntes, behavior: 'auto' });
}

// Depois de um recarregamento vindo do modal, reabre o paciente que estava em lançamento.
(function reabrirPacienteAposRecarregar() {
    let pid = '';
    try {
        pid = sessionStorage.getItem(CHAVE_PACIENTE_ABERTO) || '';
        sessionStorage.removeItem(CHAVE_PACIENTE_ABERTO);
    } catch (e) { /* ignore */ }
    if (pid) mostrarPacienteNaLista(pid);
})();

async function saveReg(e) {
    e.preventDefault();
    const saveButton = e.submitter || document.querySelector('#regForm button[type="submit"]');
    if (saveButton.disabled) return;
    // A mensagem vai em cada campo pendente; o aviso central cobriria justamente
    // os campos que o usuário precisa corrigir.
    if (!validarSelecoes()) return;
    saveButton.disabled = true;
    const form = e.target;
    const data = Object.fromEntries(new FormData(form));
    const id = data.id;
    delete data.id;
    for (const k in data) {
        if (k.startsWith('procedure_id_') || k.startsWith('quantity_')) delete data[k];
    }
    for (const k in data) { if (data[k] === '') delete data[k]; }

    const procRows = Array.from(document.querySelectorAll('#procRows .proc-row')).map(row => ({
        procedure_id: row.querySelector('.proc-hidden-id').value,
        quantity: parseInt(row.querySelector('input[type="number"]').value) || 1,
    })).filter(r => r.procedure_id);

    if (procRows.length === 0) {
        showRegNotice('Selecione ao menos um procedimento', 'error');
        saveButton.disabled = false;
        return;
    }

    const month = data.service_month;
    if (month && data.service_date && data.service_date.slice(0, 7) !== month) {
        showRegNotice(`Data do atendimento fora da competência ${month}`, 'error');
        saveButton.disabled = false;
        return;
    }

    const montarPayload = (r) => ({
        ...data, procedure_id: r.procedure_id, quantity: r.quantity,
    });

    let resp;
    if (procRows.length > 1 && !id) {
        const payloads = procRows.map(montarPayload);
        resp = await fetch('/api/registros/varios', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payloads)
        });
    } else {
        const payload = montarPayload(procRows[0]);
        const url = id ? `/api/registros/${id}` : '/api/registros/';
        const method = id ? 'PUT' : 'POST';
        resp = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
    }

    if (resp.ok) {
        if (data.patient_id) ultimoPaciente = data.patient_id;
        showRegNotice(id ? 'Registro atualizado' : 'Registro(s) criado(s)');
        if (id) {
            // Recarregar a página fecharia todos os grupos; atualizar a lista
            // deixa o paciente aberto para conferir o que mudou.
            try {
                await refreshRegistrosList(data.patient_id);
                listRefreshPending = false;
            } catch (error) {
                listRefreshPending = true;
            }
            setTimeout(closeModal, 800);
            saveButton.disabled = false;
        } else {
            try {
                await refreshRegistrosList(data.patient_id);
                listRefreshPending = false;
            } catch (error) {
                listRefreshPending = true;
                showRegNotice('Registro salvo, mas a lista não foi atualizada', 'error');
            }
            prepareNextRecord(data.service_date, manterDadosMarcado() ? { data, procRows } : null);
            saveButton.disabled = false;
        }
    } else {
        let msg = 'Erro ao salvar';
        try {
            const err = await resp.json();
            if (err.detail) msg = typeof err.detail === 'string' ? err.detail : msg;
        } catch (e) { /* ignore */ }
        showRegNotice(msg, 'error');
        saveButton.disabled = false;
    }
}

async function deleteReg(id) {
    if (!confirm('Excluir este registro?')) return;
    const row = document.querySelector(`tr[data-registro-id="${CSS.escape(id)}"]`);
    const patientId = row?.closest('.registro-group')?.dataset.patientId || '';

    const resp = await fetch(`/api/registros/${id}`, { method: 'DELETE' });
    if (!resp.ok) {
        showToast('Erro ao excluir registro', 'error');
        return;
    }

    showToast('Registro excluído');
    try {
        await refreshRegistrosList(patientId, { scroll: false });
    } catch (error) {
        location.reload();
    }
}

// Caixa "Novo Registro" arrastável — permite manter a lista de pacientes
// visível atrás dela enquanto o profissional preenche o formulário.
function resetModalPosition() {
    const modal = document.querySelector('#regModal .modal');
    if (!modal) return;
    modal.style.position = '';
    modal.style.left = '';
    modal.style.top = '';
    modal.style.margin = '';
}

/* Ao abrir a janela a barra lateral recolhe e a lista desliza junto (transição
   de .main-content). Enquanto isso não termina, a coluna "Tipo" ainda está na
   posição antiga, então os pedidos de posicionamento ficam na fila. */
let layoutDoModalAssentado = true;
let posicionamentoPendente;

function aguardarLayoutDoModal() {
    const main = document.getElementById('mainContent');
    layoutDoModalAssentado = false;
    posicionamentoPendente = undefined;
    const assentar = () => {
        if (layoutDoModalAssentado) return;
        layoutDoModalAssentado = true;
        clearTimeout(limite);
        main?.removeEventListener('transitionend', assentar);
        if (posicionamentoPendente !== undefined) {
            const grupo = posicionamentoPendente;
            posicionamentoPendente = undefined;
            posicionarModalAposTipo(grupo);
        }
    };
    // A transição pode não disparar (barra já recolhida, aba em segundo plano):
    // o limite garante que a janela não fique sem posicionar.
    const limite = setTimeout(assentar, 320);
    main?.addEventListener('transitionend', assentar);
}

/* Cabeçalho "Tipo" que está à vista: o do paciente escolhido ou, enquanto
   nenhum foi escolhido, o do primeiro grupo aberto da lista. */
function colunaTipoVisivel(group) {
    const grupos = Array.from(document.querySelectorAll('.registro-group'));
    for (const escopo of (group ? [group, ...grupos] : grupos)) {
        const th = Array.from(escopo.querySelectorAll('thead th'))
            .find(c => c.textContent.trim().toLowerCase() === 'tipo');
        if (th && th.offsetParent) return th;
    }
    return null;
}

/* Encosta a janela logo depois da coluna "Tipo" da tabela, para data,
   procedimento, profissional e tipo ficarem visíveis ao lado dela. */
function posicionarModalAposTipo(group) {
    if (!layoutDoModalAssentado) { posicionamentoPendente = group || null; return; }
    const modal = document.querySelector('#regModal .modal');
    const overlay = document.getElementById('regModal');
    if (!modal || overlay.style.display === 'none') return;
    const tipo = colunaTipoVisivel(group);
    if (!tipo) return;
    const margem = 8;
    const desejado = tipo.getBoundingClientRect().right + margem;
    const maxLeft = window.innerWidth - modal.offsetWidth - margem;
    if (maxLeft < 0) return; // tela estreita: mantém a posição padrão
    const top = modal.getBoundingClientRect().top;
    modal.style.position = 'fixed';
    modal.style.margin = '0';
    modal.style.left = Math.min(desejado, maxLeft) + 'px';
    modal.style.top = Math.max(margem, top) + 'px';
}

(function initDraggableRegModal() {
    const modal = document.querySelector('#regModal .modal');
    const header = document.querySelector('#regModal .modal-header');
    if (!modal || !header) return;

    let dragging = false;
    let offsetX = 0;
    let offsetY = 0;

    header.addEventListener('mousedown', (e) => {
        if (e.target.closest('.modal-close')) return;
        const rect = modal.getBoundingClientRect();
        dragging = true;
        offsetX = e.clientX - rect.left;
        offsetY = e.clientY - rect.top;
        modal.style.position = 'fixed';
        modal.style.margin = '0';
        modal.style.left = rect.left + 'px';
        modal.style.top = rect.top + 'px';
        document.body.style.userSelect = 'none';
        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (!dragging) return;
        const maxLeft = window.innerWidth - modal.offsetWidth;
        const maxTop = window.innerHeight - modal.offsetHeight;
        const left = Math.max(0, Math.min(e.clientX - offsetX, maxLeft));
        const top = Math.max(0, Math.min(e.clientY - offsetY, maxTop));
        modal.style.left = left + 'px';
        modal.style.top = top + 'px';
    });

    document.addEventListener('mouseup', () => {
        dragging = false;
        document.body.style.userSelect = '';
    });
})();
