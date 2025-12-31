"""
Verification System for NQ GOD Terminal
Requires users to verify Discord membership and YouTube subscription
"""

from __future__ import annotations

import os
import secrets
import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional
from dataclasses import dataclass, field
import requests


# Configuration from environment
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID", "")  # Your Discord server ID
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:8000/api/verify/discord/callback")

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
YOUTUBE_CHANNEL_ID = os.getenv("YOUTUBE_CHANNEL_ID", "")  # Your YouTube channel ID

# Verification storage (in production, use a database)
verified_users: Dict[str, Dict[str, Any]] = {}
pending_verifications: Dict[str, Dict[str, Any]] = {}


@dataclass
class VerificationSession:
    """Tracks a user's verification status"""
    session_id: str
    discord_verified: bool = False
    youtube_verified: bool = False
    discord_user_id: Optional[str] = None
    discord_username: Optional[str] = None
    youtube_channel_name: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    verified_at: Optional[datetime] = None
    
    def is_fully_verified(self) -> bool:
        return self.discord_verified and self.youtube_verified
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "discord_verified": self.discord_verified,
            "youtube_verified": self.youtube_verified,
            "discord_username": self.discord_username,
            "youtube_channel_name": self.youtube_channel_name,
            "is_verified": self.is_fully_verified(),
            "created_at": self.created_at.isoformat(),
            "verified_at": self.verified_at.isoformat() if self.verified_at else None
        }


def generate_session_id() -> str:
    """Generate a unique session ID"""
    return secrets.token_urlsafe(32)


def get_or_create_session(session_id: Optional[str] = None) -> VerificationSession:
    """Get existing session or create a new one"""
    if session_id and session_id in verified_users:
        data = verified_users[session_id]
        return VerificationSession(
            session_id=session_id,
            discord_verified=data.get("discord_verified", False),
            youtube_verified=data.get("youtube_verified", False),
            discord_user_id=data.get("discord_user_id"),
            discord_username=data.get("discord_username"),
            youtube_channel_name=data.get("youtube_channel_name"),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.now(timezone.utc),
            verified_at=datetime.fromisoformat(data["verified_at"]) if data.get("verified_at") else None
        )
    
    new_session = VerificationSession(session_id=generate_session_id())
    return new_session


def save_session(session: VerificationSession) -> None:
    """Save session to storage"""
    verified_users[session.session_id] = session.to_dict()
    
    # Also save to file for persistence
    try:
        with open("data/verified_users.json", "w") as f:
            json.dump(verified_users, f, indent=2)
    except Exception:
        pass  # In-memory only if file fails


def load_verified_users() -> None:
    """Load verified users from file"""
    global verified_users
    try:
        with open("data/verified_users.json", "r") as f:
            verified_users = json.load(f)
    except FileNotFoundError:
        verified_users = {}
    except Exception:
        verified_users = {}


# Discord OAuth2 Functions
def get_discord_oauth_url(state: str) -> str:
    """Generate Discord OAuth2 URL"""
    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify guilds",
        "state": state
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"https://discord.com/api/oauth2/authorize?{query}"


def exchange_discord_code(code: str) -> Optional[Dict[str, Any]]:
    """Exchange OAuth code for access token"""
    data = {
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": DISCORD_REDIRECT_URI
    }
    
    try:
        resp = requests.post("https://discord.com/api/oauth2/token", data=data, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"[Verify] Discord token exchange error: {e}")
    return None


def get_discord_user(access_token: str) -> Optional[Dict[str, Any]]:
    """Get Discord user info"""
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        resp = requests.get("https://discord.com/api/users/@me", headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def get_discord_guilds(access_token: str) -> list:
    """Get user's Discord guilds"""
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        resp = requests.get("https://discord.com/api/users/@me/guilds", headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return []


def check_user_in_guild(access_token: str, guild_id: str) -> bool:
    """Check if user is a member of the specified guild"""
    guilds = get_discord_guilds(access_token)
    return any(g.get("id") == guild_id for g in guilds)


def check_guild_membership_via_bot(user_id: str, guild_id: str) -> bool:
    """Check guild membership using bot token (more reliable)"""
    if not DISCORD_BOT_TOKEN or not guild_id:
        return False
    
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}
    try:
        resp = requests.get(
            f"https://discord.com/api/guilds/{guild_id}/members/{user_id}",
            headers=headers,
            timeout=10
        )
        return resp.status_code == 200
    except Exception:
        pass
    return False


# YouTube Verification Functions
def check_youtube_subscription(channel_id: str, user_channel_id: str) -> bool:
    """
    Check if user is subscribed to your channel.
    Note: This requires the user to have public subscriptions OR
    use YouTube OAuth to check their subscriptions directly.
    
    For simplicity, we'll use a verification code system.
    """
    # YouTube API doesn't easily allow checking if someone is subscribed
    # without their OAuth consent. We'll use an alternative approach.
    return True  # Placeholder - see manual verification


def get_youtube_channel_info(channel_id: str) -> Optional[Dict[str, Any]]:
    """Get YouTube channel info"""
    if not YOUTUBE_API_KEY:
        return None
    
    try:
        url = f"https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&id={channel_id}&key={YOUTUBE_API_KEY}"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("items"):
                return data["items"][0]
    except Exception:
        pass
    return None


def generate_verification_code(session_id: str) -> str:
    """Generate a unique verification code for manual YouTube verification"""
    code = f"NQGOD-{secrets.token_hex(4).upper()}"
    pending_verifications[code] = {
        "session_id": session_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "type": "youtube"
    }
    return code


def verify_youtube_code(code: str, session_id: str) -> bool:
    """Verify YouTube subscription using code (for manual flow)"""
    if code in pending_verifications:
        pending = pending_verifications[code]
        if pending.get("session_id") == session_id:
            del pending_verifications[code]
            return True
    return False


# Initialize on module load
load_verified_users()
