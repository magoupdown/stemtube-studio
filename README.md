# 🎬🎧 StemTube Studio

[![Abrir no Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/magoupdown/stemtube-studio/blob/main/StemTube.ipynb)
![versão](https://img.shields.io/badge/vers%C3%A3o-1.0.0-7c5cff)
![licença](https://img.shields.io/badge/licen%C3%A7a-MIT-22d3ee)
![testes](https://img.shields.io/badge/testes%20locais-59%20ok-34d399)

**YouTube, áudio e inteligência artificial em um só aplicativo, dentro do Google Colab.**
Baixe vídeos e playlists em MP4 ou áudio, recorte um trecho, separe voz e instrumentos com IA, ouça no mixer e renderize sua própria mixagem — tudo com uma interface de página web, prévia antes de começar e fila com progresso em tempo real.

**👆 Clique no botão acima para abrir o app no Google Colab.** Rode a célula 1️⃣ (login Google + instalação) e a célula 2️⃣ (abre o aplicativo).

> O StemTube Studio reúne, sem repetir nada, as ferramentas **StemLab** (separação de faixas com IA e mixer) e **YT Downloader Pessoal** (vídeos, playlists e áudio do YouTube): um só login, uma só seção de cookies, uma só fila e um só destino no Drive.

## ✨ O que ele faz

| | Recurso | Detalhes |
|---|---|---|
| 🎬 | **Vídeo em MP4** | Qualquer resolução disponível (144p a 8K), com fps, HDR e tamanho estimado. VP9/AV1 empacotados em MP4 sem perda. |
| 🎵 | **Somente áudio** | MP3, M4A/AAC, OPUS, FLAC, WAV ou original, com qualidade (96–320 kbps ou melhor VBR), capa e metadados embutidos. |
| 📃 | **Playlists e canais** | Seleção item a item, filtro por título, "selecionar todos / nenhum / inverter", detecção de Mixes automáticos, até 1000 vídeos. |
| ✂️ | **Recorte por tempo** | Início e fim em vídeo ou áudio, com corte exato (vídeo recodificado em H.264, áudio copiado sem perda). |
| 🎧 | **Separação com IA** | **Voz + Playback** (BS-Roformer), **Banda** (4 faixas, htdemucs_ft) ou **Completo** (6 faixas, htdemucs_6s), na GPU. Fonte: vídeo do YouTube ou arquivo local de até 1 GB. |
| 🎛 | **Mixer e mixagem** | Ouça as faixas em sincronia, silencie (M), isole (S), ajuste volumes, compare com o original e **renderize a mixagem** em WAV, FLAC ou MP3 com limitador. |
| 📥 | **Fila em duas pistas** | Downloads e processamento na GPU rodam em paralelo. Cole outro link enquanto o anterior roda; a barra de tarefas mostra tudo em qualquer etapa. |
| 🔐 | **Conta e cookies** | Login Google obrigatório. Cookies da conta para vídeos privados, +18 ou só para membros, salvos no Drive e migrados automaticamente das versões anteriores. |
| 💾 | **Destino** | Botão "Baixar" por arquivo, ZIP de tudo e cópia opcional em `Meu Drive/StemTube/{Downloads,Faixas,Mixagens}` com subpasta personalizada. |
| 📱 | **Interface** | Assistente em 5 etapas (Fonte → Prévia → Opções → Processar → Resultado), tema claro/escuro, responsivo, mensagens de erro traduzidas com o que fazer. |

## 🚀 Como usar

1. Abra o notebook pelo botão acima. Ele solicita **GPU T4** (a disponibilidade depende do Colab). Downloads funcionam com ou sem GPU.
2. Rode a célula **1️⃣** e faça login na conta Google. Deixe `conectar_google_drive` marcado para salvar cookies e arquivos no Drive. Desmarque `instalar_separador_ia` se quiser só os downloads (instalação em ~30 s em vez de 1–3 min).
3. Rode a célula **2️⃣**. O aplicativo aparece logo abaixo.
4. **Fonte**: cole um link (vídeo, Shorts, playlist ou canal) ou envie um arquivo. **Prévia**: confira título, canal, duração e, em playlists, escolha os itens. **Opções**: escolha entre vídeo MP4, só áudio ou separar faixas, ajuste qualidade, recorte e destino. **Processar** e **Resultado**: acompanhe o progresso, baixe, ouça no mixer e renderize mixagens.

Na primeira separação de cada modo, o modelo de IA é baixado uma vez por sessão. O modelo de voz já começa a baixar em segundo plano assim que o app abre.

## 🍪 Sobre os cookies

O Colab roda em um servidor do Google, então **não é possível ler os cookies do seu navegador automaticamente**. Para vídeos privados, +18, só para membros ou quando o YouTube pedir "confirme que você não é um robô":

1. Exporte uma vez o `cookies.txt` com a extensão *Get cookies.txt LOCALLY* (Chrome/Edge) ou *cookies.txt* (Firefox), logado no youtube.com.
2. Carregue o arquivo dentro do app (seção *Cookies da sua conta*). Aceita formato Netscape, JSON de extensões ou o cabeçalho `Cookie:`.
3. Com o Drive conectado ele é salvo em `Meu Drive/StemTube/cookies.txt` e **carregado automaticamente** nas próximas sessões. Cookies salvos pelo StemLab ou pelo YT Downloader são migrados sozinhos.

O botão **Testar** verifica se o YouTube reconhece a sessão. Cookies dão acesso à sua conta: nunca compartilhe o arquivo.

## 📐 Limites e observações

- Separação: áudios de **até 25 minutos** (limite operacional da GPU gratuita) e arquivos locais de **até 1 GB**.
- O áudio do YouTube tem no máximo ~130–160 kbps (256 kbps em alguns casos). FLAC e WAV preservam o que foi recebido, mas não recuperam qualidade perdida.
- Mixes automáticos (`list=RD…`) não podem ser listados fora do player: baixe o vídeo ou salve os itens em uma playlist sua.
- Arquivos temporários ficam em `/content/stemtube` enquanto a sessão estiver ativa. A célula **3️⃣** exige marcar `confirmar_limpeza` e só limpa sem tarefas ativas, preservando modelos, cookies e cópias no Drive.
- Uso pessoal. Respeite os termos do YouTube e os direitos dos criadores.

## 🧱 Estrutura do repositório

```
stemtube-studio/
├── StemTube.ipynb            ← o notebook pronto para o Colab (gerado a partir de src/)
├── README.md · CHANGELOG.md · LICENSE
└── src/
    ├── backend.py            ← funções Python: yt-dlp, cookies, upload, downloads, recorte,
    │                            audio-separator, mixagem, fila em duas pistas, servidor de prévias
    ├── app.html              ← interface (HTML/CSS/JS) que chama o Python pela ponte do Colab
    ├── setup_cell.py         ← célula 1: login Google, Drive, GPU e dependências
    ├── cleanup_cell.py       ← célula 3: limpeza opcional
    ├── intro.md · outro.md   ← células de texto do notebook
    ├── build_notebook.py     ← gera o .ipynb a partir dos arquivos acima
    ├── dev_server.py         ← servidor local para testar a interface fora do Colab
    └── tests/test_backend.py ← 59 verificações do backend em modo simulado
```

### Desenvolvimento

```bash
# gerar o notebook após editar src/
python src/build_notebook.py .

# testes do backend (precisa de ffmpeg, yt-dlp e ipython)
python src/tests/test_backend.py

# interface no navegador com separação simulada (sem GPU nem modelos)
STEMTUBE_MOCK=1 python src/dev_server.py 8791   # abra http://127.0.0.1:8791
```

No modo simulado a "separação" usa filtros do ffmpeg, o que valida upload, fila, mixer, mixagem, ZIP e servidor de arquivos sem baixar modelos. Downloads do YouTube funcionam de verdade no servidor de desenvolvimento.

### Bibliotecas

[yt-dlp](https://github.com/yt-dlp/yt-dlp) · [audio-separator](https://github.com/nomadkaraoke/python-audio-separator) · [FFmpeg](https://ffmpeg.org/) · [Deno](https://deno.land/)

---

**Desenvolvido por [@emersonms](https://github.com/magoupdown) - 2026**
