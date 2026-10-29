# Gerenciador Administrativo REVISA

Aplicativo para Windows que centraliza o acesso aos sistemas:

- **Folha de Pagamento**: colaboradores, salarios, folha mensal, proventos, descontos e relatorios PDF.
- **Controle de Energia e Agua**: inquilinos, consumos, alugueis, despesas e pagamentos.

## Executar

Requer Python com Tkinter no Windows.

```powershell
python -m pip install -r .\FolhaPagamentoRevisa\requirements.txt
python .\Controle_Energia_Agua_Barracao_Python\Iniciar_Sistemas_Revisa.py
```

Na primeira utilizacao, abra a Folha diretamente para cadastrar a senha usada pela Central:

```powershell
python .\FolhaPagamentoRevisa\folha_pagamento.py
```

## Gerar o executavel

```powershell
python -m pip install pyinstaller
Set-Location .\Controle_Energia_Agua_Barracao_Python
python -m PyInstaller --noconfirm --clean --distpath ..\dist GerenciadorAdministrativoRevisa.spec
```

O executavel sera gerado em `dist\GerenciadorAdministrativoRevisa.exe`.

## Dados e seguranca

Este repositorio contem somente os arquivos do aplicativo. Bancos de dados,
backups, documentos, senhas, certificados digitais e executaveis nao devem ser
versionados. Preserve os backups de dados separadamente.

Os executaveis armazenam os dados em subpastas de `%LOCALAPPDATA%`.
O Controle de Energia e Agua executado pelo codigo-fonte utiliza a propria pasta.

## Testes da Central

```powershell
Set-Location .\Controle_Energia_Agua_Barracao_Python
python -m unittest discover -s tests -v
```

## Documentacao

- [Folha de Pagamento](FolhaPagamentoRevisa/README.md)
- [Controle de Energia e Agua](Controle_Energia_Agua_Barracao_Python/Controle_Energia_Agua_Barracao/LEIA-ME.txt)
