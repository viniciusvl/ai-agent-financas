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
