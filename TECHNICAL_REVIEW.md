# Revisão técnica do StemTube Studio

Data: 2026-09-08. Base examinada: `9008021`.

## Correções

| Problema no código | Consequência | Correção aplicada |
|---|---|---|
| `ignoreerrors=True` no processamento do download | Uma conversão fracassada podia deixar um arquivo intermediário tratado como resultado | Erros de processamento interrompem o item e ficam disponíveis para nova tentativa |
| Recorte de áudio com `-c copy` anunciado como exato | Limites do trecho dependiam dos pacotes do codec | Recodificação apenas do trecho em MP3, M4A, OPUS, WAV e FLAC; formato original mantém cópia com aviso explícito |
| Conversão completa antes do recorte | Trabalho desnecessário e conversão adicional ao implementar corte preciso | Download do áudio de origem, seguido de uma conversão do trecho |
| `-map 0` e metadados sempre presentes no recorte | Inclusão de fluxos indesejados e desrespeito à opção de metadados | Mapeamento explícito e metadados condicionais |
| Cópia no Drive sobrescrevia nomes existentes | Resultado anterior podia ser perdido | Reserva exclusiva de nome e sufixos numéricos |
| Falha no Drive propagava exceção para processamento | Download/separação podia falhar; mixagem podia apagar o resultado local | Aviso de falha de cópia, remoção de cópia incompleta e preservação do resultado local |
| Identificador e URL eram validados separadamente | Link de outro vídeo podia passar com identificador divergente | Verificação de correspondência e URL canônica |
| Vídeos repetidos na mesma tarefa | Resultados duplicados apontando para o mesmo arquivo | Deduplicação por identificador, preservando a ordem |
| Pasta `..` e duração NaN | Destino inesperado e validação numérica incompleta | Neutralização de pasta especial, contenção de destino no Drive e duração positiva finita |

## Evidências de validação

`python src/tests/test_backend.py`: **75 verificações aprovadas**.

- Upload em blocos e rejeição de entradas inválidas.
- Separação simulada de quatro faixas com FFmpeg e prévias reais.
- Renderização FLAC de duas faixas selecionadas, com ganho diferente.
- Recortes reais em WAV, MP3, M4A, OPUS, FLAC e original. WAV de 1,5 segundo verificado com tolerância inferior a uma amostra em 44,1 kHz; demais contêineres com tolerância de 100 ms.
- Simulação de falha de conversão e de falta de espaço no Drive.
- Preservação de arquivos homônimos no destino de teste.
- ZIP, HTTP Range, bloqueio de travessia, cancelamento e limpeza.

Ambiente local: FFmpeg 6.1.1, yt-dlp 2026.08.19. A validação do Drive usa diretório temporário e falha simulada, sem acesso ao Drive pessoal.

O gerador recompilou todas as células Python e produziu novamente `StemTube.ipynb`. O JavaScript passou em `node --check`. `git diff --check` não apontou problemas de whitespace.

## Limites da revisão

Os testes não executaram autenticação Google, montagem real do Drive, downloads do YouTube, modelos de IA ou GPU T4 no Colab. A separação simulada testa o fluxo de arquivos, sem avaliar a qualidade da separação neural. A verificação JavaScript é sintática, sem validação visual ou de sincronismo do mixer em navegador.

A instalação ainda resolve dependências atualizadas em cada sessão, portanto versões futuras podem introduzir incompatibilidades. O mixer usa elementos de áudio independentes e correção periódica de posição; isso não constitui sincronização com precisão de amostra. A opção de áudio original preserva os pacotes, portanto não oferece a mesma precisão de corte da recodificação. Falhas de pós-processamento, inclusive capa, agora tornam o item falho em vez de apresentar um resultado possivelmente incompleto como sucesso.

Não se afirma ausência absoluta de erros nem validação integral no Colab. Para carregar o código atualizado, abrir novamente o link original e iniciar uma sessão nova, executando as células 1 e 2.

## Referências técnicas

- [FFmpeg: opções de busca temporal e cópia de fluxos](https://ffmpeg.org/ffmpeg.html).
- [yt-dlp: opções de tratamento de erros e pós-processamento](https://github.com/yt-dlp/yt-dlp).
