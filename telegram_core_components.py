from xai_components.base import InArg, OutArg, InCompArg, Component, xai_component, secret, SubGraphExecutor

import asyncio
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CommandHandler, MessageHandler, filters, ContextTypes

@xai_component(color="blue")
class TelegramInitApp(Component):
    """
    Initializes a Telegram Application using python-telegram-bot.

    ##### inPorts:
    - telegram_token (str): The Bot API token from BotFather.

    ##### outPorts:
    - application (object): The initialized Telegram Application object.
    """
    telegram_token: InCompArg[secret]
    application: OutArg[any]

    def execute(self, ctx) -> None:
        from telegram.ext import ApplicationBuilder
        
        token = self.telegram_token.value
        if not token:
            raise ValueError("No Telegram token provided!")
        
        app = ApplicationBuilder().token(token).build()
        self.application.value = app


@xai_component(color="blue")
class TelegramAddEchoHandler(Component):
    """
    Adds an echo handler that echoes all text messages back to the user,
    except those that start with '/' (commands).

    ##### inPorts:
    - application (object): The Telegram Application object (from InitTelegramApp).

    ##### outPorts:
    - application (object): The updated Telegram Application with the echo handler attached.
    """
    application: InCompArg[any]
    application_out: OutArg[any]

    def execute(self, ctx) -> None:

        async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
            """Simply echo all incoming text messages."""
            if update.message and update.message.text:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id, 
                    text=update.message.text
                )

        app = self.application.value
        # Create a filter that grabs all text messages except commands (i.e., no leading '/')
        echo_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), echo)
        app.add_handler(echo_handler)
        
        # Pass the updated app forward
        self.application_out.value = app


@xai_component(color="blue")
class TelegramRunApp(Component):
    """
    Runs the Telegram Application in polling mode.
    This call is blocking until the user stops the execution.

    ##### inPorts:
    - application (object): The Telegram Application (with any handlers attached).
    """
    application: InCompArg[any]

    def execute(self, ctx) -> None:
        app = self.application.value
        if not app:
            raise ValueError("No Telegram Application provided!")
        
        # This is a blocking call, so Xircuits execution will pause here until you stop the bot.
        app.run_polling()

@xai_component(color="green")
class TelegramAddCommandEvent(Component):
    """
    Registers a Telegram command handler that will fire an event in the Xircuits context
    whenever the command is received.

    ##### inPorts:
    - application (object): The Telegram Application object
    - command_name (str): The command (without slash), e.g. "start"
    - event_name (str): The event name to fire in Xircuits, e.g. "my_command_event"

    ##### outPorts:
    - application_out (object): The updated Telegram Application
    """
    application: InArg[object]
    command_name: InArg[str]
    event_name: InArg[str]
    application_out: OutArg[object]

    def execute(self, ctx) -> None:

        app = self.application.value
        cmd = self.command_name.value.strip()
        evt = self.event_name.value.strip()

        if not (app and cmd and evt):
            raise ValueError("Application, command_name, and event_name are required.")


        async def command_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
            # This is called each time user does /<cmd>.
            message_text = " ".join(context.args) if context.args else ""
            chat_id = update.effective_chat.id
            user_id = update.effective_user.id if update.effective_user else None

            # We "fire" an event. Instead of calling FireEvent directly as a component,
            # we can replicate FireEvent logic or we can store something in ctx and run it.
            # For simplicity, let's replicate the logic:
            payload = {
                "command_name": cmd,
                "message_text": message_text,
                "chat_id": chat_id,
                "user_id": user_id,
                "update": update,
            }
            # Check if there's a list of OnEvent listeners
            listeners = ctx.get('events', {}).get(evt, [])
            for listener in listeners:
                listener.payload.value = payload
                # Call do() on the OnEvent. That calls SubGraphExecutor on its body.
                SubGraphExecutor(listener).do(ctx)

        handler = CommandHandler(cmd, command_callback)
        app.add_handler(handler)

        self.application_out.value = app

@xai_component
class TelegramParsePayload(Component):
    """
    Unpacks the standard Telegram payload fields from an event payload dictionary.

    ##### inPorts:
    - event_payload (dict): A dictionary containing keys like:
        {
          "command_name": str,
          "message_text": str,
          "chat_id": int,
          "user_id": int,
          "update": <telegram.Update>
          ...
        }

    ##### outPorts:
    - chat_id (int): The chat ID where the message was sent.
    - user_id (int): The user's Telegram ID.
    - message_text (str): The text after the command or the user's message text.
    - update_obj (object): The entire Update object (telegram.Update).
    - command_name (str): The command name (if provided in payload).
    - first_name (str): The first_name from update.effective_user (if available).

    ##### Usage:
    1. Wire the `event_payload` from an event-based component (e.g. OnEvent) into `TelegramParsePayload`.
    2. Use the outPorts (chat_id, message_text, etc.) in subsequent components.
    """
    event_payload: InArg[dict]

    chat_id: OutArg[int]
    user_id: OutArg[int]
    message_text: OutArg[str]
    update_obj: OutArg[object]
    command_name: OutArg[str]
    first_name: OutArg[str]

    def execute(self, ctx) -> None:
        payload = self.event_payload.value or {}
        self.chat_id.value = payload.get("chat_id")
        self.user_id.value = payload.get("user_id")
        self.message_text.value = payload.get("message_text")
        self.update_obj.value = payload.get("update")
        self.command_name.value = payload.get("command_name")

        # Optionally derive `first_name` from the update if user data is in the payload
        first_name = ""
        update = payload.get("update")
        if update and update.effective_user:
            first_name = update.effective_user.first_name or ""
        self.first_name.value = first_name


@xai_component(color="green")
class TelegramReplyToMessageEvent(Component):
    """
    Sends a reply in a Telegram chat, quoting the original message from an event payload.

    ##### inPorts:
    - application (object): Telegram Application object
    - event_payload (dict): The payload containing info such as 'update', 'chat_id', etc.
    - reply_text (str): The text you want to send as a reply

    ##### outPorts:
    None

    ##### Usage (Event-Based):
    1. An event is triggered (e.g. /start command), providing a payload with 'update'.
    2. In a subgraph, wire that event payload into this component’s `event_payload`.
    3. Supply a `reply_text` literal or from another component to finalize the message.
    """
    application: InArg[object]
    event_payload: InArg[dict]
    reply_text: InArg[str]

    def execute(self, ctx) -> None:
        
        app = self.application.value
        payload = self.event_payload.value
        reply_text = self.reply_text.value

        if not app:
            print("[TelegramReplyToMessage] No Telegram Application found!")
            return
        if not payload:
            print("[TelegramReplyToMessage] No event_payload provided, can't reply.")
            return

        # Expecting the Telegram 'update' object to be in the event payload
        update = payload.get('update')
        if not update:
            print("[TelegramReplyToMessage] No 'update' in event_payload, cannot reply.")
            return

        chat_id = update.effective_chat.id
        # If you want to quote the original message, we need the message_id
        message_id = update.effective_message.message_id
        
        async def _send_reply():
            await app.bot.send_message(
                chat_id=chat_id,
                text=reply_text,
                parse_mode=ParseMode.HTML,
                reply_to_message_id=message_id  # This quotes the original
            )

        loop = asyncio.get_event_loop()
        loop.create_task(_send_reply())
