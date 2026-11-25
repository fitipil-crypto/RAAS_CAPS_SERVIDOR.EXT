// App — utilidades globais
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const main = document.getElementById('mainContent');
    if (window.innerWidth <= 768) {
        sidebar.classList.toggle('show');
    } else {
        sidebar.classList.toggle('collapsed');
        main.classList.toggle('expanded');
    }
}

document.addEventListener('click', (e) => {
    const sidebar = document.getElementById('sidebar');
    const toggle = document.querySelector('.menu-toggle');
    if (window.innerWidth <= 768 && sidebar.classList.contains('show')) {
        if (!sidebar.contains(e.target) && !toggle.contains(e.target)) {
            sidebar.classList.remove('show');
        }
    }
});

function showToast(msg, type = 'success') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = msg;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

function filterTable() {
    const q = document.getElementById('searchInput').value.toLowerCase();
    const rows = document.querySelectorAll('#pacientesTable tbody tr, #profTable tbody tr, #procTable tbody tr');
    rows.forEach(row => {
        const text = (row.dataset.search || row.textContent || '').toLowerCase();
        row.style.display = text.includes(q) ? '' : 'none';
    });
}

function uppercaseInput(el) {
    const pos = el.selectionStart;
    el.value = el.value.toUpperCase();
    if (pos !== null && typeof el.setSelectionRange === 'function') {
        el.setSelectionRange(pos, pos);
    }
}

function blockEnterSubmit(form) {
    form.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && e.target.tagName !== 'TEXTAREA') {
            e.preventDefault();
        }
    });
}

/* Cola uma caixa de aviso sobre o retângulo visível de um modal, para ela
   ficar centralizada no interior dele mesmo quando o modal foi arrastado,
   rola internamente ou saiu parcialmente da tela. */
function posicionarAvisoSobreModal(wrap, modal) {
    if (!wrap || !modal || wrap.hidden) return;
    const rect = modal.getBoundingClientRect();
    let left = Math.max(rect.left, 0);
    let top = Math.max(rect.top, 0);
    let width = Math.min(rect.right, window.innerWidth) - left;
    let height = Math.min(rect.bottom, window.innerHeight) - top;
    if (width < 260 || height < 120) {
        left = 0;
        top = 0;
        width = window.innerWidth;
        height = window.innerHeight;
    }
    wrap.style.left = `${left}px`;
    wrap.style.top = `${top}px`;
    wrap.style.width = `${width}px`;
    wrap.style.height = `${height}px`;
}

/* Campos que o Enter/Tab podem alcançar, na ordem em que aparecem.
   offsetParent nulo descarta o que está em aba oculta ou escondido. */
function camposFocaveis(raiz) {
    if (!raiz) return [];
    return Array.from(raiz.querySelectorAll('input, select, textarea'))
        .filter(el => !el.disabled && el.type !== 'hidden' && el.tabIndex !== -1 && el.offsetParent !== null);
}

/* Leva o cursor ao campo seguinte ao atual, dentro do mesmo contêiner. */
function focarProximoCampo(atual, raiz) {
    const campos = camposFocaveis(raiz || atual.closest('.tab-content') || atual.form);
    const proximo = campos[campos.indexOf(atual) + 1];
    if (proximo) proximo.focus();
    return proximo || null;
}

/* Leva o cursor ao campo anterior ao atual, dentro do mesmo contêiner. */
function focarCampoAnterior(atual, raiz) {
    const campos = camposFocaveis(raiz || atual.closest('.tab-content') || atual.form);
    const i = campos.indexOf(atual);
    const anterior = i > 0 ? campos[i - 1] : null;
    if (anterior) anterior.focus();
    return anterior;
}

/* A seta esquerda deve voltar ao campo anterior? Nos campos de texto só
   quando o cursor já está no início (sem seleção), para não atrapalhar quem
   está corrigindo o que digitou. Datas, listas e botões voltam direto. */
function setaEsquerdaVolta(e) {
    if (e.key !== 'ArrowLeft' || e.shiftKey || e.ctrlKey || e.altKey || e.metaKey) return false;
    const el = e.target;
    if (el.tagName === 'TEXTAREA') return false;
    let inicio = null;
    let fim = null;
    try {
        inicio = el.selectionStart;
        fim = el.selectionEnd;
    } catch (err) { /* date/number/checkbox não expõem o cursor */ }
    if (inicio === null || inicio === undefined) return true;
    return inicio === 0 && fim === 0;
}

