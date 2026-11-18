# 🎬🎧 StemTube Studio

[![Abrir no Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/magoupdown/stemtube-studio/blob/studio-aba-responsiva/StemTube.ipynb)
![versão](https://img.shields.io/badge/vers%C3%A3o-1.0.0-7c5cff)
![licença](https://img.shields.io/badge/licen%C3%A7a-MIT-22d3ee)
![testes](https://img.shields.io/badge/testes%20locais-90%20ok-34d399)

Baixe vídeos e playlists do YouTube, extraia o áudio ou converta arquivos do seu dispositivo. O painel abre em uma aba responsiva e o processamento acontece na sessão do Colab.

## ✨ O que ele faz

| | Recurso | Detalhes |
|---|---|---|
| 🎬 | **Vídeo em MP4** | Qualquer resolução disponível (144p a 8K), com fps, HDR e tamanho estimado. VP9/AV1 empacotados em MP4 sem perda. |
| 🎵 | **Somente áudio** | MP3, M4A/AAC, OPUS, FLAC, WAV ou original, com qualidade (96–320 kbps ou melhor VBR), capa e metadados embutidos. |
| 📃 | **Playlists e canais** | Seleção item a item, filtro por título, "selecionar todos / nenhum / inverter", detecção de Mixes automáticos, até 1000 vídeos. |
| ✂️ | **Recorte por tempo** | Início e fim em vídeo ou áudio, com corte exato (vídeo recodificado em H.264, áudio recodificado no formato escolhido; original usa corte aproximado por pacotes). |
| 📁 | **Arquivos locais** | Envie até 1 GB. Converta vídeos para MP4 com H.264, extraia o áudio original ou escolha outro formato. A interface oferece as opções compatíveis com o conteúdo do arquivo. |
| 📥 | **Fila de tarefas** | Prepare a próxima conversão enquanto a anterior é processada. Acompanhe o progresso, cancele ou repita itens com erro. |
| 🔐 | **Conta e cookies** | Login Google obrigatório. Cookies da conta para vídeos privados, +18 ou só para membros, salvos no Drive e migrados automaticamente das versões anteriores. |
| 💾 | **Destino** | Botão "Baixar" por arquivo, ZIP de tudo e cópia opcional em `Meu Drive/StemTube/Downloads` com subpasta personalizada. |
| 📱 | **Interface** | Assistente em 5 etapas (Fonte → Prévia → Opções → Processar → Resultado), tema claro/escuro, responsivo, mensagens de erro traduzidas com o que fazer. |

## Prévias dos resultados

Downloads, conversões e recortes têm prévias individuais com reprodução, pausa, busca, volume e velocidade. Abra **Ouvir áudio** ou **Ver vídeo** no resultado. A prévia de vídeo mantém a duração completa em até 480p; a prévia de áudio usa MP3. O arquivo de download mantém o formato e a qualidade escolhidos. Quando o proxy de mídia falha, o player carrega por blocos pela ponte do Colab. A geração de prévias acrescenta tempo ao processamento.

## 🚀 Como usar

1. Abra o notebook em uma sessão de CPU do Colab.
2. Rode a célula **1️⃣** e faça login na conta Google. Deixe `conectar_google_drive` marcado para salvar cookies e arquivos no Drive.
3. Rode a célula **2️⃣**. Clique em **Abrir StemTube Studio em nova aba**. Mantenha a aba do notebook aberta e conectada. Se o navegador bloquear a abertura, permita pop-ups ou desmarque `abrir_em_nova_aba` e execute a célula 2 novamente.
4. Cole um link ou envie um arquivo. Confira a prévia, escolha vídeo MP4 ou somente áudio, ajuste a qualidade e clique para começar.

## 🍪 Sobre os cookies

O Colab roda em um servidor do Google, então **não é possível ler os cookies do seu navegador automaticamente**. Para vídeos privados, +18, só para membros ou quando o YouTube pedir "confirme que você não é um robô":

1. Exporte uma vez o `cookies.txt` com a extensão *Get cookies.txt LOCALLY* (Chrome/Edge) ou *cookies.txt* (Firefox), logado no youtube.com.
2. Carregue o arquivo dentro do app (seção *Cookies da sua conta*). Aceita formato Netscape, JSON de extensões ou o cabeçalho `Cookie:`.
3. Com o Drive conectado ele é salvo em `Meu Drive/StemTube/cookies.txt` e **carregado automaticamente** nas próximas sessões. Cookies salvos pelo StemLab ou pelo YT Downloader são migrados sozinhos.

O botão **Testar** verifica se o YouTube reconhece a sessão. Cookies dão acesso à sua conta: nunca compartilhe o arquivo.

## 📐 Limites e observações

- O limite por arquivo enviado é de 1 GB. A duração e o espaço livre da sessão afetam o processamento.
- O áudio do YouTube tem no máximo ~130–160 kbps (256 kbps em alguns casos). FLAC e WAV preservam o que foi recebido, mas não recuperam qualidade perdida.
- Mixes automáticos (`list=RD…`) não podem ser listados fora do player: baixe o vídeo ou salve os itens em uma playlist sua.
- Arquivos temporários ficam em `/content/stemtube` enquanto a sessão estiver ativa. A célula **3️⃣** exige marcar `confirmar_limpeza` e só limpa sem tarefas ativas, preservando cookies e cópias no Drive.
- Uso pessoal. Respeite os termos do YouTube e os direitos dos criadores.

## 🧱 Estrutura do repositório

```
stemtube-studio/
├── StemTube.ipynb            ← o notebook pronto para o Colab (gerado a partir de src/)
├── README.md · CHANGELOG.md · LICENSE
└── src/
    ├── launcher.html         ← abertura em nova aba e conexão com a célula
    ├── backend.py            ← funções Python: yt-dlp, cookies, upload, downloads, recorte,
    │                            conversão local, fila de tarefas, servidor de prévias
    ├── app.html              ← interface (HTML/CSS/JS) que chama o Python pela ponte do Colab
    ├── setup_cell.py         ← célula 1: login Google, Drive e dependências
    ├── cleanup_cell.py       ← célula 3: limpeza opcional
    ├── intro.md · outro.md   ← células de texto do notebook
    ├── build_notebook.py     ← gera o .ipynb a partir dos arquivos acima
    ├── dev_server.py         ← servidor local para testar a interface fora do Colab
    └── tests/
        ├── test_backend.py   ← 90 verificações do backend
        └── test_window.py    ← nova aba e fluxo responsivo em Chromium
```

### Desenvolvimento

```bash
# gerar o notebook após editar src/
python src/build_notebook.py .

# testes do backend (precisa de ffmpeg, yt-dlp e ipython)
python src/tests/test_backend.py

# interface local no navegador
python src/dev_server.py 8791   # abra http://127.0.0.1:8791
```


### Bibliotecas

[yt-dlp](https://github.com/yt-dlp/yt-dlp) · [FFmpeg](https://ffmpeg.org/) · [Deno](https://deno.land/)

---

**Desenvolvido por [@emersonms](https://github.com/magoupdown) - 2026**
