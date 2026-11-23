# Histórico de alterações

### Marmitex e Farmácia em lote em Proventos / Descontos

- Botões separados para lançar Marmitex ou Farmácia em lote em Proventos / Descontos.
- Cada formulário mostra somente o desconto escolhido e permite informar valores para vários colaboradores na competência selecionada.
- Campos em branco preservam os valores existentes; `0,00` zera o desconto.
- Atualiza o líquido, preserva os demais descontos e observações, registra auditoria e impede alterações em folha fechada.

Todas as mudanças feitas no projeto desde a versão inicial no Git, da mais antiga para a mais recente.
Para ver o detalhe técnico de qualquer item, use o código do commit: `git show <código>`.

### Executável 1_141: importação do 13º salário por PDF

- Botão disponível somente em novembro e dezembro importa o valor líquido para a coluna do 13º salário, sem alterar o salário mensal.
- PDF do 13º armazenado separadamente e anexado aos demonstrativos junto ao PDF mensal, quando disponível.
- Relatório da folha mantém a coluna de 13º salário e inclui os valores importados.
- O atalho de inicialização prioriza o executável 1_141.

### Executável 1_140: bolinha vermelha nas observações

- Bolinha vermelha substitui [OBS] à direita do colaborador na folha, com espaço mais compacto.
- A mesma bolinha aparece antes do nome no quadro Observações dos colaboradores; nomes e textos permanecem pretos.
- Preservados seleção, rolagem, edição, cores de fundo e bloqueio das folhas fechadas.
- Executável gerado em dist, com cópias atualizadas na pasta principal para uso pelos atalhos existentes.
- O atalho de inicialização prioriza o executável 1_140.

### Executável 1_139: OBS em vermelho

- Somente o marcador [OBS] fica vermelho, inclusive na seleção e em folhas fechadas; nomes e valores continuam pretos.
- Preservados alinhamento à direita, fundos das linhas e comportamento de clique, edição e rolagem da tabela.
- O atalho de inicialização prioriza o executável 1_139.

### Executável 1_138: observações à direita e letras pretas

- [OBS] passa para a direita do nome, alinhado à margem direita de um espaço estreito sem título antes do salário.
- Letras da tabela permanecem pretas em folhas abertas, fechadas, com observações e na seleção; somente o fundo muda de cor. Nomes e textos do painel de observações também ficam pretos.
- Preservados cálculos, relatórios, seleção por lançamento e bloqueio das folhas fechadas.
- O atalho de inicialização prioriza o executável 1_138.

### Executável 1_137: marcação de observações na folha

- Colaboradores com observações na competência recebem **[OBS] antes do nome** na tabela, além do destaque laranja já existente, inclusive em folhas fechadas.
- A marcação permanece visível na linha selecionada e é atualizada ao salvar ou apagar a observação; campos vazios ou apenas com espaços não são marcados.
- Legenda explica a marcação. Nomes cadastrados, cálculos, relatórios e bloqueio das folhas fechadas permanecem iguais.
- O atalho de inicialização prioriza o executável 1_137.

### Executável 1_136: relatório Meta padronizado

- PDF de Meta segue o padrão compacto de empréstimos e adiantamentos, com título e cabeçalhos centralizados, tabela ajustada à área útil e total geral destacado.
- Colunas Colaborador, Data, Valor total e Observações, mantendo filtros, observações, cabeçalho institucional e numeração de páginas.
- O atalho de inicialização prioriza o executável 1_136.

### Executável 1_135: colunas de Meta padronizadas

- Tabela Meta com Colaborador na primeira coluna, seguido de Data, Valor total e Observações.
- Cabeçalhos, alinhamento e ajuste automático de largura seguem empréstimos e adiantamentos; somente Observações ocupa o espaço restante.
- O atalho de inicialização prioriza o executável 1_135.

### Executável 1_134: Meta em lote e inclusões somente para ativos

