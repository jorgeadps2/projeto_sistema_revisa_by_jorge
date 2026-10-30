# Sistemas Revisa

Desenvolvido: JORGE ALBERTO DE PAULA

Aplicativo para Windows que reúne em uma janela:

- **Folha de Pagamento**: colaboradores, salarios, folha mensal, proventos, descontos e relatorios PDF.
- **Controle de Energia e Agua**: inquilinos, consumos, alugueis, despesas e pagamentos.

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
3. Na tela **Backups e Transferência**, acesse a sincronização, escolha
   **Enviar dados e ceder a vez** e aguarde o MEGA concluir a sincronização do pacote inicial.
4. No outro computador, abra o executável. Se ele já contém dados locais, use
   **Administração e Segurança > Conectar como receptor** e selecione a mesma pasta do MEGA.
   Se for uma instalação nova, use **Conectar à sincronização automática** na tela de banco
   ausente. Confirme a importação somente se o pacote contém os dados corretos.
5. Ao terminar, acesse **Backups e Transferência > Acessar sincronização** no computador
   que recebeu os dados, escolha **Enviar dados e ceder a vez** e aguarde o MEGA concluir
   antes de abrir o programa no computador seguinte.

Use somente um computador por vez. Os bancos SQLite não são sincronizados enquanto o
programa está aberto; o recebimento acontece automaticamente na abertura, mas fechar o
programa não transfere a vez. Envie e ceda a vez somente quando realmente for trocar de
computador. Se o MEGA ainda não terminou de sincronizar, o computador sem a versão mais
recente permanece bloqueado para edição. A retomada manual neste computador só deve ser
usada quando o outro computador não importou o pacote ou está fechado sem alterações.
Senhas locais não são transferidas.
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

## Documentacao

- [Folha de Pagamento](FolhaPagamentoRevisa/README.md)
- [Controle de Energia e Agua](Controle_Energia_Agua_Barracao_Python/Controle_Energia_Agua_Barracao/LEIA-ME.txt)
