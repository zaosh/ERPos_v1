"""
Printer service — ZPL label generation and direct socket printing.
All retry logic lives in the job queue. This module only sends or raises.
"""
import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal

from config import settings

logger = logging.getLogger(__name__)


# ─── Exceptions ───────────────────────────────────────────────────────────────

class PrinterError(Exception):
    pass

class PrinterOfflineError(PrinterError):
    pass

class PrinterTimeoutError(PrinterError):
    pass


# ─── ZPL generation ───────────────────────────────────────────────────────────

def generate_zpl(item) -> str:
    """
    Build a ZPL label for the item.
    Stores: Code128 barcode, item ID, description line, price, intake date.
    """
    barcode = item.barcode
    price_str = f"${item.price:.2f}"
    color_str = (item.color or "?")[:10]
    type_str = (item.type.value if hasattr(item.type, "value") else str(item.type))[:10]
    desc = f"{color_str} {type_str}"[:20]
    date_str = datetime.now(timezone.utc).strftime("%m/%d/%y")
    item_id_str = f"#{item.id}"

    w_dots = int(settings.LABEL_WIDTH_MM * 8)   # 8 dots/mm at 203dpi
    h_dots = int(settings.LABEL_HEIGHT_MM * 8)

    return (
        "^XA\n"
        f"^PW{w_dots}\n"
        f"^LL{h_dots}\n"
        # Barcode — Code128
        "^FO10,8^BY2^BCN,50,N,N,N\n"
        f"^FD{barcode}^FS\n"
        # Barcode text (human readable)
        f"^FO10,62^A0N,14,14^FD{barcode}^FS\n"
        # Description
        f"^FO10,80^A0N,16,16^FD{desc}^FS\n"
        # Price (right-aligned)
        f"^FO{w_dots - 80},80^A0N,20,20^FD{price_str}^FS\n"
        # Item ID + date (small)
        f"^FO10,100^A0N,12,12^FD{item_id_str} | {date_str}^FS\n"
        "^XZ"
    )


# ─── Sending ──────────────────────────────────────────────────────────────────

async def send_label(item_id: int, label_data: dict) -> bool:
    """
    Send a ZPL string to the printer via TCP socket.
    Raises PrinterOfflineError, PrinterTimeoutError, or PrinterError on failure.
    Returns True on success.
    """
    zpl: str = label_data.get("zpl", "")
    if not zpl:
        raise PrinterError(f"No ZPL in label_data for item {item_id}")

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(settings.PRINTER_HOST, settings.PRINTER_PORT),
            timeout=settings.PRINTER_TIMEOUT,
        )
        try:
            writer.write(zpl.encode())
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

        logger.info(f"Label sent to printer: item_id={item_id} barcode={label_data.get('barcode', '?')}")
        return True

    except ConnectionRefusedError:
        raise PrinterOfflineError(f"Printer refused connection at {settings.PRINTER_HOST}:{settings.PRINTER_PORT}")
    except asyncio.TimeoutError:
        raise PrinterTimeoutError(f"Printer timed out after {settings.PRINTER_TIMEOUT}s")
    except OSError as e:
        raise PrinterOfflineError(f"Printer unreachable: {e}")
    except Exception as e:
        raise PrinterError(f"Printer error: {e}")