- Nova opção Cadastrar Meta em lote: um único valor por colaborador, com todos os ativos marcados e possibilidade de desmarcar qualquer pessoa.
- Data e observação comuns ao lote, quantidade selecionada e total; salvamento integral, sem incluir valores na folha.
- Inclusões de empréstimos, adiantamentos, folha e Meta verificam o status ativo ao salvar. Inativos não aparecem como opções de inclusão; registros históricos continuam disponíveis.
- O atalho de inicialização prioriza o executável 1_134.

### Executável 1_133: Proventos / Descontos

- O botão principal Empréstimos passa a se chamar Proventos / Descontos, com largura ajustada para o novo texto e título da seção correspondente.
- As abas internas e os cálculos permanecem iguais. O atalho de inicialização prioriza o executável 1_133.

### Executável 1_132: botões de Meta padronizados

- Meta usa o mesmo botão Cadastrar / ações de empréstimos e adiantamentos, com cadastro, edição e exclusão no menu.
- O PDF permanece separado na área Relatórios; não há mudança nos lançamentos nem na folha.
- O atalho de inicialização prioriza o executável 1_132.

### Executável 1_131: Meta, controle independente da folha

- Nova aba Meta em Adiantamento Salarial, com cadastro, edição e exclusão por colaborador, data, valor e observações.
- Consulta e relatório PDF com filtros por período e colaborador, com total dos lançamentos.
- Armazenamento separado, sem gerar parcelas ou alterar folhas e holerites; preserva os valores históricos existentes.
- O atalho de inicialização prioriza o executável 1_131.

### Colaboradores: dados bancários na tabela principal

- As listas de Ativos e Inativos exibem Banco, Agência e Conta ao lado do PIX, sem precisar abrir o cadastro.
- Agências e contas preservam zeros à esquerda; cadastros sem dados bancários ficam com essas colunas vazias.

### Painel: logo à esquerda do título

- A logo da Revisa fica imediatamente à esquerda do título “Painel de controle”.

### Executável 1_130: logo Revisa à direita do título

- Na primeira aba, a logo da Revisa foi posicionada do outro lado do título “Painel de controle”.
- O atalho de inicialização prioriza o executável 1_130.

### Executável 1_129: logo Revisa no Painel

- A logo da Revisa aparece ao lado do título “Painel de controle” na primeira aba.
- O atalho de inicialização prioriza o executável 1_129.

### Executável 1_128: cadastro de colaboradores reorganizado

- A janela de cadastro e edição de colaboradores foi reorganizada em seções visuais, com campos em colunas, cabeçalho, rolagem e ações fixas.
- O atalho de inicialização prioriza o executável 1_128.

### Executável 1_127: lançamentos por competência e tela salarial simplificada

- Em Empréstimos e Adiantamentos, a lista mostra os contratos com parcela ou quitação na competência selecionada na folha.
- Na tela de Salários e reajustes, foram removidos os campos e a indicação visual do tipo de reajuste, mantendo valores, datas e histórico.
- O atalho de inicialização prioriza o executável 1_127.

## Versão inicial — 22/10/2026

### Executável 1_126: dados bancários e relatório de salários atualizados

- O cadastro de colaboradores inclui banco, agência e conta, disponíveis também no relatório de colaboradores.
- A tela Salários gera um relatório PDF com o salário vigente de cada colaborador ativo.
- O atalho de inicialização prioriza o executável 1_126.

### Dados bancários no cadastro de colaboradores

- O cadastro geral de colaboradores permite informar banco, agência e conta bancária.
- Os dados são preservados na edição e exibidos no relatório de colaboradores.

**Commit `04bd118` — Folha de Pagamento Revisa, versão inicial**

Primeira entrada do projeto no Git, com os arquivos originais:

