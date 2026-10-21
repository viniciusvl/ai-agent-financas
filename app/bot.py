"""Orquestração do fluxo do bot (v2): mensagem → (STT) → roteador (Jev) →
escrita (extração → confirmação → planilha) | leitura (consulta) | outro.

Spec: specs/tasks/T16-bot-flow-v2.md
"""

import asyncio
import html
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.extractor import ExtractionError
from app.messages import (
    MSG_CALLBACK_CANCELLED,
    MSG_CALLBACK_SAVED,
    MSG_CANCELLED,
    MSG_EXPIRED,
    MSG_EXTRACTION_FAILED,
    MSG_HELP,
    MSG_LEITURA_FAILED,
    MSG_NOT_EXPENSE,
    MSG_NOT_OWNER,
    MSG_OUTRO,
    MSG_ROUTER_FAILED,
    MSG_SAVE_FAILED,
    MSG_SAVED_HEADER,
    MSG_TRANSCRIPTION,
    MSG_TRANSCRIPTION_FAILED,
    MSG_UNAUTHORIZED,
)
from app.payment import MetodoPagamento, Pagamento
from app.queries import ReadError, format_valor
from app.router import Intencao, RouterError
from app.sheets import SheetsError
from app.telegram_api import confirmation_keyboard

logger = logging.getLogger(__name__)

# Comandos aceitos (o sufixo ``@NomeDoBot`` é ignorado).
_COMANDOS = frozenset({"/start", "/help"})

# Por quanto tempo um id confirmado é lembrado (evita "expirou" no toque duplo).
CONFIRMADOS_TTL = timedelta(minutes=10)

METODO_LABEL: dict[MetodoPagamento, str] = {
    MetodoPagamento.DINHEIRO: "dinheiro",
    MetodoPagamento.DEBITO: "débito",
    MetodoPagamento.CREDITO_A_VISTA: "crédito à vista",
    MetodoPagamento.CREDITO_PARCELADO: "crédito parcelado",
    MetodoPagamento.PIX: "Pix",
    MetodoPagamento.BOLETO: "boleto",
    MetodoPagamento.TRANSFERENCIA: "transferência",
    MetodoPagamento.OUTRO: "outro",
}


def _format_pagamento(pagamento: Pagamento) -> str:
    """Linha de forma de pagamento, detalhando parcelas quando aplicável."""
    label = METODO_LABEL[pagamento.metodo_pagamento]
    n = pagamento.quant_parcelas
    if pagamento.metodo_pagamento is MetodoPagamento.CREDITO_PARCELADO and n >= 2:
        parcela = format_valor(pagamento.moeda, pagamento.valor_parcela)
        primeira = pagamento.valor_primeira_parcela
        if primeira != pagamento.valor_parcela:
            primeira_txt = format_valor(pagamento.moeda, primeira)
            return f"{label} em {n}x (1ª de {primeira_txt} + {n - 1}x de {parcela})"
        return f"{label} em {n}x de {parcela}"
    return label


def _format_data(pagamento: Pagamento) -> str:
    """Data (`dd/mm/aaaa`) com hora (`HH:MM`) quando informada."""
    texto = pagamento.data.strftime("%d/%m/%Y")
    if pagamento.hora is not None:
        texto += pagamento.hora.strftime(" %H:%M")
    return texto


def format_confirmacao(pagamento: Pagamento) -> str:
    """Mensagem (HTML) pedindo confirmação do pagamento. Ver spec T16."""
    linhas = [
        "📝 <b>Confirme o pagamento:</b>",
        f"• Valor: {format_valor(pagamento.moeda, pagamento.valor_compra)}",
        f"• Pagamento: {_format_pagamento(pagamento)}",
        f"• Categoria: {pagamento.categoria.value}",
        f"• Descrição: {html.escape(pagamento.descricao)}",
        f"• Data: {_format_data(pagamento)}",
    ]
    return "\n".join(linhas)


def format_registrado(pagamento: Pagamento) -> str:
    """Mensagem (HTML) após gravar o pagamento. Ver spec T16."""
    linhas = format_confirmacao(pagamento).split("\n")
    return "\n".join([MSG_SAVED_HEADER, *linhas[1:]])


def _is_command(text: str) -> bool:
    """True quando o texto é `/start` ou `/help` (aceitando `@NomeDoBot`)."""
    partes = text.strip().split()
    if not partes:
        return False
    return partes[0].split("@", 1)[0] in _COMANDOS


