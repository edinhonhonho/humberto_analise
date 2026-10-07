# Pipeline de análise espacial da votação (TSE)

Análise da votação de um candidato em eleição proporcional (deputado estadual/federal) por
município e dentro das cidades. Parametrizado por ano, UF, cargo e número do candidato.

## Instalação

    pip install -r requirements.txt

## Arquivos de entrada

| Arquivo | Onde baixar (dadosabertos.tse.jus.br / geoftp.ibge.gov.br) |
|---|---|
| Votação por seção eleitoral da UF (`votacao_secao_ANO_UF.zip`) | Resultados - ANO |
| Eleitorado por local de votação (`eleitorado_local_votacao_ANO.zip`) | Eleitorado - ANO |
| Malha municipal da UF (shapefile, GeoPackage ou .zip) | IBGE, malhas municipais |
| Opcional: despesas de candidatos (`despesas_contratadas_candidatos_ANO_UF.zip`) | Prestação de contas - ANO |
| Opcional: CSV `CD_MUNICIPIO;regiao` (ex.: COREDE) | seu próprio |

Os `.zip` podem ser usados sem descompactar.

## Uso rápido (config.json)

1. Coloque os três arquivos na pasta `dados/` (sem renomear; .zip pode ficar compactado):
   `votacao_secao_ANO_RS.zip`, `eleitorado_local_votacao_ANO.zip` e a malha municipal do IBGE
   (o nome precisa conter "munic", como em `RS_Municipios_2024.zip`).
2. Edite `config.json`: para 2026, troque `"ano": 2022` por `"ano": 2026`. Se for outro
   candidato, troque `"numero"`.
3. Execute `python rodar.py`. O resultado sai em `saida_ANO/dashboard.html`.

Opcionais, se estiverem em `dados/`: `despesas_...ANO...` e `regioes.csv`.
Para mais controle, use `run_analysis.py` com argumentos (abaixo).

## Uso detalhado (run_analysis.py)

    python run_analysis.py --ano 2026 --uf RS --cargo 7 --numero 65065 \
        --votacao dados/votacao_secao_2026_RS.zip \
        --locais  dados/eleitorado_local_votacao_2026.zip \
        --malha   dados/RS_Municipios_2025.zip \
        --saida   saida_2026

Opções úteis: `--cidades "Porto Alegre,Canoas"` (em vez das mais votadas), `--top-cidades 8`,
`--h3-res 9` (hexágonos menores), `--col-eleitores NOME_DA_COLUNA`, `--despesas`, `--regioes`.

## Saídas (`--saida`)

- `dashboard.html`: relatório autocontido (tabelas ordenáveis, mapas, mapa interativo por cidade)
- `tabelas/`: `municipios.csv`, `colegas_partido.csv`, `pareto.csv`, `resultados.xlsx`
- `geo/`: `municipios.gpkg`, `locais_votacao.gpkg`, `hexagonos_h3.gpkg` (abrem direto no QGIS)
- `figuras/`: PNGs dos mapas e gráficos

## O que o pipeline calcula

1. Panorama: votos, % de votos válidos, votos por 100 aptos, ranking, mapas.
2. Concentração: Pareto (municípios para 50% e 80%), Gini, HHI, quociente locacional.
3. Autocorrelação: Moran global e LISA (vizinhança Queen) entre municípios.
4. Dentro das cidades: locais de votação, bairros do local, hexágonos H3, Getis-Ord Gi*.
5. Eficiência: votos por eleitor apto; votos que faltaram para a média estadual.
6. Contexto: colegas de partido, líder em cada município, abstenção, brancos e nulos.
7. Prestação de contas (opcional): total declarado e custo por voto.

## Limites que importam na leitura

- O TSE não publica voto por bairro. A unidade mínima é a seção; a análise intraurbana usa o
  local de votação, que é onde a pessoa vota e não onde mora.
