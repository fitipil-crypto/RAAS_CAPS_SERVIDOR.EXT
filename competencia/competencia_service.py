"""Monta as três visões da tela "Competência" como blocos de tabela.

Os mesmos ``Bloco`` alimentam a tela e a exportação PDF/CSV/TXT, como nos
demais relatórios do sistema.
"""
from datetime import date

from sqlalchemy.orm import Session

from competencia import regras_raas as regras
from competencia.auditoria_service import (
    ALERTA, BLOQUEIO, INFO, ROTULO_GRAVIDADE, AuditoriaService,
)
from competencia.comparativo_service import ComparativoService
from competencia.periodos import mes_anterior, mes_de, rotulo_mes
from competencia.previsao_service import PrevisaoService
from relatorio.impressao_service import Bloco, Coluna

ABAS = {
    "auditoria": "Auditoria RAAS",
    "comparar": "Comparar meses",
    "previsao": "Previsão",
}
_COR = {BLOQUEIO: "C00000", ALERTA: "B45F06", INFO: "595959"}


def competencia_ou_padrao(valor: str | None, padrao: str) -> str:
    return valor if regras.competencia_valida(valor) else padrao


def _num(v) -> str:
    return f"{v:.1f}".replace(".", ",") if isinstance(v, float) and not float(v).is_integer() else f"{int(v)}"


def _pct(v) -> str:
    return "—" if v is None else f"{v:+.1f}%".replace(".", ",")


def _celula_variacao(linha: dict) -> dict:
    return {"v": _pct(linha["pct"]), "b": linha["destaque"], "cor": ("C00000" if linha["pct"] and linha["pct"] < 0 else "2E7D32") if linha["destaque"] else ""}


