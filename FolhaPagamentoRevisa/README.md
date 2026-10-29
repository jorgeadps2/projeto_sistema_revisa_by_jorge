<h1 align="center">Folha de Pagamento <code>REVISA</code></h1>

<p align="center">Controle de folha, colaboradores, salários e empréstimos para Windows</p>

Aplicativo desktop para Windows para controle de folha de pagamento mensal, colaboradores, salários e empréstimos. Feito em **Python + Tkinter + SQLite**, com relatórios em PDF gerados com **ReportLab**.

Desenvolvido por Jorge Alberto de Paula.

## Funcionalidades

O Painel mantém os atalhos em uma linha horizontal. As demais abas usam uma coluna compacta de ações à esquerda, com botões empilhados e de mesma largura, e tabelas e filtros à direita. Os botões são compactos: azul para ações principais, cinza-azulado para relatórios e ações secundárias, verde para WhatsApp e fechamento da folha. Menus de cadastro agrupam operações do colaborador ou contrato selecionado.

A barra superior tem fundo no azul da logo Revisa (#004B97) e botões claros, com a aba selecionada destacada no laranja da logo (#FF4500).

- **Acesso protegido por senha**, criada na primeira abertura (mínimo de 8 caracteres).
- Ao abrir pela **Central de Sistemas REVISA**, use esta mesma senha na tela principal; os sistemas Folha e Energia e Água abrem diretamente pelos respectivos botões, sem pedir a senha novamente. A inicialização direta de cada aplicativo continua protegida pela própria tela de acesso.
- No Windows, as janelas abertas pela Central ficam encaixadas abaixo dos botões, com bordas e barra de título dentro da área disponível. Elas acompanham o tamanho e a posição da Central, sem cobrir a barra superior nem o rodapé.
- A aba **Sobre** reúne identificação, versão, desenvolvedor, finalidade e localização do banco de dados. Na Folha de Pagamento, essas informações substituem o rodapé, liberando mais espaço para o conteúdo.
- Após o acesso, o programa abre no **Painel**, sem botões de relatório. O visual clássico usa atalhos com ícones coloridos no topo, sem tela Início e sem barra de menus. Nas demais abas, os botões de PDF ficam na parte inferior da coluna esquerda, separados das demais ações, dentro da moldura **Relatórios**, com ícones de PDF em vermelho e a cor cinza-azulada dos botões preservada: Folha e Holerites na Folha mensal, Colaboradores no cadastro, Reajustes em Salários e Por colaborador em Empréstimos. A barra de informações permanece no rodapé.
- A janela principal abre maximizada após o acesso, ajusta seu tamanho mínimo ao monitor e mantém barras de rolagem quando o conteúdo não cabe.
- **Painel** com logo da Revisa à esquerda do título, colaboradores ativos, total líquido e colaboradores lançados na competência, com gráficos dos 12 meses.
- **Folha mensal**
  - Colaboradores ativos entram automaticamente na folha.
  - Lançamento de salário, PF/adicional, hora extra, férias, marmitex, vales, farmácia, empréstimo e outros descontos.
  - 13º salário nas folhas de novembro e dezembro.
  - Fechar e reabrir folha (com registro do motivo). Folha fechada fica verde e bloqueada para edição; linhas que precisam de conferência ficam amarelas. A ação de quitação atualiza somente o desconto correspondente e mantém a folha fechada.
  - Colaboradores com observações no lançamento da competência aparecem com **uma bolinha vermelha (●), alinhada à direita após o nome**, em um espaço estreito sem título antes do salário, e linha laranja, inclusive em folhas fechadas. A mesma bolinha vermelha aparece antes de cada nome em **Observações dos colaboradores**, abaixo da tabela. Nomes e valores permanecem pretos, mesmo na linha selecionada; somente o marcador fica vermelho. A marcação desaparece ao apagar a observação. Nomes cadastrados e relatórios não são alterados.
  - **Holerites (PDF)** permite escolher um colaborador da competência ou **Todos os colaboradores**, e então usar **Gerar PDF** para abrir o relatório.
  - Na lista de holerites salvos, depois de abrir a primeira conversa, anexar o PDF e confirmar o envio no WhatsApp, use **Próximo colaborador** para abrir a próxima conversa e localizar o arquivo correspondente. O programa não verifica a entrega e não envia automaticamente; ao chegar ao fim da lista, informa que não há mais colaboradores.
  - A conversa abre no **aplicativo WhatsApp para Windows**, usando links `whatsapp://`, não no navegador. O aplicativo precisa estar instalado, conectado e associado a esse protocolo nas configurações do Windows. Se não for possível abri-lo, o programa informa o erro, sem redirecionar para o WhatsApp Web.
  - Os PDFs preparados pelo botão **WhatsApp** ficam em `%LOCALAPPDATA%\FolhaPagamentoRevisa\Relatorios ZAP`, em uma subpasta nova por lote. A pasta é criada automaticamente ao salvar. Na lista dos PDFs salvos, **Abrir WhatsApp do selecionado** abre a conversa e a pasta com o PDF correto selecionado para anexar manualmente.
  - **Compartilhar holerites pelo WhatsApp**: na barra de ações acima da tabela, use **WhatsApp**, selecione os colaboradores ou use **Selecionar todos**. Cada PDF é salvo em uma nova subpasta, sem substituir lotes anteriores. A lista resultante mostra colaborador, telefone cadastrado e arquivo. Selecione uma linha e clique em **Abrir WhatsApp do selecionado** para abrir a conversa e o Explorador com aquele PDF selecionado no Windows. Arraste o arquivo para a conversa, confira o destinatário e confirme o envio. **Localizar PDF** também funciona sem telefone cadastrado. Nenhum arquivo é anexado ou enviado automaticamente. Envie somente a colaboradores que autorizaram receber o holerite pelo WhatsApp.
- **Colaboradores**: cadastro completo (CPF, CTPS, endereço, número, bairro, dados bancários — banco, agência e conta —, PIX, telefone, datas), em uma janela organizada por seções com campos em colunas; abas de Ativos e Inativos. Banco, agência e conta também aparecem na tabela principal, ao lado do PIX; use a barra de rolagem horizontal para consultar as colunas à direita.
- **Salários e reajustes**: histórico de reajustes por colaborador, com valores e datas, sem campos de tipo ou cores por tipo. O PDF **Salários atualizados** mostra somente o salário vigente na competência atual para cada colaborador ativo.
- **Empréstimos e adiantamentos**: contratos, parcelas, ajustes de saldo, quitação antecipada com lançamento do saldo no desconto correspondente da competência selecionada e encerramento das parcelas futuras. A lista mostra somente contratos com parcela ou quitação na competência selecionada na folha, separando visualmente os lançamentos de cada mês. A quitação preserva salário e demais valores da folha, inclusive quando ela está fechada. O **Relatório Geral por Colaborador** pode ser emitido por colaborador ou para todos, em versão compacta, com empréstimos e adiantamentos em tabelas separadas: o que falta pagar, o já pago e a lista das parcelas pendentes de cada tipo. Também pode ser emitido somente para um mês escolhido.
- Na folha e no holerite, adiantamentos aparecem como **Vale** sem número de parcela; ao cadastrar ou alterar um contrato, ajustes manuais antigos são reconciliados com as parcelas futuras.
- Na aba Empréstimos, o botão **Cadastrar** reúne **Cadastrar empréstimo**, **Cadastrar adiantamento**, **Cadastrar adiantamento em lote**, **Editar**, **Excluir** e **Quitar saldo**. Para editar, excluir ou quitar, selecione antes o lançamento na tabela.
- A aba **Adiantamentos** exibe uma tabela única com **Valor total**, **Já descontado**, **Falta descontar** e **Situação** (Pendente, Parcial ou Quitado), com filtro **Pendentes / Quitados**, inicialmente em Pendentes. Os valores consideram descontos confirmados em folhas fechadas e quitações até a competência selecionada; o filtro Pendentes inclui os parciais. Apenas o vencimento do cronograma não torna um adiantamento quitado. Os empréstimos ficam em uma aba própria.
- **Meta**: em **Proventos / Descontos → Meta**, use **Cadastrar / ações → Cadastrar Meta** para informar colaborador, data, valor e observações. No mesmo menu, **Editar** e **Excluir** atuam sobre o lançamento selecionado, seguindo o padrão de botões de empréstimos e adiantamentos. Os registros ficam em uma tabela própria do banco e **não entram na folha, nos descontos, no líquido ou no holerite**, mesmo em competências fechadas. O campo antigo de Meta de folhas históricas não é alterado por este controle. Para consultar, informe as datas inicial e final (DD/MM/AAAA), selecione um colaborador ou todos e clique em **Filtrar**. O botão **Meta (PDF)**, na área **Relatórios**, usa esses mesmos filtros e mostra os lançamentos, observações e total do período. Colaboradores inativos continuam disponíveis para consulta do histórico. Os registros acompanham o backup normal do banco.
- **Meta em lote**: use **Proventos / Descontos → Meta → Cadastrar / ações → Cadastrar Meta em lote**. Informe uma data, um único valor por colaborador e a observação do lote. Todos os ativos começam marcados; desmarque qualquer pessoa que não deve receber ou use **Selecionar todos / Desmarcar todos**. A tela mostra a quantidade selecionada e o total. **Salvar lote** cria um registro separado por colaborador, sem substituir lançamentos anteriores nem alterar a folha. Se a seleção estiver vazia, algum dado for inválido ou alguém tiver sido inativado antes de salvar, nenhum registro do lote é salvo.
- **Relatório de Meta**: PDF retrato no padrão compacto de empréstimos e adiantamentos, com cabeçalho institucional, colunas Colaborador, Data, Valor total e Observações, cabeçalhos repetidos em novas páginas, total geral destacado e páginas numeradas. Usa os filtros de período e colaborador da tela e mantém a indicação de que os valores não integram a folha.
- **Somente ativos nas inclusões**: as seleções de colaborador para novos proventos, descontos, empréstimos, adiantamentos e Meta mostram somente ativos. O status é conferido novamente ao salvar. O histórico dos inativos é preservado em consultas e relatórios; na edição de registros históricos de folha e Meta, o nome inativo aparece como identificação fixa, não como opção de inclusão.
- **Adiantamentos em lote**: na aba Empréstimos, use **Cadastrar → Cadastrar adiantamento em lote** para preencher uma tabela com um valor diferente por colaborador ativo. Defina mês/ano do desconto para todo o lote; cada valor será descontado integralmente nessa competência, sem opção de parcelamento. Campos vazios ou zerados são ignorados. **Salvar lote** cadastra os adiantamentos e atualiza os descontos na folha em uma única operação. Cada salvamento cria novos contratos, sem substituir os anteriores. Se algum dado for inválido ou a folha escolhida estiver fechada, nenhum lançamento do lote é salvo.
- **Observações das folhas**: mensagens padrão geradas pelo sistema são removidas; observações escritas manualmente são preservadas. Na inclusão ou edição de um lançamento, use a área ampliada de observações para escrever várias notas, uma por linha; o campo pode ser redimensionado junto com a janela.
- **Relatórios em PDF**
  - Todas as páginas são numeradas no formato **Página 1 de 3**, inclusive nos relatórios com várias folhas. O carimbo de assinatura digital fica apenas na última página; a assinatura digital valida o PDF inteiro.
  - A folha mensal reúne proventos e descontos em uma única tabela horizontal, em formato paisagem; o cabeçalho se repete nas páginas seguintes quando necessário.
  - Os demais relatórios são gerados em formato retrato, exceto o relatório anual de todos os colaboradores, que também usa paisagem para acomodar os valores mensais.
  - Folha mensal completa.
  - Holerite por colaborador (inclui a situação do empréstimo, quando houver). Nas descrições de empréstimo e adiantamento, as parcelas previstas do mês são discriminadas com número e valor individual, incluindo quitações. A coluna de descontos mantém o valor efetivamente lançado na folha, inclusive ajustes manuais.
  - Relatório anual: tabela única com a soma do ano de todos os colaboradores, ou meses lado a lado para um colaborador.
  - Relatório de colaboradores, de salários atualizados e Relatório Geral por Colaborador de empréstimos e adiantamentos, com opção de período mensal.
  - No Relatório Geral por Colaborador, as colunas respeitam as margens e os textos e valores longos quebram dentro das células, sem sobreposição. As fontes das tabelas são de 5 a 5,5 pontos e há um espaço de 8 mm após cada tabela para separar melhor as seções.
  - **Assinatura digital (opcional)**: ao abrir qualquer PDF, o sistema pergunta se você deseja assinar. Com "Sim", o PDF é assinado com o certificado digital (.pfx) e recebe um carimbo visível, com a logo da Revisa, no canto inferior direito da última página; com "Não", abre normalmente, sem assinatura. A validade do certificado aparece em vermelho no canto direito da barra de botões da Central Revisa, com aviso quando estiver a 30 dias do vencimento ou vencido. A validade é lida do certificado na primeira assinatura e guardada (sem a senha). O certificado não fica dentro do programa: é lido da pasta `Documents\CONTROLE FINANCEIRO\CERTIFICADO DIGITAL\2026` ou do caminho informado em `%LOCALAPPDATA%\FolhaPagamentoRevisa\assinatura_digital.json` (`{"certificado": "C:\\caminho\\arquivo.pfx"}`). A senha é pedida uma vez por sessão e nunca é gravada. Sem certificado ou sem senha, o PDF abre normalmente, sem assinatura.
- **Backup** manual e automático ao fechar o programa (o backup anterior é substituído).
- **DP - Antares** (importação de PDF contábil), na folha mensal: o botão vermelho-claro abre o seletor de arquivos na pasta `C:\Users\Revisa\Documents\CONTROLE FINANCEIRO\RECURSOS HUMANOS\FOLHA DE PGTO`. A leitura é inteiramente local e aceita envelopes com texto extraível, um funcionário por página, competência identificável e campo “Total Líquido”, “Valor líquido” ou “Líquido a receber”. PDFs digitalizados precisam de OCR externo. Todos os funcionários identificados entram inicialmente como **Importar: Sim**, sem exclusões por nome. Clique nessa coluna para trocar para **Não** e deixar alguém de fora; confira antes de confirmar **Importar incluídos**. Somente o líquido do PDF substitui **Salário**: nenhum desconto é importado. Os demais proventos e descontos já existentes permanecem, portanto devem ser conferidos para evitar duplicidade. Folhas fechadas, nomes ambíguos e valores não identificados são bloqueados. Nenhum PDF é enviado pela rotina de importação.

## Como executar

Requer Python 3.11 ou superior.

```powershell
py -m pip install -r requirements.txt
py .\folha_pagamento.py
```

Para gerar o executável com PyInstaller:

```powershell
py -m pip install pyinstaller
py -m PyInstaller --noconfirm --clean .\FolhaPagamentoRevisa_1_130.spec
```

O executável gerado fica em `dist\FolhaPagamentoRevisa_1_130.exe`. Para atualizar a instalação local, feche o aplicativo e copie esse arquivo para a pasta do projeto como `FolhaPagamentoRevisa_1_130.exe` (usado pelo iniciador) e `FolhaPagamentoRevisa.exe`. Não substitua o banco de dados.

## Dados

- O banco fica em `%LOCALAPPDATA%\FolhaPagamentoRevisa\folha_pagamento.db`, criado na primeira execução.
- Todos os dados ficam armazenados localmente; o programa não envia nada pela internet.
- Os arquivos `.db` não são versionados neste repositório, por conterem dados de colaboradores.

## Estrutura

| Arquivo | Descrição |
|---|---|
| `folha_pagamento.py` | Aplicativo principal |
| `importar_planilha.py` | Utilitário para consultar a estrutura de uma planilha e gerar relatório de importação |
| `Iniciar_Folha_Pagamento.bat` | Atalho para iniciar o programa |
| `logo_revisa.png`, `folha_pagamento.ico` | Logo e ícone |
| `requirements.txt` | Dependências (`reportlab`, `openpyxl`, `Pillow` e `pypdf`) |
| `FolhaPagamentoRevisa_1_130.spec` | Configuração de build do executável, sem banco de dados embutido |
| `LEIA-ME.txt` | Manual de uso detalhado |
| `HISTORICO_DO_PROJETO.md` | Histórico explicado desde o início do projeto |

## Cálculo do líquido

```
salário + PF/adicional + hora extra + férias + 13º
- marmitex - vales - farmácia - empréstimo - outros descontos
```