- Locais sem coordenada válida no arquivo do TSE ficam fora dos mapas intraurbanos, mas
  entram nas tabelas. O dashboard informa a cobertura.
- Abstenção é aproximada (votos de todos os candidatos, brancos e nulos ÷ eleitores aptos).

## Pontos a conferir quando chegarem os arquivos reais

O código foi testado só com dados sintéticos no layout conhecido do TSE. Ao rodar pela primeira
vez com os arquivos reais, conferir no log:

- qual coluna foi usada como eleitores aptos (`colunas escolhidas -> eleitores=...`);
- o encoding e as colunas de latitude/longitude lidas;
- cobertura de seções casadas e de coordenadas válidas;
- municípios sem correspondência entre TSE e IBGE (o cruzamento é por nome).

## Teste

    python tests/make_synthetic.py
    python run_analysis.py --ano 2022 --uf RS --numero 65065 \
        --votacao tests/synth/votacao_secao_2022_RS.csv \
        --locais tests/synth/eleitorado_local_votacao_2022.csv \
        --malha tests/synth/malha_RS.gpkg --saida tests/saida_teste

Os dados sintéticos não representam nenhuma eleição real.

## Relatório (dashboard.html)

- O relatório tem abas por cidade (locais de votação, bairros e zonas eleitorais). O local de votação é só um
  proxy de onde a pessoa mora, por isso os mapas por hexágono e o Gi* ficam **desligados** por padrão.
- Para ligá-los: `"hex": true` no `config.json` (ou `--hex` no `run_analysis.py`).
- `"top_cidades"` define quantas cidades entram nas abas (padrão 10).
- `python rodar.py --relatorio` refaz só o HTML a partir de `saida_ANO/bundle`, sem reprocessar os dados.

## Dados de 2026 antes do CSV oficial: boletins de urna

Se o arquivo `votacao_secao_2026_RS` ainda não saiu no Portal de Dados Abertos, dá para gerá-lo a partir
dos boletins de urna, que já estão no site de resultados do TSE (um arquivo por seção):

    python baixar_bu.py --uf RS                 # ~27,7 mil seções; pode interromper (Ctrl+C) e retomar
    python baixar_bu.py --uf RS --limite 30     # teste rápido

Gera `dados/votacao_secao_2026_RS.csv` no mesmo layout do TSE (cargo 7 por padrão; `--cargos 7,6` para mais).
O boletim não traz nome de candidato nem endereço do local de votação:
- coloque `"nome"` no `config.json` (ou use `--candidatos consulta_cand_2026_RS.csv`);
- para bairro e nome do local, use o `eleitorado_local_votacao_2026` do portal (opcional).
O endereço do TSE usa o código do pleito (3220 = 1º turno 2026); para o 2º turno use `--pleito` com o novo código.
Cada seção é conferida: a soma dos votos tem de bater com o comparecimento.


## Análises complementares (seções 6 a 9 do relatório)

- **Sobreposição**: correlação, sobreposição de base e Moran bivariado do candidato contra o mais votado de cada partido (mínimo de 1.000 votos) e contra o resto da federação.
- **Participação na federação**: parcela dos votos da federação que foi para o candidato, por município, e votos "abaixo do esperado".
  A federação sai da tabela de 2026 em `eleicao/analises.py`; para outra, use `"federacao": "13,43,65"` no `config.json`.
- **Modelo**: mínimos quadrados ponderados (tamanho do eleitorado, abstenção, votação do resto da federação no município e nos vizinhos) e mapa de resíduos.
- **Distância dos redutos**: distância em linha reta ao mais próximo dos 5 municípios com mais votos e queda da votação por faixa.
- Nomes e siglas dos candidatos vêm de `dados/candidatos_ANO_UF.csv` (gerado por `python baixar_bu.py --so-candidatos`) ou do `consulta_cand` do TSE.

## Site estático (uma página, um arquivo de dados por candidato)

