# LGPD no RAAS-CAPS

Guia de conformidade com a Lei nº 13.709/2018 (LGPD) para o uso do sistema em rede por
vários profissionais. **Este documento descreve o que o software faz e o que a instituição
precisa fazer**; ele não substitui a avaliação do jurídico/encarregado do serviço.

## 1. Papéis

| Papel | Quem | Onde no sistema |
|-------|------|-----------------|
| Controlador | O CAPS / Secretaria de Saúde responsável | LGPD › Controlador e Encarregado |
| Encarregado (DPO, art. 41) | Pessoa indicada pelo controlador | LGPD › Controlador e Encarregado (aparece no Aviso de Privacidade) |
| Operadores | Profissionais que usam o sistema | Controle de Acesso (perfis admin / coordenador / operador) |

## 2. Dados tratados (registro das operações — art. 37)

| Titular | Dados | Sensível? | Finalidade | Base legal |
|---------|-------|-----------|------------|------------|
| Paciente | Nome, CPF, CNS, nascimento, sexo, raça/cor, filiação, contatos, endereço | Não | Identificação no cuidado e na produção RAAS | Art. 7º, II/III e 11, II |
| Paciente | CID, atendimentos, uso de substâncias, situação de rua, observações | **Sim (saúde)** | Atenção psicossocial e envio ao SUS | Art. 11, II, **f** (tutela da saúde) e **b** (políticas públicas) |
| Profissional | Nome, CPF, CNS, CBO, equipe | Não | Identificação nos atendimentos | Art. 7º, II |
| Usuário do sistema | Nome, login, hash da senha, logs de acesso | Não | Segurança e auditoria | Art. 7º, II e IX |

A base legal fica registrada **por paciente** (`base_legal`), com padrão "tutela da saúde". Consentimento
só deve ser escolhido quando de fato for a base usada.

Compartilhamento: apenas SUS (Secretaria/Ministério da Saúde, via arquivo RAAS/BPA). Não há
transferência internacional, **exceto se o túnel/servidor usado (ngrok, Cloudflare, nuvem) estiver
fora do país — nesse caso o tráfego atravessa esse provedor; avalie com o jurídico (art. 33) e prefira
VPN ou HTTPS próprio.**

## 3. O que o software faz (medidas técnicas, art. 46)

**Acesso e autenticação**
- Login individual; senhas com hash bcrypt; **política de senha** (≥ 6 caracteres, letras e números).
- **Primeiro acesso obrigatório**: o admin inicial e todo usuário criado/redefinido pelo admin trocam
  a senha provisória e **aceitam o Termo de Uso e Confidencialidade** (versão e data ficam gravadas).
  Para exigir novo aceite, aumente `TERMO_VERSAO` em `lgpd/lgpd_service.py`.
- **Bloqueio** da conta por 15 min após 5 senhas erradas; limite de tentativas por IP; mensagem de
  erro única (não revela se o usuário existe/está bloqueado).
- Sessão **expira por inatividade** (30 min) e por tempo máximo (12 h); usuário desativado é
  derrubado na hora; nova sessão a cada login; cookie `SameSite=Lax`, `HttpOnly`, `Secure` com HTTPS.
- `SECRET_KEY` aleatória gerada automaticamente (`secret.key`, fora do git) se não for definida.
- Tela de login **não** mostra mais a senha padrão.

