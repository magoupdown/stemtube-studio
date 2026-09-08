## ℹ️ Sobre o StemTube Studio

O StemTube Studio reúne, em um único aplicativo, as ferramentas **StemLab** (separação de faixas com IA e mixer) e **YT Downloader Pessoal** (vídeos, playlists e áudio do YouTube), sem repetir nada: um só login, uma só seção de cookies, uma só fila e um só destino no Drive (`Meu Drive/StemTube`).

### O que acontece por baixo dos panos

| Recurso | Como funciona |
|---|---|
| Downloads | `yt-dlp` com runtime JavaScript (deno), `ffmpeg` para converter, empacotar em MP4 e embutir capa/metadados |
| Recorte por tempo | O arquivo completo é baixado e cortado com `ffmpeg`; vídeo é recodificado (H.264) para o corte ser exato, áudio é recodificado no formato escolhido; original usa corte aproximado por pacotes |
| Separação de faixas | [audio-separator](https://github.com/nomadkaraoke/python-audio-separator) com os modelos `model_bs_roformer_ep_317_sdr_12.9755.ckpt` (voz), `htdemucs_ft.yaml` (4 faixas) e `htdemucs_6s.yaml` (6 faixas), na GPU quando disponível |
| Mixer | Prévias MP3 de cada faixa tocadas em sincronia no navegador; a mixagem final é renderizada pelo `ffmpeg` a partir das faixas completas, com limitador de picos |
| Fila | Duas pistas independentes: downloads e processamento na GPU rodam em paralelo, um item por vez em cada pista |
| Segurança | Login Google obrigatório, validação de links e de cookies, bloqueio de travessia de diretórios, limites de upload e de duração |

### Solução de problemas

- **“Confirme que você não é um robô” / vídeo privado / +18** → carregue os cookies da sua conta na seção *Cookies* e tente de novo.
- **Sem GPU** → *Ambiente de execução ▸ Alterar o tipo de ambiente de execução ▸ T4 GPU*, depois rode as células 1 e 2 novamente. Downloads não precisam de GPU.
- **A memória da GPU estourou** → use uma música mais curta (limite de 25 min) ou o modo *Voz + Playback*.
- **A interface não aparece** → rode a célula 1 até o fim e só então a célula 2. Se a sessão foi reiniciada, repita as duas.
- **Mixes automáticos do YouTube (list=RD…)** não podem ser listados fora do player: baixe o vídeo ou salve os itens em uma playlist sua.

### Limites e observações

- Separação: áudios de até **25 minutos** (limite operacional da GPU gratuita). Arquivos locais de até **1 GB**.
- Playlists: até **1000 vídeos** por análise.
- O áudio do YouTube tem no máximo ~130–160 kbps (256 kbps em alguns casos): FLAC e WAV preservam o que foi recebido, mas não recuperam qualidade perdida.
- As estimativas de tempo são aproximadas. Os arquivos ficam em `/content/stemtube` só enquanto a sessão estiver ativa; use a célula 3 para limpar.

Código-fonte, testes e servidor de desenvolvimento: [github.com/magoupdown/stemtube-studio](https://github.com/magoupdown/stemtube-studio)

---
*Desenvolvido por **@emersonms** - 2026*