/* Marca no <select> a primeira opção com valor de verdade (pulando o "—"),
   preservando o que já estiver escolhido. */
function escolherPrimeiraOpcao(select) {
    if (select.value) return false;
    const opcao = Array.from(select.options).find(o => o.value !== '');
    if (!opcao) return false;
    select.value = opcao.value;
    select.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
}

/* Primeira sugestão do <datalist> compatível com o que já foi digitado. */
function escolherPrimeiraSugestao(input) {
    const lista = input.list;
    if (!lista || input.value.trim()) return false;
    const opcao = lista.options[0];
    if (!opcao) return false;
    input.value = opcao.value;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
}

function switchTab(tabId, btn) {
    const target = btn || (typeof event !== 'undefined' ? event.target : null);
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    if (target) target.classList.add('active');
    document.getElementById(tabId).classList.add('active');
}

// Date display
document.addEventListener('DOMContentLoaded', () => {
    const dateEl = document.getElementById('currentDate');
    if (dateEl) {
        dateEl.textContent = new Date().toLocaleDateString('pt-BR', { weekday: 'short', day: 'numeric', month: 'short' });
    }
});


// Menu lateral: grupos recolhíveis. O estado fica salvo no navegador e o grupo
// da página atual sempre abre, para o item ativo nunca ficar escondido.
(function initNavGroups() {
    const KEY = 'raasNavFechados';
    let fechados = [];
    try { fechados = JSON.parse(localStorage.getItem(KEY) || '[]'); } catch (e) { fechados = []; }
    document.querySelectorAll('.nav-group').forEach((g) => {
        const temAtivo = !!g.querySelector('.nav-item.active');
        if (temAtivo) {
            // O grupo da página atual permanece visível para não esconder o item ativo.
            g.open = true;
        } else if (fechados.includes(g.dataset.group)) {
            g.open = false;
        }
        g.addEventListener('toggle', () => {
            const atual = new Set(fechados);
            if (g.open) atual.delete(g.dataset.group); else atual.add(g.dataset.group);
            fechados = Array.from(atual);
            try { localStorage.setItem(KEY, JSON.stringify(fechados)); } catch (e) { /* sem storage */ }
        });
    });
})();


// Ajuda contextual: botões .info-tip abrem um popover com a explicação.
(function initInfoTips() {
    let pop = null;
    let origem = null;

    function fechar() {
        if (pop) { pop.remove(); pop = null; }
        if (origem) { origem.setAttribute('aria-expanded', 'false'); origem = null; }
    }

    function abrir(btn) {
        fechar();
        origem = btn;
        btn.setAttribute('aria-expanded', 'true');
        pop = document.createElement('div');
        pop.className = 'info-pop';
        pop.setAttribute('role', 'tooltip');
        const titulo = btn.dataset.tipTitle;
        if (titulo) {
            const t = document.createElement('div');
            t.className = 'info-pop-title';
            t.textContent = titulo;
            pop.appendChild(t);
        }
        const corpo = document.createElement('div');
        corpo.textContent = btn.dataset.tip || '';
        pop.appendChild(corpo);
        if (btn.dataset.tipLink) {
            const a = document.createElement('a');
            a.className = 'info-pop-link';
            a.href = btn.dataset.tipLink;
            a.textContent = 'Ver o tutorial →';
            pop.appendChild(a);
        }
        document.body.appendChild(pop);
        const r = btn.getBoundingClientRect();
        const w = pop.offsetWidth;
        const h = pop.offsetHeight;
        let left = Math.min(Math.max(12, r.left + r.width / 2 - w / 2), window.innerWidth - w - 12);
        let top = r.bottom + 8;
        if (top + h > window.innerHeight - 12) top = Math.max(12, r.top - h - 8);
        pop.style.left = left + 'px';
        pop.style.top = top + 'px';
    }

    document.addEventListener('click', (e) => {
        const btn = e.target.closest('.info-tip');
        if (btn) {
            e.preventDefault();
            e.stopPropagation();
            if (origem === btn) fechar(); else abrir(btn);
            return;
        }
        if (pop && !e.target.closest('.info-pop')) fechar();
    }, true);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') fechar(); });
    window.addEventListener('resize', fechar);
    window.addEventListener('scroll', fechar, true);
})();
