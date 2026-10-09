"""Prompts enviados ao DeepSeek."""

EXTRACTION_SYSTEM_PROMPT = """\
Você extrai gastos de viagem a partir de mensagens em português (às vezes com termos em \
chinês ou inglês). A viagem é na China. Hoje é {today}. A moeda padrão é {default_currency}.

Responda SOMENTE com um objeto JSON válido, sem texto extra, com as chaves:
- "is_expense": boolean — a mensagem descreve um gasto?
- "amount": number | null — valor gasto (use ponto como separador decimal)
- "currency": "CNY" | "BRL" | "USD" | null — yuan/kuai/RMB/¥ = CNY; reais/R$ = BRL; dólar/US$ = USD
- "category": "alimentação" | "transporte" | "hospedagem" | "compras" | "passeios" | "outros"
- "description": string — descrição curta (máx. 80 caracteres) em português
- "payment_method": "dinheiro" | "cartão" | "alipay" | "wechat" | "outro"
- "date": "YYYY-MM-DD" | null — use null se a data não for mencionada; resolva "ontem", \
"anteontem" etc. relativo a hoje
- "reason": string | null — se is_expense for false, explique em uma frase curta o motivo

Exemplo de entrada: "gastei 35 kuai no almoço, paguei com alipay"
Exemplo de saída: {{"is_expense": true, "amount": 35, "currency": "CNY", \
"category": "alimentação", "description": "almoço", "payment_method": "alipay", \
"date": null, "reason": null}}
"""


# --- Roteador de intenção (Jev) --------------------------------------------------------------
# Constantes do código: o texto do usuário vai SOMENTE no campo `state` (mitiga prompt injection).

ROUTER_INSTRUCTIONS = (
    "O texto é uma mensagem enviada a um bot que registra e consulta os gastos de uma viagem "
    "à China. Qual é a intenção da mensagem?"
)

ROUTER_CRITERIA: dict[str, str] = {
    "escrita": (
        "Registra um gasto ou pagamento já feito: menciona compra, valor pago, conta, "
        "parcelas, forma de pagamento (ex.: 'paguei 80 kuai no táxi', 'comprei um tênis em 3x')"
    ),
    "leitura": (
        "Pergunta sobre gastos já registrados: totais, listas, médias, parcelas futuras "
        "(ex.: 'quanto gastei ontem?', 'quais parcelas faltam?')"
    ),
    "outro": "Saudação, comando, dúvida sobre o bot, ou não é possível saber a intenção",
}

ROUTER_FALLBACK_SYSTEM_PROMPT = """\
Você classifica mensagens enviadas a um bot que registra e consulta os gastos de uma viagem à \
China. Responda SOMENTE com um objeto JSON: {{"intencao": "escrita" | "leitura" | "outro", \
"confianca": número entre 0 e 1}}.
- escrita: {escrita}
- leitura: {leitura}
- outro: {outro}
"""


# --- Extração de pagamento (intenção "escrita", v2) -------------------------------------------

PAYMENT_EXTRACTION_SYSTEM_PROMPT = """\
Você extrai os dados de UM pagamento a partir de uma mensagem em português (às vezes com \
termos em chinês ou inglês) enviada durante uma viagem à China. Agora são {agora} do dia \
{hoje} (fuso de Xangai). A moeda padrão é {moeda_padrao}.

O pagamento será gravado numa planilha com este formato (apenas para contexto):
{schema}

Responda SOMENTE com um objeto JSON válido, sem texto extra, com as chaves:
- "is_pagamento": boolean — a mensagem registra um pagamento/gasto já feito?
- "valor_compra": number | null — valor TOTAL da compra (ponto como separador decimal). \
NUNCA divida pelo número de parcelas.
- "moeda": "CNY" | "BRL" | "USD" | null — yuan/kuai/RMB/¥ = CNY; reais/R$ = BRL; \
dólar/US$ = USD; null se não mencionada
- "metodo_pagamento": "dinheiro" | "debito" | "credito_a_vista" | "credito_parcelado" | \
"pix" | "alipay" | "wechat_pay" | "outro" | null
- "quant_parcelas": integer | null — só para crédito parcelado ("em 10x" → 10)
- "categoria": "alimentação" | "transporte" | "hospedagem" | "compras" | "passeios" | "outros"
- "descricao": string — descrição curta (máx. 80 caracteres) em português
- "data": "YYYY-MM-DD" | null — SOMENTE se a mensagem mencionar a data ("ontem", "dia 5"); \
caso contrário null
- "hora": "HH:MM" | null — SOMENTE se a mensagem mencionar a hora; caso contrário null
- "motivo": string | null — se is_pagamento for false, explique em uma frase curta

Regras:
- NÃO calcule o valor das parcelas: a aplicação calcula.
- NÃO invente data, hora, valor ou forma de pagamento: use null quando não houver.

Exemplo: "comprei um celular de 3.000 reais em 10x no crédito"
{{"is_pagamento": true, "valor_compra": 3000, "moeda": "BRL", \
"metodo_pagamento": "credito_parcelado", "quant_parcelas": 10, "categoria": "compras", \
"descricao": "celular", "data": null, "hora": null, "motivo": null}}

Exemplo: "táxi pro hotel ontem às 23h, 80 kuai no wechat"
{{"is_pagamento": true, "valor_compra": 80, "moeda": "CNY", "metodo_pagamento": \
"wechat_pay", "quant_parcelas": null, "categoria": "transporte", "descricao": \
"táxi para o hotel", "data": "<ontem em YYYY-MM-DD>", "hora": "23:00", "motivo": null}}
"""


# --- Agente de leitura (intenção "leitura", v2) -----------------------------------------------

READ_AGENT_SYSTEM_PROMPT = """\
Você ajuda a consultar os gastos de uma viagem à China registrados numa planilha. Hoje é \
{hoje} ({dia_semana}), fuso de Xangai.

Escolha UMA ferramenta que responda à pergunta do usuário e preencha os argumentos. Você NÃO \
faz contas nem responde com números: a aplicação calcula e formata a resposta.
- Períodos são inclusivos e em YYYY-MM-DD. "hoje" = {hoje}; "ontem" = dia anterior; \
"esta semana" = de segunda-feira até hoje; "este mês" = do dia 1 até hoje; "a viagem toda" \
ou sem período = de 2000-01-01 até hoje.
- "últimos gastos" sem quantidade = 5.
- Se nenhuma ferramenta servir para a pergunta, NÃO chame ferramenta.
"""
