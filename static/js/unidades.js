// Unidades (CAPS) — cadastro, edição e desativação.
// MODALIDADES vem do template (unidades.html), já com os parâmetros de cada modalidade.

const CAMPOS_UNIDADE = [
    'nome', 'sigla', 'modalidade', 'cnes', 'cnpj', 'uf_code', 'municipio_codigo',
    'municipio_nome', 'populacao', 'destination_organ', 'destination_indicator',
    'versao', 'bdversao', 'leitos_acolhimento', 'observacoes',
];

// id do campo no formulário ('leitos_acolhimento' é 'u_leitos', mais curto na tela)
function campo(nome) {
    const id = nome === 'leitos_acolhimento' ? 'u_leitos' : `u_${nome}`;
    return document.getElementById(id);
}

document.addEventListener('DOMContentLoaded', () => {
    blockEnterSubmit(document.getElementById('formUnidade'));
    const cnes = document.getElementById('u_cnes');
    if (cnes) cnes.addEventListener('input', () => {
        cnes.value = cnes.value.replace(/\D/g, '').slice(0, 7);
    });
});

function abrirUnidade(id = null) {
    const form = document.getElementById('formUnidade');
    form.reset();
    document.getElementById('u_id').value = '';
    document.getElementById('u_descricao_modalidade').innerHTML = '';
    document.getElementById('modalUnidadeTitulo').textContent = id ? 'Editar Unidade' : 'Nova Unidade';
    document.getElementById('modalUnidade').style.display = 'flex';

    if (!id) {
        document.getElementById('u_ativa').checked = true;
        return;
    }
    fetch(`/api/unidades/${id}`).then(r => r.json()).then(u => {
        document.getElementById('u_id').value = u.id;
        CAMPOS_UNIDADE.forEach(nome => {
            const el = campo(nome);
            if (el) el.value = u[nome] ?? '';
        });
        document.getElementById('u_ativa').checked = !!u.ativa;
        descreverModalidade();
    });
}

function fecharUnidade() {
    document.getElementById('modalUnidade').style.display = 'none';
}

// Mostra, dentro do formulário, o que a modalidade escolhida prevê — para quem
// cadastra não precisar consultar a portaria em outra aba.
function descreverModalidade() {
    const alvo = document.getElementById('u_descricao_modalidade');
    const codigo = document.getElementById('u_modalidade').value;
    const m = MODALIDADES.find(x => x.codigo === codigo);
    if (!m) { alvo.innerHTML = ''; return; }

    const porte = m.populacao_minima
        ? `municípios acima de ${m.populacao_minima.toLocaleString('pt-BR')} hab.`
        : 'sem porte definido';
    const permanencia = m.permanencia_dias_corridos
        ? ` Permanência de até ${m.permanencia_dias_corridos} dia(s)` +
          (m.permanencia_dias_intercalados ? ` corridos ou ${m.permanencia_dias_intercalados} intercalados` : '') +
          (m.permanencia_janela_dias ? ` em ${m.permanencia_janela_dias} dias.` : '.')
        : '';
    alvo.innerHTML =
        `<strong>${m.nome}</strong> — ${m.descricao}` +
        `<br><strong>Porte:</strong> ${porte} · <strong>Funcionamento:</strong> ${m.funcionamento}` +
        `<br><strong>Acolhimento noturno:</strong> ${m.leitos}.${permanencia}` +
        `<br><em>${m.fundamento}</em>` +
        (m.observacoes.length ? `<br>⚠️ ${m.observacoes.join(' ')}` : '');
}

async function salvarUnidade(e) {
    e.preventDefault();
    const id = document.getElementById('u_id').value;
    const dados = { ativa: document.getElementById('u_ativa').checked };

    CAMPOS_UNIDADE.forEach(nome => {
        const el = campo(nome);
        if (!el) return;
        const valor = el.value.trim();
        if (valor === '') return;  // campo vazio não é enviado (atualização parcial)
        dados[nome] = (nome === 'populacao' || nome === 'leitos_acolhimento')
            ? parseInt(valor, 10) : valor;
    });
    // Leitos é o único numérico em que zero tem significado (sem acolhimento).
    const leitos = document.getElementById('u_leitos').value.trim();
    if (leitos !== '') dados.leitos_acolhimento = parseInt(leitos, 10);

    const resp = await fetch(id ? `/api/unidades/${id}` : '/api/unidades/', {
        method: id ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(dados),
    });
    const corpo = await resp.json().catch(() => ({}));

    if (!resp.ok) {
        showToast(mensagemDeErro(corpo) || 'Erro ao salvar a unidade', 'error');
        return;
    }
    if (corpo.avisos && corpo.avisos.length) {
        // Avisos de modalidade não impedem o cadastro; ficam visíveis na lista.
        showToast(`Unidade salva com ${corpo.avisos.length} aviso(s) de modalidade`);
    } else {
        showToast(id ? 'Unidade atualizada' : 'Unidade criada');
    }
    fecharUnidade();
    setTimeout(() => location.reload(), 900);
}

// O detail do FastAPI é string (HTTPException) ou lista de erros (validação).
function mensagemDeErro(corpo) {
    const detalhe = corpo && corpo.detail;
    if (!detalhe) return '';
    if (typeof detalhe === 'string') return detalhe;
    if (Array.isArray(detalhe)) {
        return detalhe.map(e => (e.msg || '').replace(/^Value error, /, '')).join(' · ');
    }
    return '';
}

async function desativarUnidade(id, nome) {
    const aviso = `Desativar "${nome}"?\n\n` +
        'A unidade sai do seletor, mas os pacientes, atendimentos e registros dela são ' +
        'preservados — nada é apagado.';
    if (!confirm(aviso)) return;
    const resp = await fetch(`/api/unidades/${id}`, { method: 'DELETE' });
    if (resp.ok) {
        showToast('Unidade desativada');
        setTimeout(() => location.reload(), 900);
    } else {
        showToast('Erro ao desativar', 'error');
    }
}