- `folha_pagamento.py`: aplicativo principal (Python + Tkinter + SQLite).
- `importar_planilha.py`: utilitário para consultar a planilha e gerar relatório de importação.
- `Iniciar_Folha_Pagamento.bat`: atalho para iniciar o programa.
- `LEIA-ME.txt`: manual de uso.
- `requirements.txt`: dependências.
- `logo_revisa.png` e `folha_pagamento.ico`: logo e ícone.
- `.gitignore`: mantém fora do Git os arquivos `.exe`, `.db`, `.spec`, backups e pastas de build.

### Relatório da folha mensal em tabela única

- O PDF da folha mensal agora reúne proventos e descontos em uma única tabela horizontal, em página A4 paisagem.
- O cabeçalho da tabela se repete nas páginas seguintes quando necessário.

### Executável 1_121: quitação de empréstimos e limpeza de observações automáticas

- A aba Empréstimos permite quitar o saldo de empréstimos e adiantamentos, lançando o valor no desconto correspondente e encerrando parcelas futuras.
- A quitação preserva os demais valores da folha, inclusive em competências fechadas, e aparece no demonstrativo e no relatório.
- Observações padrão geradas automaticamente nas folhas são limpas; observações manuais são mantidas.
- O atalho de inicialização prioriza o executável 1_121.

### Executável 1_122: parcelas após ajuste manual e identificação de vales

- Ao cadastrar um novo contrato, parcelas futuras são adicionadas a ajustes manuais anteriores em vez de serem zeradas por eles.
- Adiantamentos passam a ser identificados como “Vale”, sem exibir número de parcela na folha e no holerite.
- O atalho de inicialização prioriza o executável 1_122.

### Executável 1_123: identificação da parcela do empréstimo

- A identificação de parcela de empréstimo mudou de “P” para “Emp” na folha, no holerite e nos relatórios que exibem a parcela.
- Adiantamentos continuam identificados somente como “Vale”.
- O atalho de inicialização prioriza o executável 1_123.

### Executável 1_124: parcelas após alteração de contrato

- Alterações no valor, quantidade de parcelas, início ou tipo de contrato ajustam os descontos manuais anteriores pela diferença entre o cronograma antigo e o novo.
- Parcelas agendadas não ficam mais zeradas por um ajuste zero criado antes da inclusão ou extensão do contrato.
- Corrigido o cálculo de uma parcela de empréstimo em dezembro/2026; a folha permanece em revisão.
- O atalho de inicialização prioriza o executável 1_124.

### Executável 1_125: relatório de adiantamentos salariais

- A aba Empréstimos permite gerar relatório PDF de adiantamentos salariais para um colaborador ou para todos.
- O relatório apresenta valores pagos, parcelas pendentes, próxima parcela e saldo devedor na competência selecionada.
- O atalho de inicialização prioriza o executável 1_125.

### 26/10/2026 — importação contábil e botão DP - Antares

**Commits `6628590` e `bd82114`**

- Na folha mensal, o botão **DP - Antares** abre o fluxo de importação de PDF contábil. O botão tem ícone de documento com seta de importação e fundo vermelho-claro.
- O seletor de arquivos inicia em `C:\Users\Revisa\Documents\CONTROLE FINANCEIRO\RECURSOS HUMANOS\FOLHA DE PGTO`; o usuário ainda pode escolher outro local na janela.
- A leitura é local e reconhece PDFs com texto extraível. A rotina confere a competência, a identificação de um colaborador por página e um valor líquido reconhecido; PDFs digitalizados precisam de OCR externo.
- Os colaboradores e valores identificados são apresentados para conferência antes de salvar. É possível excluir pessoas da importação nessa etapa.
- O líquido importado substitui somente o campo Salário; descontos e demais valores não são extraídos do PDF. A folha fechada, nomes ambíguos e valores não identificados bloqueiam a importação.
- Foram adicionados testes para a leitura do PDF, a conferência da importação e o diretório inicial do seletor.

### Orientação dos relatórios PDF

