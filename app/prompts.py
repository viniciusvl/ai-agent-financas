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
