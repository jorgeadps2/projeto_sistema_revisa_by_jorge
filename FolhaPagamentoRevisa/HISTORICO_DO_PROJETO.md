# Histórico do projeto

Este documento resume a evolução do aplicativo desde sua entrada inicial no Git, em 22/10/2026, até a versão atual. O histórico técnico detalhado por funcionalidades e versões do executável está em [CHANGELOG.md](./CHANGELOG.md).

## Linha do tempo dos commits

### 22/10/2026 — versão inicial e primeiros ajustes

- `04bd118` — primeira versão do aplicativo de folha de pagamento Revisa, com aplicativo principal, utilitário de planilha, manual, dependências, logo, ícone e atalho para iniciar.
- `859f75c`, `0b29701`, `995eb27`, `fa964ca`, `a8adda8` — criação e ajustes sucessivos do README: descrição do projeto, título e apresentação.
- `0c0fbb3` — padronização do status das folhas: folhas não fechadas ficam “Em revisão”; folhas fechadas permanecem bloqueadas.
- `571776a` — ampliação do painel com total anual de folhas fechadas e relação de folhas pendentes de fechamento.
- `64ec188` — simplificação dos botões de Colaboradores e transferência do relatório anual para o Painel.
- `12a72d0`, `ec7d3dc`, `7fa31c9` — refinamentos do botão de ações de cadastro: nome, cor, seta única e tamanho alinhado aos demais botões.
- `5e12780` — remoção da ação “Remover lançamento” da barra principal da folha mensal.
- `3b2fff8`, `a688e62` — inclusão de percentuais de reajuste salarial e destaque visual dos totais no relatório da folha.
- `a7005e2`, `faae8a8`, `221b10c` — cópias de segurança locais e sincronizadas, recuperação de uma cópia mais recente do Mega e correção da recuperação na primeira abertura de outro computador.
- `1f57ef3` — inclusão do primeiro changelog, para registrar as alterações do projeto.

### 23/10/2026 — documentação

- `9baa3ed` — ampliação do README com autoria e informações gerais do projeto.

### 26/10/2026 — importação contábil e atualização da interface

- `6628590` — integração da importação local de valores líquidos a partir de PDFs contábeis, com conferência dos nomes e valores antes de salvar; atualização da interface, testes, dependências, documentação e configuração de build.
- `bd82114` — ajuste visual do botão DP - Antares, configuração da pasta inicial para selecionar PDFs e inclusão deste histórico do projeto.

## Áreas de evolução

As mudanças funcionais detalhadas estão no [CHANGELOG.md](./CHANGELOG.md). Em resumo, o projeto evoluiu nas seguintes áreas:

- **Folha, painéis e relatórios:** estados das folhas, totais anuais, controles de fechamento e melhorias na apresentação dos PDFs.
- **Colaboradores e salários:** simplificação das ações, histórico de salários, reajustes e relatórios.
- **Empréstimos e adiantamentos:** parcelas, ajustes, quitação e acompanhamento dos saldos.
- **Experiência de uso e dados:** adaptação a diferentes monitores e backups locais/sincronizados.
- **Documentos:** assinatura digital opcional, preparação assistida de holerites e importação local de PDFs contábeis.

O build do executável usa `FolhaPagamentoRevisa_1_125.spec`. Bancos de dados de trabalho, backups, certificados e executáveis compilados ficam fora do histórico versionado. Para instruções de uso, consulte [README.md](./README.md) e [LEIA-ME.txt](./LEIA-ME.txt).