- Os relatórios PDF usam páginas A4 com tabelas ajustadas à largura útil da página.
- A folha mensal e o relatório anual com todos os colaboradores usam formato paisagem para acomodar os valores.
- A folha mensal reúne proventos e descontos em uma única tabela, com cabeçalho repetido nas páginas seguintes.
- O relatório de salários atualizados mostra somente o salário vigente de cada colaborador ativo, sem valores anteriores ou histórico de reajustes.

## README

| Commit | Alteração |
|---|---|
| `859f75c` | Adiciona o README com funcionalidades, instruções de execução, estrutura de arquivos e cálculo do líquido. |
| `0b29701` | README: cabeçalho com logo. |
| `995eb27` | README: novo título. |
| `fa964ca` | README: título "Folha de Pagamento". |
| `a8adda8` | README: remove o logo. |

## Alterações no programa

### Executável 1_112: relatórios padronizados e endereço completo

- Todos os relatórios passaram a usar o mesmo padrão visual e página A4 horizontal da folha mensal.
- Relatório de colaboradores ficou mais compacto; campos não preenchidos aparecem com “—”, sem células vazias.
- Cadastro e relatório de colaboradores agora separam endereço, número e bairro. O banco recebe os novos campos sem apagar os endereços já cadastrados.

### Executável 1_111: janela adaptada ao monitor

- A janela principal continua abrindo maximizada e agora calcula o tamanho inicial e o mínimo de acordo com a resolução disponível.
- Em monitores menores, a janela pode ser reduzida para que a área de trabalho continue acessível; as telas mantêm a rolagem quando o conteúdo não cabe.

### Telas se adaptam a monitores menores — executável 1_110

- As páginas (Painel, Folha mensal, Colaboradores, Salários e Empréstimos) agora ficam em uma área com rolagem: em telas grandes continuam preenchendo toda a janela; em telas menores (como o notebook) aparecem barras de rolagem, em vez de cortar o conteúdo.
- A roda do mouse rola a página (Shift + roda para os lados); tabelas continuam rolando por conta própria.
- Tamanho mínimo da janela reduzido para 760 × 480.

### Executável 1_109: maximização automática

- A janela principal agora abre maximizada após o acesso.
- Executável atualizado com o ícone do projeto.

### Janela principal maximizada ao entrar

- Após autenticar, a janela principal do programa abre maximizada automaticamente.

### Status das folhas: só "Em revisão" e "Fechada" — `0c0fbb3` (executável 1_97)

- O status "Aberta" deixou de existir. Toda folha que não está fechada fica **"Em revisão"**.
- Folhas novas, folhas criadas automaticamente por parcelas de empréstimo e folhas reabertas passam a ficar "Em revisão".
- Ao abrir o programa, folhas antigas com status diferente de "Fechada" são convertidas para "Em revisão". Com isso, o contador do painel passou a contar todas as folhas pendentes (antes uma folha "Aberta" ficava de fora).
- Textos da tela ajustados ("folha em revisão" no lugar de "folha aberta").

### Painel: total anual fechado e folhas pendentes — `571776a` (executável 1_98)

- Novo bloco **Total anual das folhas fechadas**, com o valor do ano e quantas folhas já estão fechadas (ex.: 9 de 12).
- Novo bloco **Folhas em revisão (falta fechar)**, com a competência, a situação "Em revisão" e o valor líquido de cada folha, mais o total pendente.
- Ao fechar uma folha, ela sai da lista de revisão e entra no total fechado.
- Altura dos gráficos reduzida para os novos blocos caberem na tela.

### Colaboradores com menos botões e relatório anual no painel — `64ec188` (executável 1_99)

- Os 7 botões da tela Colaboradores foram reduzidos a 3: **Novo colaborador**, **Relatório de colaboradores (PDF)** e um menu de ações.
- O menu reúne Editar cadastro, Salário / reajustes, Ativar / inativar e Excluir colaborador. O mesmo menu abre com o clique direito em um colaborador da lista.
- O botão **Relatório anual (PDF)** saiu de Colaboradores e foi para o Painel, com o símbolo **R$**.

### Botão "Cadastro" — `12a72d0` (executável 1_100)

