"""
Shadow Ads Bot - Intelligent Telegram Channel & Group Join Helper
================================================================
Handles both Public usernames (@group, t.me/group) and Private
invite links (t.me/+hash, t.me/joinchat/hash).
Includes robust exception handling (UserAlreadyParticipantError,
InviteRequestSentError, FloodWaitError, ChannelsTooMuchError).
"""
import logging
from typing import Tuple, Dict, Any
from telethon import TelegramClient
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors import (
    UserAlreadyParticipantError,
    InviteRequestSentError,
    InviteHashExpiredError,
    InviteHashInvalidError,
    FloodWaitError,
    ChannelsTooMuchError,
    ChannelPrivateError,
)

logger = logging.getLogger(__name__)


def parse_telegram_link(raw_link: str) -> Dict[str, Any]:
    """
    Parses a Telegram link into target info:
    - type: 'private' | 'public'
    - target: invite hash or clean username
    - original: original input
    """
    link = raw_link.strip()
    
    # Check for private invite links
    if "join?invite=" in link:
        h = link.split("join?invite=")[-1].split("&")[0].strip()
        return {"type": "private", "target": h, "original": link}
        
    if "+" in link:
        h = link.split("+")[-1].split("/")[0].split("?")[0].strip()
        return {"type": "private", "target": h, "original": link}
        
    if "joinchat/" in link:
        h = link.split("joinchat/")[-1].split("/")[0].split("?")[0].strip()
        return {"type": "private", "target": h, "original": link}
        
    # Public link: @username or https://t.me/username
    clean = (
        link.replace("https://t.me/", "")
        .replace("http://t.me/", "")
        .replace("t.me/", "")
        .replace("@", "")
        .strip()
    )
    clean = clean.split("/")[0].split("?")[0].strip()
    return {"type": "public", "target": clean, "original": link}


async def join_telegram_target(client: TelegramClient, raw_link: str) -> Tuple[bool, str]:
    """
    Attempts to join a Telegram channel or group using the provided client.
    Handles both public channels/groups and private invite links seamlessly.
    
    Returns:
        (success: bool, status_note: str)
    """
    info = parse_telegram_link(raw_link)
    target = info["target"]
    
    if not target:
        return False, "Invalid or empty link"
        
    if info["type"] == "private":
        try:
            await client(ImportChatInviteRequest(hash=target))
            return True, "Joined private link successfully"
        except UserAlreadyParticipantError:
            return True, "Already a participant"
        except InviteRequestSentError:
            return True, "Join request sent (admin approval pending)"
        except (InviteHashExpiredError, InviteHashInvalidError):
            return False, "Invite link is expired or invalid"
        except FloodWaitError as e:
            return False, f"FloodWait ({e.seconds}s)"
        except ChannelsTooMuchError:
            return False, "Account channel limit reached"
        except Exception as e:
            err_str = str(e)
            logger.warning(f"Private join error for {target}: {err_str}")
            return False, f"Failed: {err_str[:40]}"
            
    else:
        # Public target
        try:
            await client(JoinChannelRequest(channel=target))
            return True, "Joined public group successfully"
        except UserAlreadyParticipantError:
            return True, "Already a participant"
        except FloodWaitError as e:
            return False, f"FloodWait ({e.seconds}s)"
        except ChannelsTooMuchError:
            return False, "Account channel limit reached"
        except ChannelPrivateError:
            return False, "Chat is private or inaccessible"
        except Exception as e:
            # Fallback to get_entity
            try:
                entity = await client.get_entity(target)
                await client(JoinChannelRequest(channel=entity))
                return True, "Joined public group successfully"
            except UserAlreadyParticipantError:
                return True, "Already a participant"
            except Exception as ex:
                err_str = str(ex)
                logger.warning(f"Public join error for {target}: {err_str}")
                return False, f"Failed: {err_str[:40]}"
