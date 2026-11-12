# Matriz de comparação de tipos

`cases.json` fixa os resultados esperados das entradas e respostas antes da
execução dos testes. Cada caso verifica o resultado, a presença ou ausência
de achados e os vínculos de evidência. `test_types.py` constrói as fontes sem
executar os projetos analisados.

O recorte usa operações da implementação: getters de JsonElement, int.Parse
de parâmetro FromQuery string e métodos de string/número aplicados ao JSON
recebido. Respostas resolvidas usam Content com JSON e media type literais.
Tipos declarados e atributos de contrato não sobrescrevem esses fatos.

Casos dinâmicos, condicionais, respostas não resolvidas, relações candidatas,
serialização customizada e caminhos não cobertos permanecem como lacunas.
O documento de exemplo é preenchido e validado no teste de integração.