- O botão de ações da tela Colaboradores passou a se chamar **Cadastro**.

### Botão laranja e seta duplicada — `ec7d3dc` (executável 1_101)

- O botão **Cadastro** ficou laranja.
- Removida a seta duplicada: o botão já desenha a própria seta.

### Botão "Cadastro" do mesmo tamanho do vizinho — executável 1_102

- O botão **Cadastro** ficou com o mesmo tamanho do botão **Novo colaborador** ao lado (170 × 39 px).

### Folha mensal sem o botão "Remover lançamento" — executável 1_103

- O botão **Remover lançamento** saiu da barra da Folha mensal, que ficou apenas com **Editar lançamento**.

### Coluna de % de reajuste — executável 1_104 e 1_105

- Na tela **Salários e reajustes**, ao lado de cada coluna "Reajuste - MM/AAAA" há uma coluna "%" (sem data no título) com o percentual de aumento em relação ao salário anterior (o salário anterior para o primeiro reajuste, ou o reajuste anterior para os seguintes).
- No **Relatório folha (PDF)**, o líquido de cada colaborador passou a sair em negrito (o total geral já era em negrito).

### Cópia do banco ao fechar, no local e no Mega — executável 1_106

- Ao fechar o programa, o banco é copiado como `backup_saida.db` para a pasta local (`%LOCALAPPDATA%\FolhaPagamentoRevisa\backups`) e para `Backup Folha Revisa`, na pasta do Mega. Se um dos destinos falhar, o outro continua sendo gravado.

### Carregar a cópia do Mega ao abrir — executável 1_107

- Ao abrir, se o `backup_saida.db` do Mega foi gravado por outro computador (mais novo que a última sincronização registrada neste), o programa pergunta se deve carregá-lo. Antes de carregar, o banco local é guardado em `backups\antes_de_carregar.db`.

### Correção da sincronização no notebook — executável 1_108

- Na primeira abertura em um computador (sem registro de sincronização), o programa agora sempre oferece a cópia do Mega, mesmo que o banco local recém-criado seja mais novo.
- A pasta `Backup Folha Revisa` passou a ser localizada a partir de onde o programa está, e não mais por um caminho fixo do usuário do PC.

### Backup automático do Mega substitui a cópia anterior

- O backup automático a cada 30 dias agora usa sempre `backup_folha.db`, substituindo a cópia anterior em vez de criar arquivos com data e hora no nome.
- Cópias automáticas antigas com o padrão `backup_folha_AAAAMMDD_HHMMSS.db` são removidas quando uma nova cópia é salva.
## Executáveis

Os arquivos `.exe` não são enviados ao Git, por estarem no `.gitignore`. Cada alteração do programa gerou uma versão local, e o atalho da área de trabalho foi apontado para a mais recente:

| Versão | Alteração incluída |
|---|---|
| 1_110 | Páginas com rolagem automática para telas menores |
| 1_109 | Janela principal maximizada após o acesso; ícone atualizado no executável |
| 1_96 | Versão anterior às alterações acima |
| 1_97 | Status "Em revisão" e "Fechada" |
| 1_98 | Painel com total anual fechado e folhas pendentes |
| 1_99 | Tela Colaboradores simplificada e relatório anual no painel |
| 1_100 | Botão renomeado para "Cadastro" |
| 1_101 | Botão laranja e seta única |
| 1_102 | Botão Cadastro do mesmo tamanho do botão vizinho |
| 1_103 | Folha mensal sem o botão Remover lançamento |
| 1_104 | Coluna de % de reajuste |
| 1_105 | Coluna só "%" e totais em negrito no relatório da folha |
| 1_106 | Ao fechar, cópia do banco salva na pasta local e na pasta do Mega |
| 1_107 | Ao abrir, carrega a cópia do Mega se ela for mais nova (outro computador) |
| 1_108 | Correção: primeira abertura no notebook oferece a cópia do Mega; pasta do Mega localizada pelo local do programa |
