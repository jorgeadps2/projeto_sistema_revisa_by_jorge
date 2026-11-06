# Sistemas Revisa

Desenvolvido: JORGE ALBERTO DE PAULA

Aplicativo para Windows que reúne em uma janela:

- **Folha de Pagamento**: colaboradores, salarios, folha mensal, proventos, descontos e relatorios PDF.
- **Controle de Energia e Agua**: inquilinos, consumos, alugueis, despesas e pagamentos.

Na aba **Inquilinos**, clique em **Aviso leitura** para escolher quais inquilinos
devem receber o lembrete de leitura do medidor. Inquilinos já cadastrados mantêm
a configuração compatível com os avisos anteriores. A partir do dia 5, aparece
um aviso para confirmar as leituras do mês anterior. Escolha **Leitura OK** para
encerrar o aviso daquela competência; em **Não OK**, ele volta a aparecer
diariamente até a confirmação.

A inicialização aparece centralizada no monitor onde está o ponteiro do mouse ao abrir.
A tela de senha permanece centralizada no mesmo monitor da janela, inclusive com vários
monitores conectados.
O rodapé do login exibe a imagem do robô ao lado do crédito do desenvolvedor.
Os textos do rodapé ficam centralizados horizontal e verticalmente em suas colunas.
A janela principal abre maximizada no monitor do login após a montagem do menu.
Ao abrir a Folha ou o
Energia e Água, a janela em tamanho normal volta ao centro do monitor; a maximização
feita pelo usuário é preservada.

## Executar pelo código-fonte

Requer Python com Tkinter no Windows. Para abrir a versão integrada:

```powershell
python -m pip install -r .\FolhaPagamentoRevisa\requirements.txt
python .\SistemasRevisa\app.py
```

## Gerar o executável integrado

```powershell
python -m pip install pyinstaller
Set-Location .\SistemasRevisa
python -m PyInstaller --noconfirm --clean --distpath ..\dist Sistemas_Revisa.spec
```

O executável será gerado em `dist\Sistemas_Revisa.exe`.

## Sincronização entre computadores

1. Instale o MEGA nos computadores e sincronize a mesma pasta compartilhada.
2. No computador que já contém os dados corretos, abra **Administração e Segurança**,
   informe a senha principal para acessar a sincronização, escolha a pasta compartilhada,
   ative a sincronização e confirme que ele é o primeiro computador titular.
3. Feche o sistema para enviar automaticamente os bancos da Folha e de Energia e Água.
   Aguarde o MEGA concluir a sincronização do pacote inicial. Também é possível antecipar
   o envio em **Backups e Transferência > Acessar sincronização > Enviar dados e ceder a vez**.
4. No outro computador, abra o executável. Se ele já contém dados locais, use
   **Administração e Segurança > Conectar como receptor** e selecione a mesma pasta do MEGA.
   Se for uma instalação nova, use **Conectar à sincronização automática** na tela de banco
   ausente. Confirme a importação somente se o pacote contém os dados corretos.
5. Ao terminar, feche o sistema no computador que recebeu os dados e aguarde o MEGA
   concluir o envio antes de abrir o programa no computador seguinte.

Use somente um computador por vez. Os bancos SQLite não são sincronizados enquanto o
programa está aberto; com a sincronização ativa, o recebimento acontece automaticamente
na abertura e o envio dos dois bancos acontece ao fechar uma sessão autenticada no PC
titular. A pasta compartilhada deve ser configurada em cada PC (neste ambiente,
`Banco de Dados Sistema`); o caminho local pode ser diferente no outro computador.
Se o envio falhar, o sistema avisa e permanece aberto para nova tentativa.
Na abertura, pacotes externos são verificados mesmo quando uma instalação antiga
ainda considera este PC titular. Conflitos bloqueiam a edição e aparecem como
falha, com o motivo ao tentar abrir um módulo. O envio também recusa sobrescrever
um pacote externo mais recente ainda não recebido.
Pacotes já recebidos ou antigos são ignorados na abertura após validar sua integridade;
eles não são importados novamente nem causam um falso conflito com os dados atuais.
Se o MEGA ainda não terminou de sincronizar, o computador sem a versão mais
recente permanece bloqueado para edição. Ao reabrir no mesmo PC que enviou o pacote,
o sistema pergunta se você quer continuar nele. Confirme somente se o outro computador
não importou o pacote ou está fechado sem alterações; bancos locais alterados ou um
pacote mais recente do outro PC impedem a retomada. Também é possível retomar em
**Backups e Transferência > Acessar sincronização > Retomar neste PC**.
Senhas locais não são transferidas.
Cada pacote deve conter os bancos da Folha e do Controle de Energia e Água. Se faltar algum
banco, a importação é bloqueada para evitar que apenas parte dos dados seja sincronizada.
Os PDFs contábeis importados pelo botão **Antares DP** ficam dentro do banco da Folha
e acompanham a sincronização e os backups, sem depender de caminhos iguais nos PCs.
No programa integrado, a Folha não carrega o backup legado isolado ao abrir o módulo:
os dois bancos são recebidos juntos pelo pacote, evitando substituir os dados recém-importados.
Ao atualizar, abra primeiro no computador que possui os PDFs antigos, para incorporá-los
ao banco antes de enviar os dados e ceder a vez. Utilize a versão atualizada nos dois PCs.
Ao abrir um módulo, o sistema avisa se o Gerenciador Administrativo anterior estiver
aberto; feche-o antes de continuar para evitar alterações simultâneas.
Após um novo pacote completo ser criado, os pacotes anteriores verificados são removidos
da pasta compartilhada, que mantém somente o mais recente. Backups locais de segurança
continuam preservados.

## Dados e seguranca

Este repositorio contem somente os arquivos do aplicativo. Bancos de dados,
backups, documentos, senhas, certificados digitais e executaveis nao devem ser
versionados. Preserve os backups de dados separadamente.

Os executaveis armazenam os dados em subpastas de `%LOCALAPPDATA%`.
O Controle de Energia e Agua executado pelo codigo-fonte utiliza a propria pasta.
Na tela **Backups e Transferência**, é possível escolher uma pasta adicional para
salvar uma segunda cópia verificada de cada backup manual e dos backups anteriores
à importação de dados. A pasta adicional pode ser desativada nessa mesma tela.

Ao fechar o módulo de Energia e Água no programa integrado (inclusive ao sair do
sistema), uma cópia consistente e validada é salva como `backup_energia_saida.db`
na mesma pasta `Backup Folha Revisa` utilizada pela Folha. Essa cópia é atualizada
sem sobrescrever o `backup_saida.db` da Folha. Se não for possível salvar, o sistema
avisa sobre a falha. Essa cópia isolada não é importada automaticamente no outro PC:
o recebimento dos dois bancos depende do pacote criado na pasta compartilhada pela
sincronização ativa. Aguarde sempre o MEGA concluir o envio.

## Documentacao

- [Folha de Pagamento](FolhaPagamentoRevisa/README.md)
- [Controle de Energia e Agua](Controle_Energia_Agua_Barracao_Python/Controle_Energia_Agua_Barracao/LEIA-ME.txt)