class BotService:
    def __init__(
        self,
        telegram: Any,
        transcriber: Any,
        router: Any,
        extractor: Any,
        read_agent: Any,
        store: Any,
        writer: Any,
        allowed_user_ids: set[int],
        timezone: str = "America/Sao_Paulo",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.telegram = telegram
        self.transcriber = transcriber
        self.router = router
        self.extractor = extractor
        self.read_agent = read_agent
        self.store = store
        self.writer = writer
        self.allowed_user_ids = set(allowed_user_ids)
        self.timezone = timezone
        self.clock = clock if clock is not None else (lambda: datetime.now(ZoneInfo(timezone)))
        # Ids confirmados com sucesso e o instante da confirmação (toque duplo).
        self._confirmados: dict[str, datetime] = {}

    async def handle_update(self, update: dict[str, Any]) -> None:
        """Processa um Update do Telegram. Nunca propaga exceções."""
        try:
            await self._dispatch(update)
        except Exception:  # noqa: BLE001 - qualquer falha vira log; o bot nunca derruba
            logger.exception("Erro ao processar update")

    async def _dispatch(self, update: dict[str, Any]) -> None:
        """Roteia o update: callbacks ou mensagens (texto/voz) autorizadas."""
        callback = update.get("callback_query")
        if callback:
            await self._handle_callback(callback)
            return
        message = update.get("message")
        if not message:
            return
        user_id = (message.get("from") or {}).get("id")
        chat_id = (message.get("chat") or {}).get("id")
        if user_id not in self.allowed_user_ids:
            await self.telegram.send_message(chat_id, MSG_UNAUTHORIZED.format(user_id=user_id))
            return

        text = await self._resolve_text(chat_id, message)
        if text is None:
            return
        if _is_command(text):
            await self.telegram.send_message(chat_id, MSG_HELP)
            return
        await self._process_text(chat_id, user_id, text, self._recebido_em(message))

    async def _resolve_text(self, chat_id: int, message: dict[str, Any]) -> str | None:
        """Devolve o texto da mensagem, transcrevendo voz/áudio quando necessário."""
        if "text" in message:
            return message["text"]
        if "voice" in message:
            media, filename = message["voice"], "voice.ogg"
        elif "audio" in message:
            media = message["audio"]
            filename = media.get("file_name") or "audio.ogg"
        else:
            return None
        try:
            audio = await self.telegram.download_file(media["file_id"])
            transcribed = await self.transcriber.transcribe(audio, filename)
        except Exception:  # noqa: BLE001 - download/transcrição podem falhar de várias formas
            logger.exception("Falha ao baixar/transcrever áudio")
            await self.telegram.send_message(chat_id, MSG_TRANSCRIPTION_FAILED)
            return None
        await self.telegram.send_message(
            chat_id, MSG_TRANSCRIPTION.format(text=html.escape(transcribed))
        )
        return transcribed

    def _recebido_em(self, message: dict[str, Any]) -> datetime:
        """Horário da mensagem (UTC); sem `date`, usa o relógio do serviço."""
        timestamp = message.get("date")
        if timestamp is None:
            return self.clock()
        return datetime.fromtimestamp(timestamp, tz=UTC)

    async def _process_text(
        self, chat_id: int, user_id: int, text: str, recebido_em: datetime
    ) -> None:
        """Roteia o texto entre escrita, leitura e outro."""
        try:
            rota = await self.router.route(text)
        except RouterError:
            logger.exception("Falha ao rotear a mensagem")
            await self.telegram.send_message(chat_id, MSG_ROUTER_FAILED)
            return
        logger.info(
            "Mensagem roteada: intencao=%s origem=%s confianca=%.3f",
            rota.intencao,
            rota.origem,
            rota.confianca,
        )
        if rota.intencao is Intencao.ESCRITA:
            await self._handle_escrita(chat_id, user_id, text, recebido_em)
        elif rota.intencao is Intencao.LEITURA:
            await self._handle_leitura(chat_id, text, recebido_em)
        else:
            await self.telegram.send_message(chat_id, MSG_OUTRO)

    async def _handle_escrita(
        self, chat_id: int, user_id: int, text: str, recebido_em: datetime
    ) -> None:
        """Extrai o pagamento, pergunta o que faltar e pede confirmação."""
        try:
            resultado = await self.extractor.extract(text, recebido_em)
        except ExtractionError:
            logger.exception("Falha ao extrair o pagamento")
            await self.telegram.send_message(chat_id, MSG_EXTRACTION_FAILED)
            return
        if resultado.erro:
            await self.telegram.send_message(chat_id, MSG_NOT_EXPENSE.format(reason=resultado.erro))
            return
        if resultado.pergunta:
            await self.telegram.send_message(chat_id, resultado.pergunta)
            return
        pagamento = resultado.pagamento
        pending_id = self.store.save(chat_id, user_id, pagamento)
        await self.telegram.send_message(
            chat_id,
            format_confirmacao(pagamento),
            reply_markup=confirmation_keyboard(pending_id),
        )

    async def _handle_leitura(self, chat_id: int, text: str, recebido_em: datetime) -> None:
        """Responde a uma consulta usando o agente de leitura."""
        try:
            resposta = await self.read_agent.answer(text, recebido_em)
        except ReadError:
            logger.exception("Falha ao consultar a planilha")
            await self.telegram.send_message(chat_id, MSG_LEITURA_FAILED)
            return
        await self.telegram.send_message(chat_id, resposta)

    async def _handle_callback(self, callback: dict[str, Any]) -> None:
        """Trata `confirm:<id>` / `cancel:<id>` de um callback_query autorizado."""
        callback_id = callback["id"]
        user_id = (callback.get("from") or {}).get("id")
        if user_id not in self.allowed_user_ids:
            await self.telegram.answer_callback_query(
                callback_id, MSG_UNAUTHORIZED.format(user_id=user_id)
            )
            return
        data = callback.get("data") or ""
        acao, _, pending_id = data.partition(":")
        if acao not in {"confirm", "cancel"}:
            await self.telegram.answer_callback_query(callback_id)
            return
        message = callback.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        message_id = message.get("message_id")
        pendente = self.store.get(pending_id)
        if pendente is None:
            if acao == "confirm" and self._ja_confirmado(pending_id):
                await self.telegram.answer_callback_query(callback_id, MSG_CALLBACK_SAVED)
                return
            await self.telegram.answer_callback_query(callback_id, MSG_EXPIRED)
            await self.telegram.edit_message_text(chat_id, message_id, MSG_EXPIRED)
            return
        if pendente.user_id != user_id:
            await self.telegram.answer_callback_query(callback_id, MSG_NOT_OWNER)
            return
        if acao == "cancel":
            self.store.delete(pending_id)
            await self.telegram.edit_message_text(chat_id, message_id, MSG_CANCELLED)
            await self.telegram.answer_callback_query(callback_id, MSG_CALLBACK_CANCELLED)
            return
        await self._confirmar(
            callback_id, chat_id, message_id, pending_id, pendente, callback.get("from") or {}
        )

    async def _confirmar(
        self,
        callback_id: str,
        chat_id: int,
        message_id: Any,
        pending_id: str,
        pendente: Any,
        sender: dict[str, Any],
    ) -> None:
        """Grava o pendente confirmado; em falha da planilha, mantém para nova tentativa."""
        pagamento = pendente.expense
        try:
            await asyncio.to_thread(
                self.writer.append_pagamento,
                pagamento,
                self._user_name(sender),
                self.clock(),
                pending_id,
            )
        except SheetsError:
            logger.exception("Falha ao gravar na planilha")
            await self.telegram.answer_callback_query(callback_id, MSG_SAVE_FAILED)
            return
        self.store.delete(pending_id)
        self._marcar_confirmado(pending_id)
        await self.telegram.edit_message_text(chat_id, message_id, format_registrado(pagamento))
        await self.telegram.answer_callback_query(callback_id, MSG_CALLBACK_SAVED)

    def _purgar_confirmados(self, agora: datetime) -> None:
        """Descarta os ids confirmados há mais de ``CONFIRMADOS_TTL``."""
        vencidos = [
            pending_id
            for pending_id, quando in self._confirmados.items()
            if agora - quando > CONFIRMADOS_TTL
        ]
        for pending_id in vencidos:
            del self._confirmados[pending_id]

    def _marcar_confirmado(self, pending_id: str) -> None:
        """Lembra um id gravado com sucesso, com o instante da confirmação."""
        agora = self.clock()
        self._purgar_confirmados(agora)
        self._confirmados[pending_id] = agora

    def _ja_confirmado(self, pending_id: str) -> bool:
        """True quando o id foi confirmado há no máximo ``CONFIRMADOS_TTL``."""
        agora = self.clock()
        self._purgar_confirmados(agora)
        return pending_id in self._confirmados

    @staticmethod
    def _user_name(sender: dict[str, Any]) -> str:
        """Nome do usuário para a planilha: nome completo, senão username, senão id."""
        nome = " ".join(p for p in (sender.get("first_name"), sender.get("last_name")) if p)
        if nome:
            return nome
        return sender.get("username") or str(sender.get("id"))
