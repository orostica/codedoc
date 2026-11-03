# Resultados esperados — ticket 03

Matriz fixada antes da implementação do detector. Cada caso de cases.json
representa uma chamada POST para um Controller com destino confirmado.

O frontend declara `name?: string`; essa declaração não basta para concluir
omissão. O detector deve considerar o corpo passado ao fetch. Um objeto inline
com valores JSON primitivos ou uma string JSON literal tem formato determinável.
Valores dinâmicos, spreads, chaves computadas, undefined e replacers ficam
como lacunas nesta entrega. Null conta como chave presente; validar seu valor
ou tipo pertence a outro recorte.

A exigência comprovada é a guarda inicial do método de ação, com parâmetro
FromBody JsonElement, que retorna BadRequest quando TryGetProperty não encontra
uma chave literal. A guarda precisa rejeitar e ser incondicional em relação
a outras regras de negócio. Guardas condicionais, retornos de sucesso prévios,
atributos Required sem resolução de binding/validação e DTOs não resolvidos
não sustentam achados. Eles devem produzir lacunas.

Omissões só podem ser afirmadas em relações confirmadas por destino, método e
rota. Candidatos, endpoints ambíguos e serializações não resolvidas não geram
achados. Content-Type JSON explícito é exigido para a comparação do corpo.

Além da matriz, a integração deve levar o achado ao pacote e a um documento
de exemplo validado, citando as evidências do frontend e do backend. A execução
continua estática, sem invocar agentes ou APIs.