**Proteção na rede**
- Cabeçalhos: CSP, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`,
  `Cache-Control: no-store` (dados pessoais não ficam em cache do navegador), HSTS sob HTTPS.
- Proteção CSRF por verificação de `Origin`/`Referer` + SameSite.
- `X-Forwarded-For` só é aceito com `TRUST_PROXY=true` (evita burlar o limite de tentativas).

**Minimização, auditoria e direitos**
- Perfis com o mínimo necessário (o operador não acessa backup, eventos nem a área LGPD).
- **Trilha de auditoria**: login/logout, criação/edição/exclusão, abertura da ficha do paciente
  (página e API), **exportações** (RAAS, CSV de pacientes, backup, dados do titular), anonimizações e
  aceites do termo. Logs não registram IP nem conteúdo de dados; **não podem ser apagados com menos de 180 dias**.
- **Direitos do titular (art. 18)** em LGPD › Solicitações: registro com **prazo de 15 dias**
  (alerta de atraso), exportação dos dados do titular em JSON (acesso/portabilidade) na ficha do paciente,
  **anonimização** irreversível (admin) e exclusão (já existente).
- **Incidentes (art. 48)**: registro em LGPD › Incidentes.
- **Aviso de Privacidade** público em `/privacidade` (com o encarregado cadastrado).
- Retenção: os atendimentos não são excluídos automaticamente; qualquer exclusão deve ser feita por uma funcionalidade controlada e conforme a política da instituição.

## 4. O que a instituição precisa fazer (checklist de implantação em rede)

1. **HTTPS obrigatório.** Dados de saúde não podem trafegar em HTTP puro numa rede compartilhada.
   Opções: túnel ngrok/Cloudflare (já suportados), proxy reverso (nginx/Caddy) com certificado, ou VPN.
   Depois defina `COOKIE_SECURE=true` e, se houver proxy/túnel, `TRUST_PROXY=true`
   (e `ORIGENS_PERMITIDAS=seu.dominio` se o proxy reescrever o `Host`).
2. **Troque a senha do admin** no primeiro acesso e crie **um usuário por pessoa** (nada de login
   compartilhado). Desative quem sair do serviço.
3. **Preencha o Encarregado** em LGPD e confira o Painel de conformidade (todos ✅).
4. **Disco criptografado** no servidor (BitLocker/LUKS) — o banco SQLite e os backups ficam em texto
   aberto no disco. Restrinja o acesso físico e à pasta do projeto.
5. **Backups**: arquivos `.json`/`.db` contêm todos os pacientes. Guarde em local restrito/criptografado
   e descarte com segurança. O download de backup é auditado.
6. **Firewall**: libere a porta somente para a rede do serviço; não exponha à internet sem HTTPS.
7. **Atualizações**: mantenha Python/dependências em dia (Dependabot já configurado).
8. **Treinamento** dos usuários e guarda dos termos aceitos (o sistema registra o aceite digital).
9. **Incidente**: se houver vazamento/perda de equipamento, registre em LGPD › Incidentes e avalie, com o
   encarregado, a comunicação à **ANPD e aos titulares** (Resolução CD/ANPD nº 15/2024: em regra, 3 dias úteis).
10. **Prontuário**: a eliminação de dados de saúde pode ser limitada por obrigação legal de guarda
    (Lei 13.787/2018 e normas do CFM/Conselhos). Em pedidos de eliminação, prefira a **anonimização**
    e registre a resposta na solicitação.

## 5. Variáveis de ambiente

| Variável | Padrão | Função |
|----------|--------|--------|
| `SECRET_KEY` | gerada em `secret.key` | Assina o cookie de sessão |
| `ADMIN_INITIAL_PASSWORD` | `admin` | Senha inicial do admin (troca obrigatória) |
| `COOKIE_SECURE` | `false` | `true` quando acessado por HTTPS |
| `TRUST_PROXY` | `false` | Confia em `X-Forwarded-*` (proxy/túnel) |
| `ORIGENS_PERMITIDAS` | vazio | Hosts extras aceitos no CSRF |
| `SESSAO_INATIVIDADE_MIN` | `30` | Minutos sem uso até expirar |
| `SESSAO_MAX_HORAS` | `12` | Duração máxima do cookie |

## 6. Limitações conhecidas (não cobertas)

- Sem criptografia **por campo** no banco (use criptografia de disco/PostgreSQL com TDE).
- Sem autenticação em dois fatores.
- Sem controle de acesso por paciente/equipe (todo usuário autenticado vê todos os pacientes do seu perfil);
  a auditoria registra quem abriu cada ficha, mas não impede.
- Lista de pacientes e relatórios exibem CPF/CNS completos aos perfis que acessam essas telas.
- O texto do Termo e do Aviso de Privacidade são modelos: **revise com o jurídico do serviço**.
