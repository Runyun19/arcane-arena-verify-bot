# main.py — Arcane Arena Verify Bot
import os, re, json, base64, discord
from datetime import datetime

# ── ENV / IDs ────────────────────────────────────────────────────────────────
TOKEN               = os.getenv("DISCORD_TOKEN")
REGISTER_CHANNEL_ID = int(os.getenv("REGISTER_CHANNEL_ID", "0"))   # #welcome
LOG_CHANNEL_ID      = int(os.getenv("LOG_CHANNEL_ID", "0"))        # #player-id-log
VERIFIED_ROLE_ID    = int(os.getenv("VERIFIED_ROLE_ID", "0"))      # Verified role

# (optional) Community Managers contact
CM_ROLE_ID       = int(os.getenv("CM_ROLE_ID", "0"))               # @Community Managers role id
SUPPORT_USER_ID  = os.getenv("SUPPORT_USER_ID", "0")               # single user id (string)

# For clickable jump link in DMs
GUILD_ID    = int(os.getenv("GUILD_ID", "0"))
SERVER_NAME = os.getenv("SERVER_NAME", "Arcane Arena")

# Google Sheets (use either GOOGLE_CREDENTIALS or GOOGLE_CREDENTIALS_B64)
SHEET_ID              = os.getenv("SHEET_ID", "")
WORKSHEET             = os.getenv("WORKSHEET", "Registrations")
GOOGLE_CREDENTIALS    = os.getenv("GOOGLE_CREDENTIALS", "")
GOOGLE_CREDENTIALS_B64= os.getenv("GOOGLE_CREDENTIALS_B64", "")

# ── VALIDATION ───────────────────────────────────────────────────────────────
EXACT_DIGITS = 9
ONLY_9_ASCII_DIGITS = re.compile(r"^\d{9}$")  # exactly 9 ASCII digits

# ── TEXTS (EN) ───────────────────────────────────────────────────────────────
BRAND = "Arcane Arena"
CHANNEL_MENTION_TEXT = f"<#{REGISTER_CHANNEL_ID}>"
REGISTER_JUMP = (
    f"https://discord.com/channels/{GUILD_ID}/{REGISTER_CHANNEL_ID}" if GUILD_ID else "#welcome"
)

def cm_contact():
    if SUPPORT_USER_ID and SUPPORT_USER_ID.isdigit() and SUPPORT_USER_ID != "0":
        return f"<@{SUPPORT_USER_ID}>"
    if CM_ROLE_ID:
        return f"<@&{CM_ROLE_ID}>"
    return "the Community Managers"

MSG_TOO_SHORT = (
    "{mention} You sent **{typed} digits** — you need **exactly {need}**. "
    "Please send digits only in {ch}. Example: `123456789`"
)
MSG_TOO_LONG = (
    "{mention} You sent **{typed} digits** — that’s **more than {need}**. "
    "Please send exactly {need} digits in {ch}."
)
MSG_NON_DIGIT = (
    "{mention} Only numbers are allowed. Please send **just your Player ID** in {ch}. "
    "Example: `123456789`"
)
MSG_ALREADY_VERIFIED = (
    "{mention} You are **already verified**. Updates are disabled. "
    "Please DM {cm} to request a change."
)
DM_OK    = "✅ Player ID saved and your access has been granted. Enjoy!"
DM_BLOCK = f"Hi! I can’t process DMs. Please post your Player ID in the registration channel on **{SERVER_NAME}**: {REGISTER_JUMP}"

COLOR_OK = 0x57F287

# ── Discord client ───────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = discord.Client(intents=intents)

allowed_mentions_users_only = discord.AllowedMentions(everyone=False, roles=False, users=True)

async def send_temp(ch: discord.TextChannel, text: str):
    try:
        return await ch.send(text, delete_after=10, allowed_mentions=allowed_mentions_users_only)
    except:
        return None

# ── Google Sheets init ───────────────────────────────────────────────────────
ws = None
if SHEET_ID and (GOOGLE_CREDENTIALS or GOOGLE_CREDENTIALS_B64):
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        if GOOGLE_CREDENTIALS_B64 and not GOOGLE_CREDENTIALS:
            GOOGLE_CREDENTIALS = base64.b64decode(GOOGLE_CREDENTIALS_B64).decode("utf-8")

        info = json.loads(GOOGLE_CREDENTIALS)
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SHEET_ID)
        try:
            ws = sh.worksheet(WORKSHEET)
        except Exception:
            ws = sh.add_worksheet(title=WORKSHEET, rows="1000", cols="10")
        print("✅ Google Sheets connected.")
    except Exception as e:
        print("⚠️ Sheets disabled:", e)

