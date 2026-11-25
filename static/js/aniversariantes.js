// Aniversariantes — busca por nome na linha do tempo do mês
function filtrarAniversariantes() {
    const q = document.getElementById('searchInput').value.trim().toLowerCase();
    const timeline = document.getElementById('timeline');
    let visiveis = 0;
    timeline.querySelectorAll('.aniv-dia').forEach(dia => {
        let algum = false;
        dia.querySelectorAll('.aniv-item').forEach(item => {
            const ok = !q || item.dataset.search.includes(q);
            item.style.display = ok ? '' : 'none';
            if (ok) { algum = true; visiveis++; }
        });
        dia.style.display = algum ? '' : 'none';
    });
    const vazio = document.getElementById('semResultado');
    if (vazio) vazio.style.display = (q && visiveis === 0) ? '' : 'none';
}
