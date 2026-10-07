// Gerado a partir de fixtures/conteudo.json (textos fixos de eleicao/conteudo.py). Nao editar a mao.
export const REFS = {
 "moran": "Moran, P. A. P. (1950). Notes on continuous stochastic phenomena. <i>Biometrika</i>, 37(1/2), 17–23.",
 "lisa": "Anselin, L. (1995). Local indicators of spatial association—LISA. <i>Geographical Analysis</i>, 27(2), 93–115.",
 "pysal": "Rey, S. J., &amp; Anselin, L. (2007). PySAL: a Python library of spatial analytical methods. <i>The Review of Regional Studies</i>, 37(1), 5–27. (Cálculos com os módulos esda e libpysal.)",
 "gini": "Gini, C. (1912). <i>Variabilità e mutabilità</i>. Bologna: Tipografia di Paolo Cuppini.",
 "white": "White, H. (1980). A heteroskedasticity-consistent covariance matrix estimator and a direct test for heteroskedasticity. <i>Econometrica</i>, 48(4), 817–838.",
 "mackinnon": "MacKinnon, J. G., &amp; White, H. (1985). Some heteroskedasticity-consistent covariance matrix estimators with improved finite sample properties. <i>Journal of Econometrics</i>, 29(3), 305–325.",
 "harvey": "Harvey, A. C. (1976). Estimating regression models with multiplicative heteroscedasticity. <i>Econometrica</i>, 44(3), 461–465.",
 "getis": "Getis, A., &amp; Ord, J. K. (1992). The analysis of spatial association by use of distance statistics. <i>Geographical Analysis</i>, 24(3), 189–206.",
 "ord95": "Ord, J. K., &amp; Getis, A. (1995). Local spatial autocorrelation statistics: distributional issues and an application. <i>Geographical Analysis</i>, 27(4), 286–306.",
 "laakso": "Laakso, M., &amp; Taagepera, R. (1979). “Effective” number of parties: a measure with application to West Europe. <i>Comparative Political Studies</i>, 12(1), 3–27.",
 "isard": "Isard, W. (1960). <i>Methods of Regional Analysis: an introduction to regional science</i>. Cambridge, MA: Technology Press of MIT; New York: John Wiley &amp; Sons.",
 "duncan": "Duncan, O. D., &amp; Duncan, B. (1955). A methodological analysis of segregation indexes. <i>American Sociological Review</i>, 20(2), 210–217.",
 "wartenberg": "Wartenberg, D. (1985). Multivariate spatial correlation: a method for exploratory geographical analysis. <i>Geographical Analysis</i>, 17(4), 263–283.",
 "dunn": "Dunn, E. S. (1960). A statistical and analytical technique for regional analysis. <i>Papers of the Regional Science Association</i>, 6(1), 97–112.",
 "anselin88": "Anselin, L. (1988). <i>Spatial Econometrics: methods and models</i>. Dordrecht: Kluwer Academic.",
 "slx": "Halleck Vega, S., &amp; Elhorst, J. P. (2015). The SLX model. <i>Journal of Regional Science</i>, 55(3), 339–363.",
 "tobler": "Tobler, W. R. (1970). A computer movie simulating urban growth in the Detroit region. <i>Economic Geography</i>, 46(sup1), 234–240.",
 "spearman": "Spearman, C. (1904). The proof and measurement of association between two things. <i>The American Journal of Psychology</i>, 15(1), 72–101."
};
export const PARTES = [
 [
  "A",
  "Panorama e concentração",
  [
   "panorama",
   "concentracao",
   "vizinhanca",
   "cidades"
  ]
 ],
 [
  "B",
  "Comparação com outros candidatos",
  [
   "comparacao",
   "sobreposicao",
   "federacao"
  ]
 ],
 [
  "C",
  "Modelagem e prioridades",
  [
   "modelo",
   "distancia",
   "potencial"
  ]
 ],
 [
  "D",
  "Contexto e método",
  [
   "contexto",
   "contas",
   "metodo"
  ]
 ]
];
export const NOTAS = {
 "panorama": [
  "<b>% de votos válidos</b> = votos do candidato ÷ votos válidos do município (nominais e de legenda; sem brancos e nulos). <b>Quociente locacional</b> = % do candidato no município ÷ % dele no estado; acima de 1, o município vota nele mais do que a média. <b>Votos por 100 aptos</b> = votos ÷ eleitores aptos × 100. Todos os valores são somas dos boletins de urna por município; o total estadual do candidato confere com o resultado oficial.",
  [
   "isard"
  ]
 ],
 "concentracao": [
  "A curva de Pareto ordena os municípios do mais para o menos votado e acumula a participação nos votos do candidato (é uma curva de concentração, descritiva). O <b>Gini</b> mede a desigualdade da distribuição dos votos entre os municípios (0 = iguais em todos; 1 = todos em um só) e inclui os municípios sem voto. O <b>número efetivo</b> de municípios é 1/Σs², em que s é a fração dos votos do candidato em cada município (Laakso e Taagepera propuseram a medida para partidos; aqui ela é aplicada a municípios).",
  [
   "gini",
   "laakso"
  ]
 ],
 "vizinhanca": [
  "<b>Moran global</b>: correlação entre a % de votos válidos de cada município e a média dessa % entre os vizinhos. Vizinhos = municípios que dividem divisa ou vértice (critério da rainha), com pesos padronizados por linha. A significância é um pseudo-p por 999 permutações, e por isso o menor valor possível é 0,001. <b>LISA</b>: decomposição local do Moran; classifica cada município em Alto-Alto, Baixo-Baixo ou contraste (um valor alto entre baixos, ou o inverso), com pseudo-p &lt; 0,05 por permutação condicional. Esse corte vale para cada município isoladamente, sem correção para comparações múltiplas: com centenas de municípios, parte das manchas marcadas pode ser acaso, e a lista deve ser lida como indicação. Cálculo com esda 2.7 e libpysal 4.13.",
  [
   "moran",
   "lisa",
   "pysal"
  ]
 ],
 "cidades": [
  "Os dados por zona eleitoral vêm da soma dos boletins de urna das seções de cada zona. O TSE não publica voto por bairro, e os nomes dos locais de votação não estão nesta base.",
  []
 ],
 "comparacao": [
  "Para cada partido entra o candidato mais votado do estado no mesmo cargo. As medidas de abrangência contam municípios em que o candidato teve algum voto e aqueles em que teve 0,5%, 1% e 5% ou mais dos votos válidos do município. Gini e número efetivo são os mesmos da seção 2 e o Moran é o da seção 3 (999 permutações para o candidato em foco; 199 para a tabela comparativa, cujo menor p possível é 0,005).",
  [
   "gini",
   "moran"
  ]
 ],
 "sobreposicao": [
  "<b>Sobreposição</b> = Σ min(sᵢ, tᵢ), em que s e t são as frações dos votos de cada candidato em cada município. Vale 100% quando as distribuições coincidem e 0 quando não têm município em comum; é o complemento do índice de dissimilaridade de Duncan e Duncan (100% − D). <b>Correlação</b>: Pearson entre as % de votos válidos dos dois candidatos nos municípios (não ponderada). <b>Moran bivariado</b>: associação entre a % do candidato em foco em cada município e a média da % do outro nos vizinhos (Σ zx·W zy ÷ n, com os pesos da seção 3), segundo a lógica de correlação espacial multivariada de Wartenberg; pseudo-p por 199 permutações. Só entram candidatos com ao menos 1.000 votos.",
  [
   "duncan",
   "wartenberg",
   "pysal"
  ]
 ],
 "federacao": [
  "Participação = votos nominais do candidato ÷ votos nominais de todos os candidatos dos partidos da federação no município (votos de legenda não entram). O <b>esperado</b> é o total da federação no município vezes a participação média do candidato no estado; a soma dos esperados é igual à soma dos votos observados. A lógica é a do componente diferencial da análise shift-share (Dunn, 1960), usada por analogia: compara o desempenho local com o que ocorreria se o candidato tivesse a mesma participação em todo lugar. A composição da federação é a registrada no TSE em 05/10/2026.",
  [
   "dunn"
  ]
 ],
 "modelo": [
  "Regressão por mínimos quadrados ponderados (peso = votos válidos do município) da % de votos válidos do candidato sobre o logaritmo do eleitorado, a abstenção, a % do resto da federação no município e a % do resto da federação nos vizinhos (defasagem espacial das covariáveis, o modelo SLX). Os erros-padrão e os valores de p são robustos a heterocedasticidade (HC1), porque a dispersão dos resíduos cresce com o porte do município. O R² é ponderado. O <b>resíduo padronizado</b> divide o resíduo (em pontos percentuais) da dispersão típica de municípios do mesmo porte, estimada por variância multiplicativa; |z| &gt; 2 é destacado. O Moran dos resíduos padronizados (199 permutações) testa se sobrou padrão espacial. O modelo descreve associações; não identifica causas.",
  [
   "anselin88",
   "slx",
   "white",
   "mackinnon",
   "harvey",
   "moran"
  ]
 ],
 "distancia": [
  "Distância em linha reta entre centroides dos municípios, calculada em projeção UTM (a diferença para a distância geodésica é de no máximo 0,3% neste estado), até o mais próximo dos 5 municípios mais votados do candidato. A associação entre distância e % de votos válidos é a correlação de Spearman (postos), calculada sem os redutos e incluindo municípios sem voto; é descritiva, porque municípios vizinhos não são observações independentes e o valor de p convencional seria otimista. Que a votação decaia com a distância é a ideia da primeira lei da geografia, de Tobler.",
  [
   "tobler",
   "spearman"
  ]
 ],
 "potencial": [
  "<b>Votos por 100 aptos</b> = votos ÷ eleitores aptos × 100. <b>Votos até a média</b> = quanto faltaria para o município atingir a % de votos válidos que o candidato tem no estado (zero quando ele já a atinge). É uma medida de oportunidade, não uma previsão.",
  []
 ],
 "contexto": [
  "Abstenção = 1 − (votos de todos os candidatos, brancos e nulos ÷ eleitores aptos). É uma aproximação: o numerador vem dos boletins de urna e o denominador, do cadastro de aptos por seção.",
  []
 ]
};
export const INTRO = {
 "A": "Quanto voto o candidato teve, onde ele se concentra e se há padrão de vizinhança.",
 "B": "Posição do candidato frente aos mais votados dos outros partidos e à própria federação.",
 "C": "O que o modelo espera de cada município e onde vale concentrar esforço.",
 "D": "Partido, abstenção, prestação de contas, fontes e referências."
};
export const GUIA = "\n<details class=\"guide\" id=\"guia\"><summary>Como ler este relatório: o que significam os números e mapas</summary>\n<dl>\n<dt>% dos votos válidos</dt><dd><p>De cada 100 votos válidos dados no município (sem brancos e nulos), quantos foram para o\ncandidato. É o melhor jeito de comparar cidades grandes e pequenas.</p></dd>\n<dt>Quociente locacional</dt><dd><p>A % do candidato no município dividida pela % dele no estado inteiro.\n<em>1</em> = igual à média; <em>3</em> = o município vota nele três vezes mais que a média; <em>0,5</em> = metade.\nServe para achar onde ele é proporcionalmente forte, mesmo em cidade pequena.</p></dd>\n<dt>Gini (concentração)</dt><dd><p>Mede quanto os votos estão concentrados em poucos municípios. Vai de <em>0</em> a <em>1</em>.\nPerto de 0, os votos estão espalhados de forma parecida por todo o estado. Perto de 1, quase tudo vem de pouquíssimos\nmunicípios. Ele não desconta o tamanho da cidade: uma capital grande já tem mais votos só por ter mais eleitores.\nPor isso vale olhar junto o gráfico de concentração (seção 2).</p></dd>\n<dt>Moran global (vizinhança)</dt><dd><p>Responde a uma pergunta só: <em>municípios vizinhos tendem a ter votação parecida?</em>\nVai de <em>−1</em> a <em>+1</em>. Perto de 0, não há padrão geográfico. Positivo, a votação forma manchas no mapa\n(vizinhos fortes juntos, vizinhos fracos juntos). Negativo, os vizinhos tendem a ser opostos, como um tabuleiro de xadrez.\nO <em>p</em> diz se o resultado pode ser acaso: abaixo de 0,05, é improvável que seja.</p></dd>\n<dt>Eficiência e potencial</dt><dd><p><em>Votos por 100 aptos</em> mostra quanto do eleitorado o candidato converteu em voto em cada município.\n<em>Votos até a média</em> é quantos votos a mais o município daria se votasse nele como o estado inteiro. É um indicador para priorizar,\nnão uma projeção.</p></dd>\n<dt>Abrangência</dt><dd><p>Em quantos municípios o candidato teve presença relevante (1% ou mais dos votos válidos). Serve para comparar\nalcance geográfico entre candidatos, separado do total de votos.</p></dd>\n<dt>LISA (clusters)</dt><dd><p>É o Moran feito município por município. Para cada um, compara a sua votação com a média dos\nvizinhos que fazem divisa. Só colore o que for estatisticamente significativo:\n<em>Alto-Alto</em> (vermelho) = forte e cercado de vizinhos fortes, ou seja, um <b>núcleo de força</b>;\n<em>Baixo-Baixo</em> (azul) = fraco e cercado de vizinhos fracos, ou seja, um vazio;\n<em>Outlier</em> (dourado) = contraste: forte em meio a fracos é uma <b>ilha de voto</b>; fraco em meio a fortes é uma lacuna, a oportunidade mais barata. A seção 3 explica cada um;\ncinza = sem padrão claro. Quando o candidato tem poucos votos, o Baixo-Baixo costuma ser só &quot;não teve voto&quot;;\no mais útil costuma ser o Alto-Alto e os outliers.</p></dd>\n</dl></details>\n";
export const GUIA_HEX = "<dt>Hexágonos (H3)</dt><dd><p>Dentro das cidades, o TSE só informa os votos por seção eleitoral, e cada seção funciona num local\nde votação (uma escola, por exemplo) com endereço e coordenada. Os locais são agrupados em hexágonos de tamanho igual, o que\ndeixa o mapa comparável e evita que uma escola isolada pareça uma região. As zonas eleitorais não têm limite público em mapa,\nentão aparecem em tabela e no texto de cada hexágono. Atenção: o mapa mostra onde as pessoas <em>votam</em>, que costuma ser perto,\nmas não é exatamente onde moram.</p></dd>\n<dt>Ponto quente / frio (Gi*)</dt><dd><p>É o equivalente do LISA para os hexágonos de uma cidade. <em>Ponto quente</em> = hexágono e\nvizinhos com % de votos acima do esperado; <em>ponto frio</em> = abaixo do esperado. Só aparecem os significativos\n(p &lt; 0,05); o resto fica cinza.</p></dd>\n";
