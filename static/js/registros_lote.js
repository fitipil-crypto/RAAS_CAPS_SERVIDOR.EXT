// Registros RAAS — digitação em lote (até 30 pacientes × até 5 procedimentos),
// solta ou dentro de um grupo de atendimento.
(function () {
    const MAX_LINHAS = 30;
    const MAX_PROCS = 5;
    const MAX_SUGESTOES = 50;
    const MAX_PESSOAS_GRUPO = 30; // igual ao limite do schema do grupo
    // Até 5 profissionais por lançamento (10 para o administrador), definido pelo servidor.
    const MAX_PROFS = typeof LOTE_MAX_PROFS === 'number' ? LOTE_MAX_PROFS : 5;
    const AUTH_PROC_CODE = '03.01.08.038-0';
    // 03.01.08.021-6: o atendimento em grupo só entra pelo "Lançar grupo", já escolhido.
    const PROC_GRUPO = PROCEDIMENTOS_DATA.find((p) => String(p.code || '').replace(/\D/g, '') === '0301080216') || null;
    const ehProcGrupo = (id) => !!PROC_GRUPO && id === PROC_GRUPO.id;

    const modal = document.getElementById('loteModal');
    if (!modal) return;
    const tbody = document.getElementById('loteBody');
    const drop = document.getElementById('loteDrop');
    const prof = document.getElementById('loteProf');
    const profsBox = document.getElementById('loteProfs');
    const procInput = document.getElementById('loteProc');
    const procsBox = document.getElementById('loteProcs');
    const authRow = document.getElementById('loteAuthRow');
    const authInput = document.getElementById('loteAuth');
    const barra = document.getElementById('loteGrupoBarra');
    const barraTxt = document.getElementById('loteGrupoTxt');
    const btnEditarGrupo = document.getElementById('loteGrupoEditar');
    const btnSairGrupo = document.getElementById('loteGrupoSair');
    const btnExcluirGrupo = document.getElementById('loteGrupoExcluir');
    const escolherGrupo = document.getElementById('loteGrupoEscolher');
    const btnNovoGrupo = document.getElementById('loteGrupoNovo');
    const grupoModal = document.getElementById('loteGrupoModal');
    const grupoModalTitulo = document.getElementById('loteGrupoModalTitulo');
    const grupoDesc = document.getElementById('loteGrupoDesc');
    const grupoData = document.getElementById('loteGrupoData');
    const grupoHora = document.getElementById('loteGrupoHora');
    const grupoPessoas = document.getElementById('loteGrupoPessoas');
    const gruposBox = document.getElementById('loteGrupos');
    const gruposModoBtn = document.getElementById('loteGruposModo');
    const avulsosBox = document.getElementById('loteAvulsos');
    const abaGrupos = document.getElementById('loteAbaGrupos');
    const abaAvulsos = document.getElementById('loteAbaAvulsos');
    const excessoModal = document.getElementById('loteExcessoModal');
    const excessoTitulo = document.getElementById('loteExcessoTitulo');
    const excessoTxt = document.getElementById('loteExcessoTxt');
    const avisoModal = document.getElementById('loteAvisoModal');
    const avisoTxt = document.getElementById('loteAvisoTxt');
    const summary = document.getElementById('loteSummary');
    const saveBtn = document.getElementById('loteSaveBtn');

    let ac = null; // autocomplete aberto: { input, items, idx }
    let procs = []; // procedimentos do lote: [{ id, label }]
    let profs = []; // profissionais do lote: [{ id, label }]
    let aba = 'grupos'; // aba visível à direita: 'grupos' ou 'avulsos'
    let recentes = new Set(); // registros do último lote salvo (destacados à direita)
    let lancados = []; // registros já salvos na competência (repetição)
    // Registros salvos desde que a caixa foi aberta ou desde o último "Limpar
    // tela": só eles aparecem à direita (Grupos e Avulsos).
    let sessao = new Set();
    let grupos = []; // grupos da competência, com pacientes e procedimentos
    let grupoAtivo = null; // grupo em que o lote está sendo lançado
    let editandoGrupo = null; // grupo aberto na janela de grupo (null = novo)
    let soPacientes = false; // caixa de grupos retraída (só os pacientes)
    const retraidos = new Set(); // grupos fechados um a um

    const norm = (s) => String(s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
    const dataBr = (iso) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`;

    // ── Busca (mesmas fontes do formulário individual) ─────────────────────
    // Relevância do nome: começa com o texto, depois alguma palavra começa com
    // ele, depois contém em qualquer ponto.
    function pesoNome(nome, q) {
        if (nome.startsWith(q)) return 0;
        if (nome.split(/\s+/).some((w) => w.startsWith(q))) return 1;
        return 2;
    }

    function buscar(kind, texto, input) {
        const q = norm(texto);
        if (!q) return [];
        if (kind === 'pac') {
            // Pacientes já escolhidos em outras linhas não aparecem de novo.
            const usados = new Set(Array.from(tbody.querySelectorAll('.l-pac'))
                .filter((el) => el !== input && el.dataset.id).map((el) => el.dataset.id));
            const livres = PACIENTES_DATA.filter((p) => !usados.has(p.id));
            const exato = livres.filter((p) => norm(p.prontuario) === q || norm(p.cns) === q);
            const lista = exato.length ? exato : livres
                .filter((p) => norm(p.name).includes(q) || norm(p.cns).includes(q) || norm(p.prontuario).includes(q))
                .map((p) => ({ p, peso: pesoNome(norm(p.name), q) }))
                .sort((a, b) => a.peso - b.peso || a.p.name.localeCompare(b.p.name, 'pt-BR'))
                .map((x) => x.p);
            return lista.slice(0, MAX_SUGESTOES).map((p) => ({
                id: p.id,
                label: p.name,
                sub: `${p.prontuario ? 'Pront: ' + p.prontuario + ' · ' : ''}CNS: ${p.cns || 's/doc'} · Nasc: ${formatBirthDate(p.birthDate)}`,
            }));
        }
        if (kind === 'proc') {
            // O código também é encontrado sem pontuação (ex.: 0301080216).
            const digitos = q.replace(/\D/g, '');
            const casa = (p) => norm(p.label).includes(q) ||
                (digitos.length >= 3 && digitos === q.replace(/[\s.\-]/g, '') && String(p.code || '').replace(/\D/g, '').includes(digitos));
            // Fora de um grupo o atendimento em grupo nem aparece na busca.
            return PROCEDIMENTOS_DATA.filter((p) => casa(p) && !procs.some((x) => x.id === p.id) && (grupoAtivo || !ehProcGrupo(p.id)))
                .slice(0, MAX_SUGESTOES)
                .map((p) => ({ id: p.id, label: p.label, sub: '' }));
        }
        return PROFISSIONAIS_DATA.filter((p) => norm(p.name).includes(q) && !profs.some((x) => x.id === p.id)).slice(0, MAX_SUGESTOES)
            .map((p) => ({ id: p.id, label: p.name, sub: p.cbo || 's/CBO' }));
    }

    // Destaca o trecho digitado no nome (comparação sem acentos).
    function destacar(texto, q) {
        const i = norm(texto).indexOf(norm(q));
        if (!q.trim() || i < 0) return escapeHtml(texto);
        const n = norm(q).length;
        return escapeHtml(texto.slice(0, i)) + '<mark>' + escapeHtml(texto.slice(i, i + n)) + '</mark>' + escapeHtml(texto.slice(i + n));
    }

    function abrirDrop(input, items) {
        ac = { input, items, idx: 0 };
        if (!items.length) {
            drop.innerHTML = '<div class="autocomplete-empty">Nada encontrado</div>';
        } else {
            const cabecalho = items.length >= MAX_SUGESTOES
                ? `Primeiros ${MAX_SUGESTOES} resultados — continue digitando para filtrar`
                : `${items.length} resultado(s)`;
            drop.innerHTML = `<div class="lote-drop-info">${cabecalho}</div>` + items.map((it, i) =>
                `<div class="autocomplete-item${i === 0 ? ' selected' : ''}" data-i="${i}">
                    <div class="item-name">${destacar(it.label, input.value)}</div>
                    ${it.sub ? `<div class="item-sub">${escapeHtml(it.sub)}</div>` : ''}
                </div>`).join('');
        }
        drop.style.display = 'block';
        posicionarDrop(input);
        drop.scrollTop = 0;
    }

    // Abre para cima quando não cabe embaixo, sempre dentro da janela.
    function posicionarDrop(input) {
        const r = input.getBoundingClientRect();
        const abaixo = window.innerHeight - r.bottom - 12;
        const acima = r.top - 12;
        const paraCima = abaixo < 260 && acima > abaixo;
        const altura = Math.min(420, paraCima ? acima : abaixo);
        drop.style.maxHeight = altura + 'px';
        drop.style.left = r.left + 'px';
        drop.style.width = Math.max(r.width, 320) + 'px';
        drop.style.top = (paraCima ? r.top - 2 - Math.min(altura, drop.scrollHeight) : r.bottom + 2) + 'px';
    }

    function fecharDrop() {
        drop.style.display = 'none';
        ac = null;
    }

    function moverSelecao(delta) {
        if (!ac || !ac.items.length) return;
        ac.idx = (ac.idx + delta + ac.items.length) % ac.items.length;
        drop.querySelectorAll('.autocomplete-item').forEach((el, i) => {
            el.classList.toggle('selected', i === ac.idx);
            if (i === ac.idx) el.scrollIntoView({ block: 'nearest' });
        });
    }

    function escolher(input, item) {
        if (input === procInput) { adicionarProc(item); return; }
        if (input === prof) { adicionarProf(item); return; }
        input.value = item.label;
        input.dataset.id = item.id;
        input.classList.remove('input-invalid');
        input.removeAttribute('title');
        fecharDrop();
        // Mesmo paciente já lançado com a mesma data, profissional, procedimento
        // e grupo: avisa e desfaz a escolha.
        if (input.classList.contains('l-pac')) {
            const iso = parseData(input.closest('tr').querySelector('.l-date').value, selectedMonth());
            const repetidos = duplicadosSalvos(item.id, iso);
            if (repetidos.length) {
                avisarDuplicado(item.label, iso, repetidos, () => {
                    input.value = ''; input.dataset.id = ''; atualizarResumo(); input.focus();
                });
                atualizarResumo();
                return;
            }
        }
        // Paciente além da quantidade de pessoas do grupo: pergunta se amplia;
        // se não, desfaz a escolha e avisa.
        if (input.classList.contains('l-pac') && grupoExcedido()) {
            perguntarExcesso({
                sim: () => focarCelula(input.closest('tr'), 'l-qty'),
                nao: () => { input.value = ''; input.dataset.id = ''; atualizarResumo(); input.focus(); },
            });
        }
        atualizarResumo();
    }

    // ── Procedimentos do lote (chips) ─────────────────────────────────────
    function adicionarProc(item) {
        fecharDrop();
        procInput.value = '';
        procInput.dataset.id = '';
        if (procs.length >= MAX_PROCS) { showToast(`Máximo de ${MAX_PROCS} procedimentos por lote`, 'error'); return; }
        if (!procs.some((p) => p.id === item.id)) procs.push({ id: item.id, label: item.label });
        desenharProcs();
    }

    function desenharProcs() {
        procsBox.innerHTML = procs.map((p, i) =>
            `<span class="lote-chip" title="${escapeHtml(p.label)}"><span>${escapeHtml(p.label)}</span>` +
            `<button type="button" tabindex="-1" data-i="${i}" title="Remover">✕</button></span>`).join('');
        procInput.placeholder = procs.length >= MAX_PROCS ? 'Limite de 5 procedimentos' : 'Buscar procedimento...';
        procInput.classList.remove('input-invalid');
        atualizarAutorizacao();
        atualizarResumo();
    }

    procsBox.addEventListener('click', (e) => {
        const b = e.target.closest('button[data-i]');
        if (!b) return;
        procs.splice(+b.dataset.i, 1);
        desenharProcs();
    });

    // ── Profissionais do lote (chips) ─────────────────────────────────────
    function adicionarProf(item) {
        fecharDrop();
        prof.value = '';
        prof.dataset.id = '';
        if (profs.length >= MAX_PROFS) { showToast(`Máximo de ${MAX_PROFS} profissionais por lançamento`, 'error'); return; }
        if (!profs.some((p) => p.id === item.id)) profs.push({ id: item.id, label: item.label });
        desenharProfs();
    }

    function desenharProfs() {
        profsBox.innerHTML = profs.map((p, i) => {
            const cbo = PROFISSIONAIS_DATA.find((x) => x.id === p.id)?.cbo;
            return `<span class="lote-chip" title="${escapeHtml(p.label)}${cbo ? ' · CBO ' + escapeHtml(cbo) : ''}"><span>${escapeHtml(p.label)}</span>` +
                `<button type="button" tabindex="-1" data-i="${i}" title="Remover">✕</button></span>`;
        }).join('');
        prof.placeholder = profs.length >= MAX_PROFS ? `Limite de ${MAX_PROFS} profissionais` : 'Buscar profissional...';
        prof.classList.remove('input-invalid');
        atualizarResumo();
    }

    profsBox.addEventListener('click', (e) => {
        const b = e.target.closest('button[data-i]');
        if (!b) return;
        profs.splice(+b.dataset.i, 1);
        desenharProfs();
    });

    // O atendimento em grupo entra sozinho ao lançar num grupo e sai ao deixá-lo.
    function aplicarProcDoGrupo() {
        if (!PROC_GRUPO) return;
        const tem = procs.some((x) => ehProcGrupo(x.id));
        if (grupoAtivo && !tem) {
            procs.unshift({ id: PROC_GRUPO.id, label: PROC_GRUPO.label });
            procs = procs.slice(0, MAX_PROCS);
        } else if (!grupoAtivo && tem) {
            procs = procs.filter((x) => !ehProcGrupo(x.id));
        }
        desenharProcs();
    }

    // ── Linhas ─────────────────────────────────────────────────────────────
    function criarLinha(dados = {}) {
        if (tbody.rows.length >= MAX_LINHAS) {
            showToast(`Máximo de ${MAX_LINHAS} pacientes por lote`, 'error');
            return null;
        }
        // Dentro de um grupo a data é a do grupo e não se digita.
        const data = grupoAtivo ? dataBr(grupoAtivo.group_date) : (dados.data || '');
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td class="l-n"></td>
            <td><input class="l-date" inputmode="numeric" placeholder="dd" autocomplete="off" value="${escapeHtml(data)}"${grupoAtivo ? ' readonly tabindex="-1" title="Data do grupo"' : ''}></td>
            <td><input class="l-pac ac" data-kind="pac" placeholder="Paciente (nome, prontuário ou CNS)" autocomplete="off" spellcheck="false" autocorrect="off" autocapitalize="off" value="${escapeHtml(dados.pacLabel || '')}" data-id="${escapeHtml(dados.pacId || '')}">
                <div class="l-msg"></div></td>
            <td><input class="l-qty" type="number" min="1" value="${dados.qty || 1}"></td>
            <td><button type="button" class="btn btn-ghost btn-sm l-del" tabindex="-1" title="Remover linha (Ctrl+Delete)">✕</button></td>`;
        tbody.appendChild(tr);
        numerar();
        return tr;
    }

    function numerar() {
        Array.from(tbody.rows).forEach((tr, i) => { tr.querySelector('.l-n').textContent = i + 1; });
        atualizarResumo();
    }

    function linhaVazia(tr) {
        return !tr.querySelector('.l-pac').value.trim();
    }

    function atualizarResumo() {
        const n = Array.from(tbody.rows).filter((tr) => !linhaVazia(tr)).length;
        const base = n
            ? `${n} paciente(s) × ${procs.length} procedimento(s) × ${profs.length} profissional(is) = ${n * procs.length * profs.length} registro(s)`
            : 'Nenhum paciente preenchido';
        summary.textContent = grupoAtivo
            ? `${base} · Grupo nº ${grupoAtivo.numero}: ${totalNoGrupo()}/${grupoAtivo.people_count} pessoa(s)`
            : base;
    }

    function novaLinhaApos(tr) {
        const ultimaData = tr?.querySelector('.l-date').value || '';
        return criarLinha({ data: ultimaData });
    }

    function focarCelula(tr, classe) {
        const el = tr?.querySelector('.' + classe);
        if (el) { el.focus(); el.select?.(); }
    }

    // ── Datas ──────────────────────────────────────────────────────────────
    function parseData(txt, month) {
        const t = txt.trim();
        if (!t) return null;
        const [y0, m0] = month.split('-').map(Number);
        let d, m = m0, y = y0;
        const partes = t.split(/[\/\-.]/).filter(Boolean);
        if (partes.length === 1) {
            const dg = partes[0].replace(/\D/g, '');
            if (dg.length <= 2) d = +dg;
            else if (dg.length === 4) { d = +dg.slice(0, 2); m = +dg.slice(2); }
            else if (dg.length === 8) { d = +dg.slice(0, 2); m = +dg.slice(2, 4); y = +dg.slice(4); }
            else return null;
        } else {
            d = +partes[0]; m = +partes[1];
            if (partes[2]) { y = +partes[2]; if (y < 100) y += 2000; }
        }
        const dt = new Date(y, m - 1, d);
        if (!d || dt.getFullYear() !== y || dt.getMonth() !== m - 1 || dt.getDate() !== d) return null;
        return `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    }

    function formatarData(input) {
        const iso = parseData(input.value, selectedMonth());
        if (iso) input.value = dataBr(iso);
    }

    // ── Autorização (procedimento de acompanhamento infanto-juvenil) ───────
    function atualizarAutorizacao() {
        const precisa = procs.some((x) => PROCEDIMENTOS_DATA.find((p) => p.id === x.id)?.code === AUTH_PROC_CODE);
        authRow.style.display = precisa ? '' : 'none';
        if (!precisa) authInput.value = '';
    }

    // ── Grupos de atendimento ──────────────────────────────────────────────
    const tituloGrupo = (g) =>
        `Grupo nº ${g.numero} – ${g.description} - Data ${dataBr(g.group_date)} – ${g.group_time} hrs`;

    async function carregarGrupos(manterAtivo = true) {
        try {
            const resp = await fetch(`/api/grupos/?month=${encodeURIComponent(selectedMonth())}`);
            grupos = resp.ok ? await resp.json() : [];
        } catch (err) {
            grupos = [];
        }
        // O grupo ativo é relido da lista: número, pacientes e lotação mudam a cada lote.
        if (manterAtivo && grupoAtivo) grupoAtivo = grupos.find((g) => g.id === grupoAtivo.id) || null;
        desenharGrupos();
        atualizarBarraGrupo();
    }

    function desenharGrupos() {
        gruposBox.classList.toggle('so-pacientes', soPacientes);
        avulsosBox.classList.toggle('so-pacientes', soPacientes);
        gruposModoBtn.textContent = soPacientes ? 'Mostrar atendimentos' : 'Ocultar atendimentos';
        desenharEscolhaDeGrupo();
        // O quadro é só para ver o que foi lançado desde que a caixa foi
        // aberta ou limpa: grupo sem atendimento dessa leva não aparece.
        const visiveis = grupos.filter((g) => g.pacientes.some((p) => p.registros.some((r) => sessao.has(chaveRegistro({ ...r, service_date: g.group_date })))));
        document.getElementById('loteAbaGruposN').textContent = visiveis.length ? `(${visiveis.length})` : '';
        if (!visiveis.length) {
            gruposBox.innerHTML = '<div class="lote-lanc-vazio">Os atendimentos em grupo salvos aparecem aqui.<br>Ao limpar a tela ou fechar a caixa, a lista recomeça.</div>';
            return;
        }
        gruposBox.innerHTML = visiveis.map((g) => {
            const ativo = grupoAtivo && grupoAtivo.id === g.id;
            const fechado = retraidos.has(g.id);
            const cheio = g.pacientes.length >= g.people_count;
            const daSessao = g.pacientes
                .map((p) => ({ ...p, registros: p.registros.filter((r) => sessao.has(chaveRegistro({ ...r, service_date: g.group_date }))) }))
                .filter((p) => p.registros.length);
            const corpo = daSessao.length
                ? daSessao.map((p, i) => `
                    <div class="grp-pac">
                        <div class="grp-pac-nome" title="${escapeHtml(p.patient_name)}">${i + 1}) ${escapeHtml(p.patient_name)}${p.patient_prontuario ? ` <span>– pront: ${escapeHtml(p.patient_prontuario)}</span>` : ''}</div>
                        <ul class="grp-procs">${p.registros.map((r) => `
                            <li><span class="grp-check">✓</span>
                                <span class="grp-proc" title="${escapeHtml((r.procedure_code || '') + ' ' + r.procedure_name)}">${escapeHtml(r.procedure_name)}${r.quantity > 1 ? ` <span class="grp-qtd">${r.quantity}x</span>` : ''}</span>
                                <span class="grp-prof" title="${escapeHtml(r.professional_name)}">${escapeHtml(r.professional_name)}</span></li>`).join('')}
                        </ul>
                    </div>`).join('')
                : '';
            return `<div class="grp-card${ativo ? ' ativo' : ''}${fechado ? ' retraido' : ''}" data-id="${g.id}">
                <div class="grp-cab" data-acao="toggle" title="Clique para fechar ou abrir este grupo">
                    <span class="grp-seta" aria-hidden="true"></span>
                    <span class="grp-titulo" title="${escapeHtml(tituloGrupo(g))}">${escapeHtml(tituloGrupo(g))}</span>
                    <span class="grp-vagas${cheio ? ' cheio' : ''}">${g.pacientes.length}/${g.people_count}</span>
                    ${ativo ? '<span class="grp-usar">● lançando</span>' : ''}
                </div>
                <div class="grp-corpo">${corpo}</div>
            </div>`;
        }).join('');
    }

    // Lista "Grupo já criado…" da barra: é por ela que se escolhe um grupo
    // existente (o quadro da direita é só para visualização).
    function desenharEscolhaDeGrupo() {
        escolherGrupo.innerHTML = '<option value="">Grupo já criado…</option>' + grupos.map((g) =>
            `<option value="${g.id}">${escapeHtml(`Nº ${g.numero} – ${g.description} – ${dataBr(g.group_date)} ${g.group_time} (${g.pacientes.length}/${g.people_count})`)}</option>`).join('');
        escolherGrupo.value = '';
        atualizarBarraGrupo();
    }

    function escolherGrupoExistente(sel) {
        const grupo = grupos.find((g) => g.id === sel.value);
        sel.value = '';
        if (!grupo) return;
        entrarNoGrupo(grupo, grupo.pacientes.length > 0);
        if (!grupo.pacientes.length) {
            showToast(`O grupo nº ${grupo.numero} ainda não tem pacientes lançados: digite os pacientes na grade e salve`, 'info');
        }
    }

    gruposBox.addEventListener('click', (e) => {
        const card = e.target.closest('.grp-card');
        if (!card || !e.target.closest('.grp-cab')) return;
        const grupo = grupos.find((g) => g.id === card.dataset.id);
        if (!grupo) return;
        if (retraidos.has(grupo.id)) retraidos.delete(grupo.id); else retraidos.add(grupo.id);
        desenharGrupos();
    });

    function atualizarBarraGrupo() {
        barra.classList.toggle('ativo', !!grupoAtivo);
        barraTxt.textContent = grupoAtivo
            ? `Lançando no ${tituloGrupo(grupoAtivo)} · ${grupoAtivo.pacientes.length}/${grupoAtivo.people_count} pessoa(s)`
            : 'Lançamento avulso — nenhum grupo selecionado';
        btnEditarGrupo.style.display = grupoAtivo ? '' : 'none';
        btnSairGrupo.style.display = grupoAtivo ? '' : 'none';
        btnExcluirGrupo.style.display = grupoAtivo && !grupoAtivo.total_registros ? '' : 'none';
        // Dentro de um grupo, escolher outro grupo ou criar um novo só depois de
        // "Sair do grupo": a barra mostra apenas o que vale para o grupo atual.
        escolherGrupo.style.display = !grupoAtivo && grupos.length ? '' : 'none';
        btnNovoGrupo.style.display = grupoAtivo ? 'none' : '';
        atualizarResumo();
    }

    // A data das linhas passa a ser a do grupo (ou volta a ser digitável).
    function aplicarDataDoGrupo() {
        const iso = grupoAtivo ? dataBr(grupoAtivo.group_date) : null;
        Array.from(tbody.rows).forEach((tr) => {
            const campo = tr.querySelector('.l-date');
            if (iso) {
                campo.value = iso;
                campo.readOnly = true;
                campo.tabIndex = -1;
                campo.title = 'Data do grupo';
            } else {
                campo.readOnly = false;
                campo.removeAttribute('tabindex');
                campo.removeAttribute('title');
            }
        });
    }

    // comPacientes: a grade já vem com os pacientes do grupo, para lançar mais
    // procedimentos/profissionais para eles.
    function entrarNoGrupo(grupo, comPacientes = false) {
        // Só pergunta se a grade tiver paciente que não é do grupo (seria perdido).
        const doGrupo = new Set(grupo.pacientes.map((p) => p.patient_id));
        const deFora = Array.from(tbody.querySelectorAll('.l-pac')).some((el) => el.value.trim() && !doGrupo.has(el.dataset.id));
        if (comPacientes && deFora && !confirm('A grade tem pacientes que não são deste grupo. Trocar pelos pacientes do grupo?')) return;
        grupoAtivo = grupo;
        retraidos.delete(grupo.id);
        if (comPacientes) {
            tbody.innerHTML = '';
            grupo.pacientes.forEach((p) => criarLinha({ pacLabel: p.patient_name, pacId: p.patient_id }));
        }
        aplicarDataDoGrupo();
        ajustarLinhas(grupo.people_count);
        aplicarProcDoGrupo();
        mostrarAba('grupos');
        desenharGrupos();
        atualizarBarraGrupo();
        gruposBox.querySelector('.grp-card.ativo')?.scrollIntoView({ block: 'nearest' });
        focarCelula(Array.from(tbody.rows).find(linhaVazia) || tbody.rows[0], 'l-pac');
    }

    function sairDoGrupo() {
        grupoAtivo = null;
        aplicarDataDoGrupo();
        aplicarProcDoGrupo();
        desenharGrupos();
        atualizarBarraGrupo();
    }

    // A grade passa a ter uma linha por pessoa do grupo: cria as que faltam e
    // tira as vazias que sobram.
    function ajustarLinhas(n) {
        n = Math.min(n, MAX_LINHAS);
        const data = tbody.rows[tbody.rows.length - 1]?.querySelector('.l-date').value || defaultServiceDateBr();
        while (tbody.rows.length < n) criarLinha({ data });
        for (let i = tbody.rows.length - 1; i >= 0 && tbody.rows.length > n; i--) {
            if (linhaVazia(tbody.rows[i])) tbody.rows[i].remove();
        }
        numerar();
    }

    // ── Janela "Lançar grupo" (nova ou edição) ─────────────────────────────
    function abrirDialogoGrupo(grupo = null) {
        fecharDrop();
        editandoGrupo = grupo;
        grupoModalTitulo.textContent = grupo ? '👥 Editar grupo' : '👥 Lançar grupo';
        document.getElementById('loteGrupoSalvar').textContent = grupo ? 'Salvar alterações' : 'Salvar grupo';
        const month = selectedMonth();
        grupoDesc.value = grupo ? grupo.description : '';
        grupoData.value = grupo ? grupo.group_date : defaultServiceDate();
        grupoHora.value = grupo ? grupo.group_time : '';
        grupoPessoas.value = grupo ? grupo.people_count : '';
        const { first, last } = monthBounds(month);
        grupoData.min = first;
        grupoData.max = last;
        // Mudar a data de um grupo com atendimentos deixaria os registros fora do dia.
        grupoData.disabled = !!(grupo && grupo.pacientes.length);
        [grupoDesc, grupoData, grupoHora, grupoPessoas].forEach((el) => el.classList.remove('input-invalid'));
        grupoModal.style.display = 'flex';
        grupoDesc.focus();
        grupoDesc.select();
    }

    function cancelarGrupo() {
        grupoModal.style.display = 'none';
        editandoGrupo = null;
        prof.focus();
    }

    let salvandoGrupo = false;
    async function confirmarGrupo() {
        if (salvandoGrupo) return;
        const month = selectedMonth();
        const descricao = grupoDesc.value.trim();
        const pessoas = parseInt(grupoPessoas.value, 10);
        let ok = true;
        const marcarSeVazio = (el, valido) => { el.classList.toggle('input-invalid', !valido); if (!valido) ok = false; };
        marcarSeVazio(grupoDesc, !!descricao);
        marcarSeVazio(grupoData, !!grupoData.value && grupoData.value.slice(0, 7) === month);
        marcarSeVazio(grupoHora, /^\d{1,2}:\d{2}$/.test(grupoHora.value));
        marcarSeVazio(grupoPessoas, pessoas >= 1 && pessoas <= MAX_PESSOAS_GRUPO);
        if (!ok) {
            showToast(`Preencha a descrição, uma data da competência ${month.slice(5)}/${month.slice(0, 4)}, o horário e de 1 a ${MAX_PESSOAS_GRUPO} pessoas`, 'error');
            grupoModal.querySelector('.input-invalid')?.focus();
            return;
        }
        const corpo = {
            description: descricao,
            group_date: grupoData.value,
            group_time: grupoHora.value,
            people_count: pessoas,
        };
        salvandoGrupo = true;
        try {
            const editando = editandoGrupo;
            const resp = await fetch(editando ? `/api/grupos/${editando.id}` : '/api/grupos/', {
                method: editando ? 'PUT' : 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(corpo),
            });
            const salvo = await resp.json().catch(() => ({}));
            if (!resp.ok) {
                showToast(typeof salvo.detail === 'string' ? salvo.detail : 'Não foi possível salvar o grupo', 'error');
                return;
            }
            grupoModal.style.display = 'none';
            editandoGrupo = null;
            await carregarGrupos(false);
            const grupo = grupos.find((g) => g.id === salvo.id);
            if (grupo) entrarNoGrupo(grupo);
            showToast(editando ? `Grupo nº ${salvo.numero} atualizado` : `Grupo nº ${salvo.numero} lançado`);
        } finally {
            salvandoGrupo = false;
        }
    }

    async function excluirGrupo(grupo) {
        if (grupo.total_registros) {
            showToast('O grupo tem atendimentos lançados e não pode ser excluído', 'error');
            return;
        }
        if (!confirm(`Excluir o ${tituloGrupo(grupo)}?`)) return;
        const resp = await fetch(`/api/grupos/${grupo.id}`, { method: 'DELETE' });
        const corpo = await resp.json().catch(() => ({}));
        if (!resp.ok) {
            showToast(typeof corpo.detail === 'string' ? corpo.detail : 'Não foi possível excluir o grupo', 'error');
            return;
        }
        if (grupoAtivo && grupoAtivo.id === grupo.id) sairDoGrupo();
        await carregarGrupos();
        showToast('Grupo excluído');
    }

    grupoModal.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); confirmarGrupo(); }
        if (e.key === 'Escape') { e.preventDefault(); cancelarGrupo(); }
    });
    grupoModal.addEventListener('input', (e) => e.target.classList?.remove('input-invalid'));

    // ── Quantidade de pessoas do grupo ─────────────────────────────────────
    function pacientesDoLote() {
        return new Set(Array.from(tbody.querySelectorAll('.l-pac'))
            .filter((el) => el.dataset.id).map((el) => el.dataset.id));
    }

    // Pacientes distintos que o grupo terá: os já lançados mais os do lote.
    function totalNoGrupo() {
        if (!grupoAtivo) return 0;
        const ids = new Set(grupoAtivo.pacientes.map((p) => p.patient_id));
        pacientesDoLote().forEach((id) => ids.add(id));
        return ids.size;
    }

    const grupoExcedido = () => !!grupoAtivo && totalNoGrupo() > grupoAtivo.people_count;

    function avisarExcesso() {
        showToast(`Quantidade de pessoas do grupo nº ${grupoAtivo.numero} excedida`, 'error');
    }

    // Janela "O grupo nº N comporta X pessoas. Deseja ampliar para Y?": Sim
    // aumenta a quantidade de pessoas do grupo; Não mantém (quem chamou desfaz).
    let excessoAcoes = null;

    function perguntarExcesso(acoes = {}) {
        fecharDrop();
        excessoAcoes = acoes;
        const total = totalNoGrupo();
        excessoTitulo.textContent = `O grupo nº ${grupoAtivo.numero} comporta ${grupoAtivo.people_count} pessoa(s).`;
        excessoTxt.textContent = `Deseja ampliar para ${total}?`;
        excessoModal.style.display = 'flex';
        excessoModal.querySelector('.btn-primary').focus();
    }

    async function responderExcesso(sim) {
        excessoModal.style.display = 'none';
        const acoes = excessoAcoes || {};
        excessoAcoes = null;
        if (!sim) {
            avisarExcesso();
            acoes.nao?.();
            return;
        }
        const total = totalNoGrupo();
        if (total > MAX_PESSOAS_GRUPO) {
            showToast(`Máximo de ${MAX_PESSOAS_GRUPO} pessoas por grupo`, 'error');
            acoes.nao?.();
            return;
        }
        const resp = await fetch(`/api/grupos/${grupoAtivo.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ people_count: total }),
        });
        if (!resp.ok) {
            const corpo = await resp.json().catch(() => ({}));
            showToast(typeof corpo.detail === 'string' ? corpo.detail : 'Não foi possível ampliar o grupo', 'error');
            acoes.nao?.();
            return;
        }
        await carregarGrupos();
        ajustarLinhas(Math.max(total, tbody.rows.length));
        showToast(`Grupo nº ${grupoAtivo?.numero ?? ''} ampliado para ${total} pessoa(s)`);
        acoes.sim?.();
    }

    excessoModal.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') { e.preventDefault(); responderExcesso(false); }
    });
    const janelaAberta = () => [grupoModal, excessoModal, avisoModal].some((m) => m.style.display !== 'none');

    // ── Lançamento repetido (mesma data, paciente, profissional, procedimento e grupo) ──
    // Procedimentos do lote que já foram salvos para o paciente nessa data, com
    // o mesmo profissional e no mesmo grupo (a mesma regra do servidor).
    // Devolve as combinações procedimento × profissional já salvas.
    function duplicadosSalvos(pacId, iso) {
        if (!pacId || !iso || !profs.length) return [];
        const grupoId = grupoAtivo ? grupoAtivo.id : null;
        const repetidos = [];
        procs.forEach((x) => profs.forEach((pf) => {
            if (lancados.some((r) => r.service_date === iso && r.patient_id === pacId && r.professional_id === pf.id &&
                r.procedure_id === x.id && (r.group_id ?? null) === grupoId)) repetidos.push({ proc: x, prof: pf });
        }));
        return repetidos;
    }

    let avisoAoFechar = null;

    function avisarDuplicado(nome, iso, repetidos, aoFechar) {
        fecharDrop();
        const itens = repetidos.map(({ proc, prof: pf }) =>
            `<li><strong>${escapeHtml(PROCEDIMENTOS_DATA.find((p) => p.id === proc.id)?.code || proc.label)}</strong> com ${escapeHtml(pf.label)}</li>`).join('');
        avisoTxt.innerHTML = `<strong>${escapeHtml(nome)}</strong> já foi lançado(a) em <strong>${dataBr(iso)}</strong>` +
            `${grupoAtivo ? ` no <strong>Grupo nº ${grupoAtivo.numero}</strong>` : ''}:<ul class="lote-aviso-lista">${itens}</ul>`;
        avisoAoFechar = aoFechar;
        avisoModal.style.display = 'flex';
        avisoModal.querySelector('.btn-primary').focus();
    }

    function fecharAviso() {
        avisoModal.style.display = 'none';
        const fn = avisoAoFechar;
        avisoAoFechar = null;
        fn?.();
    }

    avisoModal.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') { e.preventDefault(); fecharAviso(); }
    });

    // ── Registros já salvos na competência (lançamento repetido) ───────────
    async function carregarLancados() {
        try {
            const resp = await fetch(`/api/registros/?month=${encodeURIComponent(selectedMonth())}`);
            lancados = resp.ok ? await resp.json() : [];
        } catch (err) {
            lancados = [];
        }
        desenharAvulsos();
    }

    // ── Aba "Avulsos": lançamentos fora de grupo, por data e paciente ──────
    const chaveRegistro = (r) => `${r.patient_id}|${r.service_date}|${r.procedure_id}|${r.professional_id}`;

    function desenharAvulsos() {
        const avulsos = lancados.filter((r) => !r.group_id && sessao.has(chaveRegistro(r)));
        document.getElementById('loteAbaAvulsosN').textContent = avulsos.length ? `(${avulsos.length})` : '';
        if (!avulsos.length) {
            avulsosBox.innerHTML = '<div class="lote-lanc-vazio">Nenhum lançamento avulso desde que a tela foi aberta ou limpa.</div>';
            return;
        }
        const pac = new Map(PACIENTES_DATA.map((p) => [p.id, p]));
        const proc = new Map(PROCEDIMENTOS_DATA.map((p) => [p.id, p]));
        const prf = new Map(PROFISSIONAIS_DATA.map((p) => [p.id, p]));
        const dias = new Map();
        avulsos.forEach((r) => {
            if (!dias.has(r.service_date)) dias.set(r.service_date, new Map());
            const porPac = dias.get(r.service_date);
            if (!porPac.has(r.patient_id)) porPac.set(r.patient_id, []);
            porPac.get(r.patient_id).push(r);
        });
        avulsosBox.innerHTML = Array.from(dias.keys()).sort().reverse().map((iso) => {
            const porPac = dias.get(iso);
            const nRegs = Array.from(porPac.values()).reduce((n, l) => n + l.length, 0);
            const fechado = retraidos.has('dia:' + iso);
            const pacientes = Array.from(porPac.entries())
                .map(([id, regs]) => ({ p: pac.get(id), regs }))
                .sort((a, b) => (a.p?.name || '').localeCompare(b.p?.name || '', 'pt-BR'));
            const corpo = pacientes.map(({ p, regs }, i) => `
                <div class="grp-pac${regs.some((r) => recentes.has(chaveRegistro(r))) ? ' novo' : ''}">
                    <div class="grp-pac-nome" title="${escapeHtml(p?.name || '')}">${i + 1}) ${escapeHtml(p?.name || 'Paciente')}${p?.prontuario ? ` <span>– pront: ${escapeHtml(p.prontuario)}</span>` : ''}</div>
                    <ul class="grp-procs">${regs.map((r) => {
                        const pr = proc.get(r.procedure_id);
                        const nomeProc = pr ? pr.label.replace(/^\S+\s+—\s+/, '') : 'Procedimento';
                        return `<li><span class="grp-check">✓</span>
                            <span class="grp-proc" title="${escapeHtml(pr?.label || '')}">${escapeHtml(nomeProc)}${r.quantity > 1 ? ` <span class="grp-qtd">${r.quantity}x</span>` : ''}</span>
                            <span class="grp-prof" title="${escapeHtml(prf.get(r.professional_id)?.name || '')}">${escapeHtml(prf.get(r.professional_id)?.name || '—')}</span></li>`;
                    }).join('')}</ul>
                </div>`).join('');
            return `<div class="avs-dia grp-card${fechado ? ' retraido' : ''}" data-dia="${iso}">
                <div class="grp-cab" title="Clique para fechar ou abrir este dia">
                    <span class="grp-seta" aria-hidden="true"></span>
                    <span class="grp-titulo">📅 ${dataBr(iso)}</span>
                    <span class="grp-vagas">${porPac.size} paciente(s) · ${nRegs} atend.</span>
                </div>
                <div class="grp-corpo">${corpo}</div>
            </div>`;
        }).join('');
    }

    avulsosBox.addEventListener('click', (e) => {
        const dia = e.target.closest('.avs-dia');
        if (!dia || !e.target.closest('.grp-cab')) return;
        const chave = 'dia:' + dia.dataset.dia;
        if (retraidos.has(chave)) retraidos.delete(chave); else retraidos.add(chave);
        desenharAvulsos();
    });

    function mostrarAba(nome) {
        aba = nome;
        gruposBox.style.display = nome === 'grupos' ? '' : 'none';
        avulsosBox.style.display = nome === 'avulsos' ? '' : 'none';
        abaGrupos.classList.toggle('ativo', nome === 'grupos');
        abaAvulsos.classList.toggle('ativo', nome === 'avulsos');
    }

    // ── Teclado e eventos ──────────────────────────────────────────────────
    const primeiraCelula = () => (grupoAtivo ? 'l-pac' : 'l-date');

    function proximo(el) {
        const tr = el.closest('tr');
        // Profissionais: Enter com o campo vazio segue para os procedimentos.
        if (el === prof) { if (!prof.value.trim() && profs.length) procInput.focus(); return; }
        // Procedimentos: Enter com o campo vazio segue para a grade.
        if (el === procInput) {
            if (procInput.value.trim() || !procs.length) return;
            focarCelula(tbody.rows[0], primeiraCelula());
            return;
        }
        if (!tr) { focarCelula(tbody.rows[0], primeiraCelula()); return; }
        if (el.classList.contains('l-date')) return focarCelula(tr, 'l-pac');
        if (el.classList.contains('l-pac')) return focarCelula(tr, 'l-qty');
        // quantidade: segue para o paciente da próxima linha (cria se for a última)
        const prox = tr.nextElementSibling || (tbody.rows.length < MAX_LINHAS ? novaLinhaApos(tr) : null);
        if (prox) focarCelula(prox, 'l-pac'); else saveBtn.focus();
    }

    function moverLinha(el, delta) {
        const tr = el.closest('tr');
        if (!tr) return;
        const alvo = delta > 0 ? tr.nextElementSibling : tr.previousElementSibling;
        if (!alvo) return;
        const classe = ['l-date', 'l-pac', 'l-qty'].find((c) => el.classList.contains(c));
        focarCelula(alvo, classe);
    }

    modal.addEventListener('input', (e) => {
        const el = e.target;
        if (el.classList.contains('ac')) {
            el.dataset.id = '';
            el.classList.remove('input-invalid');
            const items = buscar(el.dataset.kind, el.value, el);
            if (el.value.trim()) abrirDrop(el, items); else fecharDrop();
        }
        el.classList.remove('input-invalid');
        atualizarResumo();
    });

    modal.addEventListener('keydown', (e) => {
        const el = e.target;
        if (e.key === 'Enter' && e.ctrlKey) { e.preventDefault(); salvar(); return; }
        if (e.key === 'Delete' && e.ctrlKey && el.closest('tbody')) {
            e.preventDefault();
            const tr = el.closest('tr');
            const prox = tr.nextElementSibling || tr.previousElementSibling;
            removerLinha(tr);
            if (prox) focarCelula(prox, 'l-pac');
            return;
        }
        const aberto = ac && ac.input === el && drop.style.display !== 'none';
        if (aberto) {
            if (e.key === 'ArrowDown') { e.preventDefault(); moverSelecao(1); return; }
            if (e.key === 'ArrowUp') { e.preventDefault(); moverSelecao(-1); return; }
            if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); fecharDrop(); return; }
            if (e.key === 'Enter' || e.key === 'Tab') {
                const item = ac.items[ac.idx];
                if (item) escolher(el, item);
                else fecharDrop();
                // Procedimentos: continua no campo para escolher o próximo.
                if (e.key === 'Enter') { e.preventDefault(); if (el !== procInput && el !== prof && !janelaAberta()) proximo(el); }
                return;
            }
        }
        if (e.key === 'Enter' && el.tagName === 'INPUT') { e.preventDefault(); proximo(el); return; }
        if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && el.closest('tbody') && el.type !== 'number') {
            e.preventDefault();
            moverLinha(el, e.key === 'ArrowDown' ? 1 : -1);
        }
    });

    modal.addEventListener('focusout', (e) => {
        if (e.target.classList?.contains('l-date')) formatarData(e.target);
        if (e.target.classList?.contains('ac')) setTimeout(() => { if (ac && ac.input === e.target) fecharDrop(); }, 120);
    });

    // O mousedown (não o click) escolhe a opção, antes de o campo perder o foco.
    drop.addEventListener('mousedown', (e) => {
        e.preventDefault();
        const it = e.target.closest('.autocomplete-item');
        if (!it || !ac) return;
        const input = ac.input;
        escolher(input, ac.items[+it.dataset.i]);
        if (janelaAberta()) return;
        if (input.closest('tr')) proximo(input); else input.focus();
    });

    tbody.addEventListener('click', (e) => {
        if (e.target.closest('.l-del')) removerLinha(e.target.closest('tr'));
    });

    // Colar várias linhas (ex.: lista de prontuários/nomes) na coluna Paciente
    tbody.addEventListener('paste', (e) => {
        const el = e.target;
        if (!el.classList.contains('l-pac')) return;
        const linhas = (e.clipboardData.getData('text') || '').split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
        if (linhas.length < 2) return;
        e.preventDefault();
        if (linhas.length > MAX_LINHAS) {
            showToast(`Só os ${MAX_LINHAS} primeiros pacientes foram colados (máximo por lote)`, 'error');
            linhas.length = MAX_LINHAS;
        }
        let tr = el.closest('tr');
        const base = tr.querySelector('.l-date').value;
        linhas.forEach((txt, i) => {
            if (i > 0) tr = tr.nextElementSibling || criarLinha({ data: base });
            if (!tr) return;
            const exatos = PACIENTES_DATA.filter((p) => [p.prontuario, p.cns, p.name].some((v) => v && norm(v) === norm(txt)));
            const campo = tr.querySelector('.l-pac');
            campo.value = exatos.length === 1 ? exatos[0].name : txt;
            campo.dataset.id = exatos.length === 1 ? exatos[0].id : '';
            if (!tr.querySelector('.l-date').value) tr.querySelector('.l-date').value = base;
        });
        atualizarResumo();
        if (grupoExcedido()) {
            perguntarExcesso({
                nao: () => {
                    const campos = Array.from(tbody.querySelectorAll('.l-pac')).filter((i) => i.dataset.id).reverse();
                    for (const c of campos) {
                        if (!grupoExcedido()) break;
                        c.value = ''; c.dataset.id = '';
                    }
                    atualizarResumo();
                },
            });
            return;
        }
        const semId = Array.from(tbody.querySelectorAll('.l-pac')).filter((i) => i.value && !i.dataset.id).length;
        showToast(semId ? `${linhas.length} linhas coladas — ${semId} sem correspondência exata` : `${linhas.length} linhas coladas`, semId ? 'error' : 'success');
    });

    function removerLinha(tr) {
        tr.remove();
        if (!tbody.rows.length) criarLinha({ data: defaultServiceDateBr() });
        numerar();
        atualizarAutorizacao();
    }

    function defaultServiceDateBr() {
        return dataBr(defaultServiceDate());
    }

    // ── Salvar ─────────────────────────────────────────────────────────────
    function marcar(el, msg) {
        el.classList.add('input-invalid');
        el.title = msg;
    }

    function limparErros() {
        modal.querySelectorAll('.input-invalid').forEach((el) => { el.classList.remove('input-invalid'); el.removeAttribute('title'); });
        tbody.querySelectorAll('tr').forEach((tr) => { tr.classList.remove('lote-erro'); tr.querySelector('.l-msg').textContent = ''; });
    }

    function coletar() {
        limparErros();
        const month = selectedMonth();
        const erros = [];
        const itens = [];
        if (!profs.length) { marcar(prof, 'Escolha ao menos um profissional'); erros.push(prof); }
        if (!procs.length) { marcar(procInput, 'Escolha ao menos um procedimento'); erros.push(procInput); }
        if (!grupoAtivo && procs.some((x) => ehProcGrupo(x.id))) {
            marcar(procInput, 'Atendimento em grupo só pelo Lançar grupo');
            showToast('O atendimento em grupo (03.01.08.021-6) só pode ser lançado pelo 👥 Lançar grupo', 'error');
            return null;
        }
        if (grupoExcedido()) { perguntarExcesso({ sim: () => salvar() }); return null; }

        Array.from(tbody.rows).forEach((tr) => {
            if (linhaVazia(tr)) return;
            const dateEl = tr.querySelector('.l-date');
            const pacEl = tr.querySelector('.l-pac');
            const qtyEl = tr.querySelector('.l-qty');
            const msgEl = tr.querySelector('.l-msg');
            const problemas = [];

            const iso = grupoAtivo ? grupoAtivo.group_date : parseData(dateEl.value, month);
            if (!iso) { marcar(dateEl, 'Data inválida'); problemas.push('data inválida'); }
            else if (iso.slice(0, 7) !== month) { marcar(dateEl, 'Fora da competência'); problemas.push('data fora da competência'); }
            if (!pacEl.dataset.id) { marcar(pacEl, 'Escolha o paciente na lista'); problemas.push('paciente não escolhido'); }
            else if (iso && duplicadosSalvos(pacEl.dataset.id, iso).length) {
                marcar(pacEl, 'Já lançado');
                problemas.push('já lançado com a mesma data, profissional, procedimento e grupo');
            }
            const qty = parseInt(qtyEl.value, 10);
            if (!(qty >= 1)) { marcar(qtyEl, 'Quantidade mínima 1'); problemas.push('quantidade inválida'); }

            if (problemas.length) {
                tr.classList.add('lote-erro');
                msgEl.textContent = problemas.join(', ');
                erros.push(tr);
                return;
            }
            // Um registro por procedimento e por profissional do lote.
            procs.forEach(({ id: procId }) => profs.forEach(({ id: profId }) => {
                const profData = PROFISSIONAIS_DATA.find((p) => p.id === profId);
                const item = {
                    service_month: month,
                    service_date: iso,
                    patient_id: pacEl.dataset.id,
                    professional_id: profId,
                    procedure_id: procId,
                    quantity: qty,
                    local_realizacao: document.getElementById('loteLocal').value,
                    srv: document.getElementById('loteSrv').value,
                    cls: document.getElementById('loteCls').value,
                };
                if (grupoAtivo) item.group_id = grupoAtivo.id;
                if (profData?.cbo) item.cbo_code = profData.cbo;
                const proc = PROCEDIMENTOS_DATA.find((p) => p.id === procId);
                if (proc?.code === AUTH_PROC_CODE && authInput.value.trim()) item.authorization = authInput.value.trim();
                itens.push({ tr, item });
            }));
        });

        if (!itens.length && !erros.length) { showToast('Preencha ao menos um paciente', 'error'); return null; }
        if (erros.length) {
            const primeiro = erros[0];
            (primeiro.tagName === 'TR' ? primeiro.querySelector('.input-invalid') : primeiro)?.focus();
            showToast('Corrija os campos destacados', 'error');
            return null;
        }
        return itens;
    }

    let salvando = false;
    async function salvar() {
        if (salvando) return;
        const itens = coletar();
        if (!itens) return;
        salvando = true;
        saveBtn.disabled = true;
        try {
            const resp = await fetch('/api/registros/lote', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ registros: itens.map((x) => x.item) }),
            });
            const corpo = await resp.json().catch(() => ({}));
            if (resp.ok) {
                showToast(`${corpo.criados} registro(s) salvo(s)`);
                recentes = new Set(itens.map((x) => chaveRegistro(x.item)));
                recentes.forEach((k) => sessao.add(k));
                await depoisDeSalvar();
                return;
            }
            if (Array.isArray(corpo.erros) && corpo.erros.length) {
                corpo.erros.forEach((er) => {
                    const alvo = itens[er.linha]?.tr;
                    if (!alvo) return;
                    alvo.classList.add('lote-erro');
                    const msg = alvo.querySelector('.l-msg');
                    if (!msg.textContent.includes(er.mensagem)) msg.textContent = msg.textContent ? `${msg.textContent}; ${er.mensagem}` : er.mensagem;
                });
                showToast(corpo.detail || 'Há linhas com erro', 'error');
                modal.querySelector('.lote-erro')?.scrollIntoView({ block: 'center' });
            } else {
                showToast(typeof corpo.detail === 'string' ? corpo.detail : 'Erro ao salvar o lote', 'error');
            }
        } finally {
            salvando = false;
            saveBtn.disabled = false;
        }
    }

    // Dentro de um grupo os mesmos pacientes costumam receber outro
    // procedimento com outro profissional (é assim que o grupo se monta): a
    // grade continua como está e só o profissional e os procedimentos são
    // limpos. Fora de um grupo, a grade é zerada como antes.
    async function depoisDeSalvar() {
        if (grupoAtivo) {
            prof.value = ''; prof.dataset.id = '';
            profs = [];
            procs = [];
            authInput.value = '';
            desenharProfs();
            aplicarProcDoGrupo();
            mostrarAba('grupos');
            limparErros();
            await Promise.all([carregarGrupos(), carregarLancados()]);
            try { await refreshRegistrosList('', { scroll: false }); } catch (err) { /* lista atualiza ao fechar */ }
            prof.focus();
            return;
        }
        const ultimaData = tbody.rows[tbody.rows.length - 1]?.querySelector('.l-date').value || defaultServiceDateBr();
        tbody.innerHTML = '';
        const nova = criarLinha({ data: ultimaData });
        mostrarAba('avulsos');
        await Promise.all([carregarGrupos(), carregarLancados()]);
        avulsosBox.querySelector('.grp-pac.novo')?.scrollIntoView({ block: 'nearest' });
        try { await refreshRegistrosList('', { scroll: false }); } catch (err) { /* lista atualiza ao fechar */ }
        focarCelula(nova, 'l-pac');
    }

    // ── Abrir / fechar ─────────────────────────────────────────────────────
    async function abrir(grupoId = null) {
        collapseSidebarForModal();
        document.getElementById('loteTitulo').textContent = `Digitação RAAS — competência ${selectedMonth().slice(5)}/${selectedMonth().slice(0, 4)}`;
        tbody.innerHTML = '';
        prof.value = ''; prof.dataset.id = '';
        procInput.value = ''; procInput.dataset.id = '';
        procs = [];
        profs = [];
        recentes = new Set();
        sessao = new Set();
        grupoAtivo = null;
        grupos = [];
        retraidos.clear();
        authInput.value = '';
        limparErros();
        desenharProcs();
        desenharProfs();
        criarLinha({ data: defaultServiceDateBr() });
        mostrarAba('grupos');
        desenharGrupos();
        atualizarBarraGrupo();
        modal.style.display = 'flex';
        prof.focus();
        await Promise.all([carregarGrupos(), carregarLancados()]);
        const grupo = grupoId && grupos.find((g) => g.id === grupoId);
        if (grupo) entrarNoGrupo(grupo, true);
    }

    // Limpa o que foi digitado (grade, profissionais, procedimentos e
    // autorização) sem fechar a janela. Dentro de um grupo, continua no
    // grupo: a grade volta a ter uma linha por pessoa e o atendimento em
    // grupo volta a ser escolhido.
    function limparTela() {
        const temDados = Array.from(tbody.rows).some((tr) => !linhaVazia(tr))
            || profs.length || procs.some((x) => !ehProcGrupo(x.id)) || authInput.value.trim();
        if (temDados && !confirm('Limpar tudo o que foi digitado (pacientes, profissionais e procedimentos)?')) return;
        fecharDrop();
        tbody.innerHTML = '';
        prof.value = ''; prof.dataset.id = '';
        procInput.value = ''; procInput.dataset.id = '';
        profs = [];
        procs = [];
        recentes = new Set();
        sessao = new Set();
        authInput.value = '';
        limparErros();
        desenharProfs();
        criarLinha({ data: defaultServiceDateBr() });
        if (grupoAtivo) {
            aplicarDataDoGrupo();
            ajustarLinhas(grupoAtivo.people_count);
        }
        aplicarProcDoGrupo();
        desenharProcs();
        numerar();
        atualizarAutorizacao();
        atualizarResumo();
        desenharGrupos();
        desenharAvulsos();
        prof.focus();
    }

    function fechar(forcar = false) {
        const temDados = Array.from(tbody.rows).some((tr) => !linhaVazia(tr));
        if (!forcar && temDados && !confirm('Há linhas não salvas. Fechar mesmo assim?')) return;
        fecharDrop();
        grupoModal.style.display = 'none';
        excessoModal.style.display = 'none';
        avisoModal.style.display = 'none';
        modal.style.display = 'none';
        restoreSidebarAfterModal();
    }

    modal.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && drop.style.display === 'none') fechar();
    });
    window.addEventListener('resize', fecharDrop);
    // Ao rolar a grade a lista acompanha o campo (fechar perderia a escolha do Enter).
    modal.querySelector('.lote-grid-wrap').addEventListener('scroll', () => {
        if (ac && drop.style.display !== 'none') posicionarDrop(ac.input);
    });

    window.openLote = abrir;
    window.closeLote = () => fechar();
    window.limparLote = limparTela;
    window.saveLote = salvar;
    window.lancarGrupoLote = () => abrirDialogoGrupo(null);
    window.editarGrupoLote = () => { if (grupoAtivo) abrirDialogoGrupo(grupoAtivo); };
    window.excluirGrupoLote = () => { if (grupoAtivo) excluirGrupo(grupoAtivo); };
    window.escolherGrupoLote = escolherGrupoExistente;
    window.confirmarGrupoLote = confirmarGrupo;
    window.cancelarGrupoLote = cancelarGrupo;
    window.sairDoGrupoLote = sairDoGrupo;
    window.alternarModoGruposLote = () => { soPacientes = !soPacientes; desenharGrupos(); };
    window.mostrarAbaLote = mostrarAba;
    window.responderExcessoLote = responderExcesso;
    window.fecharAvisoLote = fecharAviso;
    window.addLoteRow = () => {
        const nova = novaLinhaApos(tbody.rows[tbody.rows.length - 1]);
        if (nova) focarCelula(nova, 'l-pac');
    };

    // Vindo da tela Grupos ("＋ Novos lançamentos"): abre o lote já no grupo,
    // com os pacientes dele na grade.
    const grupoDaUrl = new URLSearchParams(window.location.search).get('lote_grupo');
    if (grupoDaUrl) {
        history.replaceState(null, '', `${window.location.pathname}?month=${encodeURIComponent(selectedMonth())}`);
        abrir(grupoDaUrl);
    }
})();
