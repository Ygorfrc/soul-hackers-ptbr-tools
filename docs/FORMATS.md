# Formatos investigados

Estas são observações da versão de 3DS investigada, não uma especificação oficial.
Os reconhecedores são heurísticos e deliberadamente restritos.

## Tabelas de mensagem LE32

Encontradas em `TK_MDT.BIN`:

| Campo | Representação |
| --- | --- |
| Deslocamento inicial dos dados | `u32` little-endian no início da tabela |
| Ponteiros | `u32` little-endian a partir de `+4` |
| Base dos ponteiros | Início da área de dados da própria tabela |
| Contagem inferida | `data_start / 4 - 1` |
| Primeiro ponteiro | Zero |
| Limite de mensagem | Terminador observado `FF 00` |

O arquivo observado contém 16 tabelas e 12.328 registros. Há referências no
executável às posições absolutas das tabelas. Os limites e espaços entre tabelas
não devem ser descartados ao reconstruir o arquivo.

O reconhecedor exige ponteiros estritamente crescentes, terminadores nas
fronteiras entre registros e uma proporção mínima de texto legível. Isso pode
deixar de reconhecer tabelas vazias, muito pequenas ou de outra versão.

## Tabelas de eventos BE16 / LE16

Observadas em recursos de eventos, resumos, dungeons e lojas. Um cabeçalho de
quatro palavras de 16 bits tem a forma `[8, b, c, d]`:

- `c` inicia o vetor de ponteiros de mensagens;
- `d` inicia a área de texto, base dos ponteiros relativos;
- os ponteiros podem ser BE ou LE, conforme o recurso;
- pode existir uma palavra zero de alinhamento no fim do vetor;
- a função exata de todos os demais campos de script ainda não foi descrita.

O parser preserva o código e o cabeçalho, alterando somente os ponteiros de
mensagem e a área de texto dentro da capacidade reconhecida.

## Tokenização

`20..7E` são tratados como ASCII imprimível. O tokenizador preserva os demais
bytes. O comando observado `FF 05` recebe dois bytes de operandos, que permanecem
no token de controle mesmo quando têm valores de letras ASCII. Os demais
comandos iniciados em `FF` são tratados como pares de bytes neste protótipo.

Ainda falta catalogar a semântica completa dos comandos. Não aplique essas regras
automaticamente a outros jogos, regiões ou formatos sem investigar seus limites.

## Texturas NW4C RGBA8

Alguns TGAs contêm duas representações: uma prévia TGA e dados adicionais NW4C
usados pela GPU. Alterar só a prévia não garante mudança na imagem do jogo.

O suporte atual exige:

- identificador `NW4C_Tga Ver1.0` e ID de 20 bytes;
- tags com nome de 8 bytes e tamanho total LE32, incluindo cabeçalho de 12 bytes;
- formato `Rgba8` e um payload `nw4c_txd` compatível com as dimensões esperadas;
- tiles 8x8 em ordem Morton, com componentes A, B, G, R no payload;
- correspondência pixel a pixel entre prévia e área visível da GPU.

O codificador preserva tamanho, posição dos metadados e pixels da área de
padding. Rejeita uma prévia que não caiba na alocação original. Não oferece
suporte geral a ETC, outras compressões, mipmaps ou texturas arbitrárias.

## Contêiner NCCH

Os campos de offset e tamanho do RomFS estão em `0x1B0`, relativos à partição.
O endereço `0x1D0` fica na região de hash ExeFS e não deve ser lido como offset.
O empacotador aplica a unidade de mídia indicada no cabeçalho e confere todos os
intervalos antes de calcular hashes.

## Recursos ainda pendentes

- `app_bin/mess.bin` e partes de `unite/unite.eve`;
- textos candidatos no executável;
- interfaces em outras texturas;
- eventuais formatos e variantes ainda não encontrados.