`python rodar.py` grava, além do `dashboard.html` (arquivo único, offline), um site estático em `site/` ao lado
de `saida_ANO/`. O site tem uma página só (`index.html`); trocar de candidato apenas busca o arquivo de dados
dele e redesenha o relatório, sem recarregar:

- `site/index.html?c=<ano>/<uf>/<cargo>/<número>`: a página; sem `?c=` abre o primeiro destaque;
- `site/assets/`: CSS e JS (versão na URL), `static.js` (textos repetidos), `geo/<UF>_<hash>.js` (traçado dos municípios, um por UF);
- `site/data/manifest.js`: grupos, destaques e siglas; `data/idx/`: candidatos de cada grupo;
- `site/data/c/<ano>/<uf>/<cargo>/<número>.js`: dados de um candidato (texto, tabelas, mapas, detalhes).

Cada execução só acrescenta ou atualiza o candidato rodado. Para publicar: `python publicar.py` monta
`site_publicar/` (sem restos de versões antigas); enviar essa pasta para qualquer hospedagem estática.
`python servir.py` serve o site localmente e gera na hora a análise de quem ainda não tem (botão "gerar análise").
`python rodar.py --lote` gera a fila (só partidos de `espectros` em `config.json`); `--indice` atualiza as listas;
`--relatorio` refaz o site e os dashboards a partir de `saida_*/bundle`; `--um UF CARGO NUM` gera um candidato.
`baixar_nomes.py` baixa os nomes de governador e senador. O texto fixo está em `eleicao/conteudo.py`; estilo e
comportamento, em `eleicao/web/`.

`baixar_rs_completo.py` baixa os boletins de todos os cargos de uma UF num só CSV.

## Vários cargos e candidatos (modo em lote)

O CSV de `baixar_rs_completo.py` traz todos os cargos. Com ele:

    python rodar.py --lote

roda a análise completa dos mais votados de cada cargo e junta tudo em `site/`, onde o botão
"Trocar candidato" do topo de cada página alterna entre cargo e candidato. Quem já está no site é pulado
(use `--refazer` para recalcular). Em `config.json`, `"lote": {"3": 99999, "5": 99999, "6": 99999, "7": 99999}`
define quantos candidatos por cargo (código do cargo: 3 governador, 5 senador, 6 deputado
federal, 7 deputado estadual) e `"permutacoes_lote"` (padrão 199) controla as permutações dos testes.
A primeira leitura do CSV de cada cargo é a parte lenta e fica em cache em `dados/.cache`.
Para os nomes dos candidatos de cada cargo, rode antes o `baixar_rs_completo.py` (baixa as listas).

`python servir.py` abre o site em http://localhost:8000. Em `config.json`, `"ufs"` lista as UFs
(cada uma precisa de `votacao_secao_ANO_UF.csv` e `UF_Municipios_*.shp`, que o `baixar_rs_completo.py`
baixa) e `"destaques"` define os candidatos dos cards com foto, analisados sempre com o rigor completo.

## Análise nacional (esquerda, todas as UFs)

    python rodar_brasil.py --plano     # quantos candidatos entram e quanto tempo leva
    python rodar_brasil.py             # roda tudo, em paralelo, retomável (Ctrl+C e rodar de novo continua)

Veja o cabeçalho de `rodar_brasil.py` para as opções (`--paralelas`, `--so=`, `--cargos=`, `--espectros`).

## Site com análise calculada no navegador (sem páginas pré-calculadas)

    python converter_parquet.py --uf todas      # CSV de votação -> Parquet por UF (dados_web/); uns 10 s por UF
    python montar_site_web.py --servir          # monta ../site e abre em http://localhost:8000

O navegador lê os Parquet da UF (só o trecho do candidato escolhido) e calcula a análise em etapas num Web Worker.
Qualquer candidato de qualquer cargo e UF abre sem rodar o pipeline em Python. Código do motor em motor_src/.