def sheet_append_row(guild: discord.Guild, user: discord.User | discord.Member, player_id: str):
    if not ws:
        return
    try:
        ts = datetime.utcnow().isoformat()
        display = getattr(user, "global_name", None) or user.display_name or user.name
        ws.append_row(
            [
                ts,
                str(guild.id), guild.name,
                str(user.id), display,
                player_id,
            ],
            value_input_option="RAW",
        )
    except Exception as e:
        print("⚠️ sheet append failed:", e)

# ── Events ───────────────────────────────────────────────────────────────────
@client.event
async def on_ready():
    print(f"✅ Login successful: {client.user} (EXACT_DIGITS={EXACT_DIGITS})")

@client.event
async def on_message(message: discord.Message):
    # 1) Block DMs and redirect to #welcome
    if not message.guild and not message.author.bot:
        try:
            await message.channel.send(DM_BLOCK)
        except:
            pass
        return

    # 2) Ignore everything except #welcome
    if message.author.bot or message.channel.id != REGISTER_CHANNEL_ID:
        return

    content = message.content.strip()

    # Delete user message for privacy
    try:
        await message.delete()
    except:
        pass

    guild = message.guild
    verified_role = guild.get_role(VERIFIED_ROLE_ID)
    log_ch = guild.get_channel(LOG_CHANNEL_ID)

    # 3) One-time registration rule
    if verified_role and verified_role in message.author.roles:
        await send_temp(message.channel, MSG_ALREADY_VERIFIED.format(
            mention=message.author.mention, cm=cm_contact()
        ))
        if log_ch:
            await log_ch.send(
                f"⛔ Update attempt blocked for {message.author.mention}. Typed `{content}`",
                allowed_mentions=allowed_mentions_users_only
            )
        return

    # 4) Count only digits (ignore other characters)
    digits_only = "".join(ch for ch in content if ch.isascii() and ch.isdigit())
    typed = len(digits_only)

    if typed == 0:
        await send_temp(message.channel, MSG_NON_DIGIT.format(
            mention=message.author.mention, ch=CHANNEL_MENTION_TEXT
        ))
        return
    if typed < EXACT_DIGITS:
        await send_temp(message.channel, MSG_TOO_SHORT.format(
            mention=message.author.mention, typed=typed, need=EXACT_DIGITS, ch=CHANNEL_MENTION_TEXT
        ))
        return
    if typed > EXACT_DIGITS:
        await send_temp(message.channel, MSG_TOO_LONG.format(
            mention=message.author.mention, typed=typed, need=EXACT_DIGITS, ch=CHANNEL_MENTION_TEXT
        ))
        return

    # Safety: ensure exactly 9 ASCII digits (no invisible chars)
    if not ONLY_9_ASCII_DIGITS.fullmatch(digits_only):
        await send_temp(message.channel, MSG_NON_DIGIT.format(
            mention=message.author.mention, ch=CHANNEL_MENTION_TEXT
        ))
        return

    player_id = digits_only

    # 5) Log (@mention guaranteed)
    if log_ch:
        await log_ch.send(
            f"{message.author.mention} player id `{player_id}`",
            allowed_mentions=allowed_mentions_users_only
        )

    # 6) Assign role
    try:
        if verified_role:
            await message.author.add_roles(verified_role, reason="Player ID verified")
    except Exception as e:
        if log_ch:
            await log_ch.send(
                f"⚠️ Could not assign role to {message.author.mention}: `{e}`",
                allowed_mentions=allowed_mentions_users_only
            )

    # 7) Write to Google Sheets
    sheet_append_row(guild, message.author, player_id)

    # 8) DM confirmation
    try:
        emb_ok = discord.Embed(description=DM_OK, color=COLOR_OK)
        emb_ok.set_author(name=f"{BRAND} Verify")
        emb_ok.add_field(name="Player ID", value=f"`{player_id}`", inline=True)
        await message.author.send(embed=emb_ok)
    except:
        await send_temp(message.channel, f"{message.author.mention} Verified. Welcome!")

client.run(TOKEN)
