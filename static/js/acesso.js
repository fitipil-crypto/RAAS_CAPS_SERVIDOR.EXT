// Controle de Acesso — Usuários
function openModal(id = null) {
    document.getElementById('userModal').style.display = 'flex';
    document.getElementById('modalTitle').textContent = id ? 'Editar Usuário' : 'Novo Usuário';
    document.getElementById('userForm').reset();
    document.getElementById('form-id').value = '';
    document.getElementById('passwordField').style.display = id ? 'none' : 'block';
    if (id) {
        fetch(`/api/usuarios/${id}`).then(r => r.json()).then(u => {
            document.querySelector('[name="name"]').value = u.name;
            document.querySelector('[name="username"]').value = u.username;
            document.querySelector('[name="role"]').value = u.role;
            document.querySelector('[name="active"]').value = u.active ? 'true' : 'false';
            const unidade = document.querySelector('[name="unidade_id"]');
            if (unidade) unidade.value = u.unidade_id || '';
            document.getElementById('form-id').value = u.id;
            alternarUnidade();  // ajusta a obrigatoriedade ao perfil carregado
        });
    } else {
        alternarUnidade();
    }
}

function closeModal() {
    document.getElementById('userModal').style.display = 'none';
}

async function saveUser(e) {
    e.preventDefault();
    const form = e.target;
    const data = Object.fromEntries(new FormData(form));
    const id = data.id;
    delete data.id;
    data.active = data.active === 'true';
    if (id) {
        delete data.password;
        const resp = await fetch(`/api/usuarios/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (resp.ok) { showToast('Usuário atualizado'); closeModal(); setTimeout(() => location.reload(), 800); }
        else { const err = await resp.json().catch(() => ({})); showToast(err.detail || 'Erro ao atualizar', 'error'); }
    } else {
        const resp = await fetch('/api/usuarios/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (resp.ok) { showToast('Usuário criado'); closeModal(); setTimeout(() => location.reload(), 800); }
        else { const err = await resp.json(); showToast(err.detail || 'Erro ao criar', 'error'); }
    }
}

async function deleteUser(id) {
    if (!confirm('Excluir este usuário? Esta ação não pode ser desfeita.')) return;
    const resp = await fetch(`/api/usuarios/${id}`, { method: 'DELETE' });
    if (resp.ok) { showToast('Usuário excluído'); setTimeout(() => location.reload(), 800); }
    else { const err = await resp.json(); showToast(err.detail || 'Erro', 'error'); }
}

function changePassword(userId, userName) {
    document.getElementById('passModal').style.display = 'flex';
    document.getElementById('passModalTitle').textContent = `Alterar Senha — ${userName}`;
    document.getElementById('pass-user-id').value = userId;
    document.getElementById('passForm').reset();
    const currentField = document.getElementById('currentPassField');
    currentField.style.display = (userId === currentUserId) ? 'block' : 'none';
}

function changeOwnPassword() {
    changePassword(currentUserId, currentUserName);
}

function closePassModal() {
    document.getElementById('passModal').style.display = 'none';
}

async function savePassword(e) {
    e.preventDefault();
    const form = e.target;
    const data = Object.fromEntries(new FormData(form));
    const userId = data.user_id;
    delete data.user_id;
    if (!data.current_password) delete data.current_password;

    const resp = await fetch(`/api/usuarios/${userId}/senha`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    if (resp.ok) { showToast('Senha alterada'); closePassModal(); }
    else { const err = await resp.json(); showToast(err.detail || 'Erro', 'error'); }
}

const currentUserId = document.querySelector('.user-badge')?.dataset?.userId || '';
const currentUserName = document.querySelector('.user-name')?.textContent || '';


// Ajuda (ícones "i" e tutoriais): o admin liga/desliga por usuário ou para todos.
async function alternarAjuda(userId, checkbox) {
    const ligar = checkbox.checked;
    checkbox.disabled = true;
    try {
        const resp = await fetch(`/api/usuarios/${userId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ help_enabled: ligar })
        });
        if (!resp.ok) throw new Error();
        checkbox.nextElementSibling.textContent = ligar ? 'Ativa' : 'Desativada';
        showToast(ligar ? 'Ajuda ativada para o usuário' : 'Ajuda desativada para o usuário');
    } catch (e) {
        checkbox.checked = !ligar;
        showToast('Erro ao alterar a ajuda', 'error');
    } finally {
        checkbox.disabled = false;
    }
}

async function ajudaEmLote(ligar) {
    const msg = ligar
        ? 'Ativar a ajuda (ícones i e tutoriais) para todos os usuários não-administradores?'
        : 'Desativar a ajuda (ícones i e tutoriais) para todos os usuários não-administradores?';
    if (!confirm(msg)) return;
    const resp = await fetch('/api/usuarios/ajuda', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: ligar })
    });
    if (resp.ok) { showToast(ligar ? 'Ajuda ativada para todos' : 'Ajuda desativada para todos'); setTimeout(() => location.reload(), 700); }
    else { showToast('Erro ao alterar a ajuda', 'error'); }
}


// ── Edição servidor: lotação do usuário em uma unidade (CAPS) ──
// admin e gestor atendem todas as unidades, então para eles o campo é opcional;
// coordenador e operador atendem uma por vez e precisam da lotação.
function alternarUnidade() {
    const form = document.getElementById('userForm');
    if (!form) return;
    const perfil = form.querySelector('[name="role"]').value;
    const campo = form.querySelector('[name="unidade_id"]');
    if (!campo) return;
    const todas = perfil === 'admin' || perfil === 'gestor';
    const marca = document.getElementById('unidadeObrigatoria');
    const ajuda = document.getElementById('unidadeAjuda');
    campo.required = !todas;
    if (marca) marca.style.display = todas ? 'none' : 'inline';
    if (ajuda) {
        ajuda.textContent = todas
            ? 'Este perfil circula por todas as unidades; a lotação é opcional.'
            : 'Coordenador e operador atendem uma unidade por vez.';
    }
    const opcaoTodas = campo.querySelector('option[value=""]');
    if (opcaoTodas) opcaoTodas.disabled = !todas;
    if (!todas && campo.value === '') campo.selectedIndex = campo.options.length > 1 ? 1 : 0;
}

document.addEventListener('DOMContentLoaded', alternarUnidade);
