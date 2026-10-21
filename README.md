# Soul Hackers PT-BR Tools

Ferramentas Python para pesquisa de formatos binários e localização de
**Devil Summoner: Soul Hackers (Nintendo 3DS)** em português brasileiro.

**Estado: experimental — tradução parcial, checkpoint v4.**

Este repositório reúne código e documentação do processo de extração de texto,
edição e reconstrução. Os exemplos usam dados fictícios. ROMs, chaves, arquivos
extraídos, texturas e o corpus de diálogos do jogo não fazem parte do repositório.

> **English:** Experimental Python tools for binary text research and Brazilian
> Portuguese localization. Includes synthetic examples; no ROMs, keys or game assets.

## O problema de engenharia

Traduzir um texto dentro de um binário exige manter as referências que o jogo
usa para encontrá-lo. Uma tradução pode ficar legível no arquivo e ainda assim
quebrar a execução se mover uma tabela ou alterar um código de controle.

Neste projeto, o primeiro extrator reconhecia apenas parte de uma tabela de
negociação. A investigação posterior identificou **16 tabelas concatenadas** em
`TK_MDT.BIN`, com posições referenciadas pelo executável. A reconstrução passou
a preservar o tamanho do arquivo e a posição absoluta de cada tabela, ajustando
apenas os ponteiros relativos das mensagens dentro da sua alocação original.

## Recursos

- Inventário heurístico de possíveis recursos de texto em um RomFS local.
- Exportação de tabelas LE32 e tabelas de eventos BE/LE16 para JSON.
- Separação entre texto ASCII, códigos de controle e bytes opacos.
- Reinserção com conferência do SHA-256 de origem e dos metadados.
- Rejeição de traduções fora de ASCII imprimível ou acima da capacidade da tabela.
- Leitura de prévias TGA e comparação com o payload GPU NW4C RGBA8.
- Reconstrução local de uma imagem CCI usando uma instalação externa do 3dstool.
- Testes sintéticos existentes para ponteiros, controles e limites de leitura.

Não é um extrator universal de jogos da Atlus. As regras são específicas dos
formatos investigados; há recursos ainda não reconhecidos.

## Começo rápido: exemplo sem ROM

Requisito: **Python 3.10+**. Os scripts usam apenas a biblioteca padrão.

No PowerShell, a partir da raiz deste repositório:

```powershell
py .\examples\demo_roundtrip.py
```

O exemplo cria três mensagens fictícias, preenche suas traduções em ASCII e
reconstrói uma tabela dentro da capacidade original. As saídas ficam em
`out/demo/`, diretório ignorado pelo Git.

Os testes já presentes no projeto podem ser executados separadamente:

```powershell
py -m unittest test_full_text_tool.py test_repack_soul_hackers.py
```

Esses testes usam dados sintéticos. Não substituem a conferência no jogo.

## Ferramentas

| Arquivo | Finalidade |
| --- | --- |
| `localization_inventory.py` | Inventariar candidatos em um RomFS fornecido localmente |
| `full_text_tool.py` | Exportar e reconstruir os formatos de mensagem reconhecidos |
| `inspect_tga.py` | Exportar uma prévia TGA como PNG |
| `nw4c_rgba8.py` | Comparar os pixels da prévia com o payload GPU RGBA8 |
| `repack_soul_hackers.py` | Reconstruir uma imagem local, preservando as outras partições |
| `examples/demo_roundtrip.py` | Demonstrar o fluxo com mensagens inventadas |

## Uso com seus arquivos locais

Mantenha entradas, saídas e ferramentas externas em `private/`, ignorado pelo Git.
O RomFS deve estar previamente extraído. A imagem usada pelo empacotador deve
estar previamente descriptografada; estes scripts não obtêm chaves.

### 1. Inventariar

```powershell
py .\localization_inventory.py --romfs .\private\RomFS --output .\private\inventory.json
```

O inventário é uma lista de candidatos, não prova de cobertura completa.

### 2. Exportar um recurso reconhecido

```powershell
py .\full_text_tool.py export --input .\private\RomFS\app_bin\btl_talk\TK_MDT.BIN --json .\private\catalogs\TK_MDT.json
```

Edite somente o campo `translation` dos tokens cujo `kind` é `text`.
`null` mantém o texto de origem. Preserve os demais campos.

### 3. Reconstruir o recurso

```powershell
py .\full_text_tool.py build --input .\private\RomFS\app_bin\btl_talk\TK_MDT.BIN --json .\private\catalogs\TK_MDT.json --output .\private\translated\TK_MDT.BIN
```

O relatório ao lado da saída informa a capacidade e os bytes livres de cada
tabela. Uma tabela excedida impede a gravação do binário reconstruído.

### 4. Reconstruir uma imagem local

Instale o [3dstool pelo projeto original](https://github.com/dnasdw/3dstool/releases).
Forneça um RomFS completo; o comando abaixo substitui o recurso de negociação.
Para outras alterações, prepare antes uma cópia completa do RomFS com os recursos
modificados. O empacotador não aplica automaticamente os catálogos de tradução.

```powershell
py .\repack_soul_hackers.py --rom .\private\source.3ds --romfs .\private\RomFS --text .\private\translated\TK_MDT.BIN --tool .\private\tools\3dstool.exe --output .\private\preview.cci
```

O arquivo de saída não pode existir. O processo verifica os arquivos do RomFS
reextraído, as partições finais e a integridade das entradas. Reserve bastante
espaço para os arquivos intermediários; o preflight calcula o mínimo necessário.

### 5. Inspecionar uma textura compatível

```powershell
py .\nw4c_rgba8.py --input .\private\title_01.tga --output .\private\title_preview.png
```

O comando só exporta depois de comparar os pixels visíveis com o payload GPU.
Outros formatos de textura, compressões e mipmaps não são suportados.

## Progresso da pesquisa

Checkpoint local de 21/10/2026:

| Métrica nos formatos reconhecidos | Quantidade |
| --- | ---: |
| Registros de mensagem exportados | 25.088 |
| Fragmentos de texto marcados como revisados | 8.363 |
| Fragmentos com texto alterado | 6.924 |
| Fragmentos pendentes | 60.424 |

Fragmentos incluem nomes mantidos e cópias de cenas. Essas contagens não são uma
porcentagem da tradução completa do jogo. O menu inicial foi confirmado por teste
manual no Azahar; a v4 foi reconstruída e conferida estruturalmente, com revisão
no jogo ainda necessária. A v4 local não é um pacote público de tradução.

## Documentação

- [Arquitetura e fluxo](docs/ARCHITECTURE.md)
- [Formatos investigados e limitações](docs/FORMATS.md)
- [Estado e próximos passos](docs/STATUS.md)
- [Contribuições](CONTRIBUTING.md)

## Autoria e uso de IA

Projeto de estudo mantido por [Ygor Ribeiro](https://github.com/Ygorfrc), com
assistência de IA no desenvolvimento das ferramentas, documentação e preparação
das traduções. As descobertas e limitações são registradas para permitir análise
e reprodução. Resultados estruturais e observações manuais são distinguidos.

## Créditos e licença

- [3dstool](https://github.com/dnasdw/3dstool): extração e criação de contêineres.
- [Project_CTR / ctrtool](https://github.com/3DSGuy/Project_CTR): investigação e extração inicial.
- Os programas externos são obtidos separadamente e mantêm suas próprias licenças.

Código e documentação deste repositório: [MIT](LICENSE). Essa licença não se
aplica ao jogo, seus textos, marcas ou recursos. Projeto de fãs independente,
sem afiliação com Atlus, Sega ou Nintendo.