class CompetenciaService:

    @staticmethod
    def construir(db: Session, aba: str, month: str | None, mes_b: str | None = None,
                  hoje: date | None = None) -> dict:
        if aba not in ABAS:
            raise ValueError("Aba inválida")
        hoje = hoje or date.today()
        month = competencia_ou_padrao(month, mes_de(hoje))
        fabrica = getattr(CompetenciaService, f"_{aba}")
        resultado = fabrica(db, month, competencia_ou_padrao(mes_b, mes_anterior(month)), hoje)
        resultado.update({"aba": aba, "titulo": ABAS[aba], "competencia": month})
        return resultado

    # ── Auditoria ───────────────────────────────────────────────────
    @staticmethod
    def _auditoria(db, month, _mes_b, hoje):
        r = AuditoriaService.auditar(db, month, hoje)
        colunas = [
            Coluna("gravidade", "Gravidade", 12, centro=True), Coluna("codigo", "Código", 8, centro=True),
            Coluna("grupo", "Onde", 22), Coluna("paciente", "Paciente", 30),
            Coluna("mensagem", "O que foi encontrado", 60), Coluna("correcao", "Como corrigir", 48),
        ]
        linhas = [[
            {"v": ROTULO_GRAVIDADE[a.gravidade], "b": True, "cor": _COR[a.gravidade]}, a.codigo, a.grupo,
            a.paciente, a.mensagem, a.correcao,
        ] for a in r["achados"]]
        c = r["contagem"]
        return {
            "dados": r,
            "resumo": [
                {"icone": "⛔", "valor": c[BLOQUEIO], "label": "Bloqueiam a exportação"},
                {"icone": "⚠️", "valor": c[ALERTA], "label": "Alertas"},
                {"icone": "ℹ️", "valor": c[INFO], "label": "Informativos"},
                {"icone": "📝", "valor": r["total_registros"], "label": "Lançamentos auditados"},
            ],
            "blocos": [Bloco(f"Auditoria RAAS — {rotulo_mes(month)}", colunas, linhas,
                             vazio="Nenhuma inconsistência encontrada.", rotulo_contagem="achado(s)")],
        }

    # ── Comparativo ─────────────────────────────────────────────────
    @staticmethod
    def _comparar(db, month, mes_b, _hoje):
        # A competência escolhida é a mais recente (B); a base de comparação é A.
        r = ComparativoService.comparar(db, mes_b, month)
        a, b = rotulo_mes(r["mes_a"]), rotulo_mes(r["mes_b"])

        def bloco(titulo, rotulo_coluna, linhas, vazio):
            colunas = [Coluna("rotulo", rotulo_coluna, 46), Coluna("a", a, 14, centro=True),
                       Coluna("b", b, 14, centro=True), Coluna("diferenca", "Diferença", 14, centro=True),
                       Coluna("pct", "Variação", 14, centro=True)]
            return Bloco(titulo, colunas, [
                [l["rotulo"], _num(l["a"]), _num(l["b"]), _num(l["diferenca"]), _celula_variacao(l)] for l in linhas
            ], vazio=vazio)

        sem_dados = not (r["metricas"][r["mes_a"]]["lancamentos"] or r["metricas"][r["mes_b"]]["lancamentos"])
        vazio = "Nenhum atendimento nas duas competências."
        return {
            "dados": r,
            "resumo": [
                {"icone": "📝", "valor": _num(r["metricas"][r["mes_b"]]["atendimentos"]), "label": f"Atendimentos em {b}"},
                {"icone": "📅", "valor": _num(r["metricas"][r["mes_a"]]["atendimentos"]), "label": f"Atendimentos em {a}"},
                {"icone": "📈", "valor": _pct(r["linhas"][0]["pct"]), "label": "Variação nos atendimentos"},
            ],
            "blocos": [
                bloco("Resumo comparativo", "Indicador", [] if sem_dados else r["linhas"], vazio),
                bloco("Por profissional", "Profissional", r["por_profissional"], vazio),
                bloco("Por procedimento", "Procedimento", r["por_procedimento"], vazio),
            ],
        }

    # ── Previsão ────────────────────────────────────────────────────
    @staticmethod
    def _previsao(db, month, _mes_b, hoje):
        p = PrevisaoService.prever(db, month, hoje)
        if p["estado"] == "futuro":
            return {"dados": p, "resumo": [], "blocos": [
                Bloco("Previsão", [Coluna("aviso", "Aviso", 80)], [["Competência futura: ainda não há o que prever."]])
            ]}
        faixa = p["faixa"]
        texto_faixa = f"{faixa[0]} a {faixa[2]}" if faixa else "Histórico insuficiente"
        rotulo_proj = "Projeção de fechamento" if p["estado"] == "corrente" else "Total realizado"
        colunas = [Coluna("profissional", "Profissional", 40), Coluna("atual", "Realizado", 14, centro=True),
                   Coluna("projecao", rotulo_proj, 20, centro=True), Coluna("media", "Média (meses anteriores)", 24, centro=True),
                   Coluna("situacao", "Situação", 24)]
        linhas = [[
            l["profissional"], l["atual"], "—" if l["projecao"] is None else l["projecao"],
            "—" if l["media"] is None else l["media"],
            {"v": l["situacao"], "b": l["situacao"] == "Abaixo do ritmo", "cor": "C00000" if l["situacao"] == "Abaixo do ritmo" else ""},
        ] for l in p["profissionais"]]
        return {
            "dados": p,
            "resumo": [
                {"icone": "📝", "valor": p["atual"], "label": "Atendimentos lançados"},
                {"icone": "🔮", "valor": "—" if p["projecao"] is None else p["projecao"], "label": rotulo_proj},
                {"icone": "📊", "valor": "—" if p["media_historica"] is None else p["media_historica"],
                 "label": f"Média dos {p['meses_historico']} meses anteriores"},
                {"icone": "🎯", "valor": texto_faixa, "label": "Faixa esperada (média ± desvio)"},
            ],
            "blocos": [
                Bloco("Resumo da previsão", [Coluna("i", "Indicador", 46), Coluna("v", "Valor", 30, centro=True)], [
                    ["Atendimentos lançados", p["atual"]],
                    ["Dias úteis decorridos / no mês", f"{p['dias_decorridos']} / {p['dias_totais']}"],
                    ["Ritmo (atendimentos por dia útil)", "—" if p["ritmo"] is None else _num(p["ritmo"])],
                    [rotulo_proj, "—" if p["projecao"] is None else p["projecao"]],
                    ["Faixa esperada pelo histórico", texto_faixa],
                    ["Situação", p["situacao"]],
                ]),
                Bloco("Por profissional", colunas, linhas, vazio="Nenhuma produção encontrada."),
            ],
        }
