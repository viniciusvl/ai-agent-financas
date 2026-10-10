"""Textos enviados pelo bot (HTML do Telegram). Fonte única de copy."""

MSG_HELP = (
    "👋 <b>Olá! Sou seu assistente de gastos.</b>\n\n"
    "Envie um texto ou um áudio descrevendo o gasto, por exemplo:\n"
    "• <i>gastei 35 reais no almoço, paguei no pix</i>\n"
    "• <i>comprei um tênis de 600 reais em 3x no crédito</i>\n\n"
    "Eu interpreto e peço sua confirmação antes de salvar na planilha. "
    "Também respondo perguntas como <i>quanto gastei esta semana?</i>"
)
MSG_UNAUTHORIZED = "⛔ Acesso não autorizado. Seu ID do Telegram: <code>{user_id}</code>"
MSG_NOT_EXPENSE = "🤔 {reason}\n\nTente algo como: <i>gastei 35 reais no almoço</i>"
MSG_TRANSCRIPTION = "🎙️ Transcrição: <i>{text}</i>"
MSG_TRANSCRIPTION_FAILED = (
    "😕 Não consegui entender o áudio. Pode tentar de novo ou mandar por texto?"
)
MSG_EXTRACTION_FAILED = (
    "😕 Não consegui processar sua mensagem agora. Tente novamente em instantes."
)
MSG_SAVED_HEADER = "✅ <b>Gasto registrado!</b>"
MSG_SAVE_FAILED = "⚠️ Falha ao salvar na planilha. Toque em Confirmar novamente para tentar de novo."
MSG_CANCELLED = "❌ Registro cancelado."
MSG_EXPIRED = "⌛ Este registro expirou ou já foi processado. Envie o gasto novamente."
MSG_NOT_OWNER = "⛔ Apenas quem enviou o gasto pode confirmá-lo."
MSG_CALLBACK_SAVED = "Registrado!"
MSG_CALLBACK_CANCELLED = "Cancelado"

# --- v2 -----------------------------------------------------------------------------------------
MSG_PERGUNTA_VALOR = "💬 Qual foi o valor desse gasto?"
MSG_PERGUNTA_PARCELAS = "💬 Em quantas parcelas foi essa compra?"
MSG_ROUTER_FAILED = "😕 Não consegui processar sua mensagem agora. Tente novamente em instantes."
MSG_OUTRO = (
    "🤔 Não entendi se você quer <b>registrar</b> um gasto ou <b>consultar</b> seus gastos.\n\n"
    "• Registrar: <i>paguei 80 reais no mercado com pix</i>\n"
    "• Consultar: <i>quanto gastei esta semana?</i>"
)
MSG_LEITURA_NAO_SUPORTADA = (
    "🤔 Ainda não sei responder isso. Posso informar: total por período, total por categoria, "
    "total por forma de pagamento, últimos gastos e parcelas futuras."
)
MSG_LEITURA_FAILED = "😕 Não consegui consultar a planilha agora. Tente novamente em instantes."
MSG_NENHUM_GASTO = "nenhum gasto registrado"
MSG_NENHUMA_PARCELA = "nenhuma parcela futura"
