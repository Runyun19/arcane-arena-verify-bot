# main.py — Arcane Arena Verify Bot (Panel + Modal + Confirm, Mods, Sheets)
import os, re, json, base64, discord
from discord import app_commands
from datetime import datetime

# ── ENV / IDs ────────────────────────────────────────────────────────────────
TOKEN               = os.getenv("DISCORD_TOKEN")

REGISTER_CHANNEL_ID = int(os.getenv("REGISTER_CHANNEL_ID", "0"))   # #welcome
LOG_CHANNEL_ID      = int(os.getenv("LOG_CHANNEL_ID", "0"))        # #player-id-log
VERIFIED_ROLE_ID    = int(os.getenv("VERIFIED_ROLE_ID", "0"))      # Verified role

# Moderation / permissions
MOD_ROLE_ID   = int(os.getenv("MOD_ROLE_ID", "0"))                 # optional role allowed to use commands
AUTO_REGISTER = os.getenv("AUTO_REGISTER", "false").lower() in ("1", "true", "yes")  # default false (panel kullanımını teşvik)
ID_LENGTH     = int(os.getenv("ID_LENGTH", "9"))

# Branding / jump links
GUILD_ID    = int(os.getenv("GUILD_ID", "0"))
SERVER_NAME = os.getenv("SERVER_NAME", "Arcane Arena")
BRAND       = os.getenv("BRAND", "Arcane Arena")

# Welcome panel text (opsiyonel özelleştirme)
WELCOME_TITLE = os.getenv("WELCOME_TITLE", "Welcome to Arcane Arena!")
WELCOME_DESC  = os.getenv(
    "WELCOME_DESC",
    "Arcane Arena — the most competitive tower defense experience.\n\n"
    "To unlock the server, click **Verify** and enter your **Player ID** "
    "(exactly {n} digits). Example: `123456789`.\n\n"
    "Your message will be private. If your DMs are closed, you may miss the confirmation."
).format(n=ID_LENGTH)

# Button & modal labels (ops.)
VERIFY_BUTTON_LABEL  = os.getenv("VERIFY_BUTTON_LABEL", "Verify")
MODAL_TITLE          = os.getenv("MODAL_TITLE", "Enter your Player ID")
MODAL_FIELD_LABEL    = os.getenv("MODAL_FIELD_LABEL", f"Player ID (exactly {ID_LENGTH} digits)")
CONFIRM_LABEL        = os.getenv("CONFIRM_LABEL", "Confirm")
CANCEL_LABEL         = os.getenv("CANCEL_LABEL", "Cancel")

# Google Sheets (raw JSON or base64)
SHEET_ID               = os.getenv("SHEET_ID", "")
WORKSHEET              = os.getenv("WORKSHEET", "Registrations")
GOOGLE_CREDENTIALS     = os.getenv("GOOGLE_CREDENTIALS", "")
GOOGLE_CREDENTIALS_B64 = os.getenv("GOOGLE_CREDENTIALS_B64", "")

# Community managers contact (already-verified yönlendirme)
CM_ROLE_ID      = int(os.getenv("CM_ROLE_ID", "0"))
SUPPORT_USER_ID = os.getenv("SUPPORT_USER_ID", "0")

# ── VALIDATION ───────────────────────────────────────────────────────────────
ONLY_ASCII_DIGITS   = re.compile(r"^\d+$")
EXACT_ASCII_DIGITS  = re.compile(rf"^\d{{{ID_LENGTH}}}$")  # exactly ID_LENGTH ASCII digits

# ── TEXTS (EN) ───────────────────────────────────────────────────────────────
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
    "{mention} You sent **{typed} digits** — you need **exactly {need}**."
)
MSG_TOO_LONG = (
    "{mention} You sent **{typed} digits** — that’s **more than {need}**."
)
MSG_NON_DIGIT = (
    "{mention} Only numbers are allowed. Please enter digits only."
)
MSG_ALREADY_VERIFIED = (
    "{mention} You are **already verified**. Updates are disabled. "
    "Please DM {cm} to request a change."
)
DM_OK    = "✅ Player ID saved and your access has been granted. Enjoy!"
DM_BLOCK = f"Hi! I can’t process DMs. Please click **Verify** in {REGISTER_JUMP} on **{SERVER_NAME}**."

COLOR_OK   = 0x57F287
COLOR_WARN = 0xFEE75C
COLOR_ERR  = 0xED4245

# ── Discord client & commands ────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

allowed_mentions_users_only = discord.AllowedMentions(everyone=False, roles=False, users=True)

def is_mod(member: discord.Member) -> bool:
    if member.guild_permissions.administrator or member.guild_permissions.manage_roles:
        return True
    if MOD_ROLE_ID and discord.utils.get(member.roles, id=MOD_ROLE_ID):
        return True
    return False

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
            ws = sh.add_worksheet(title=WORKSHEET, rows="1000", cols="12")
        print("✅ Google Sheets connected.")
    except Exception as e:
        print("⚠️ Sheets disabled:", e)

def sheet_append_row(guild: discord.Guild, user: discord.abc.User, player_id: str, source: str):
    if not ws:
        return
    try:
        ts = datetime.utcnow().isoformat()
        display = getattr(user, "global_name", None) or getattr(user, "display_name", None) or user.name
        ws.append_row(
            [
                ts,
                str(guild.id), guild.name,
                str(user.id), display,
                player_id,
                source,  # "panel" | "auto" | "manual"
            ],
            value_input_option="RAW",
        )
    except Exception as e:
        print("⚠️ sheet append failed:", e)

async def apply_success(guild: discord.Guild, member: discord.Member, player_id: str, source: str):
    log_ch = guild.get_channel(LOG_CHANNEL_ID)
    if log_ch:
        await log_ch.send(
            f"{member.mention} player id `{player_id}` · source **{source}**",
            allowed_mentions=allowed_mentions_users_only
        )
    vrole = guild.get_role(VERIFIED_ROLE_ID)
    if vrole and vrole not in member.roles:
        try:
            await member.add_roles(vrole, reason="Player ID verified")
        except Exception as e:
            if log_ch:
                await log_ch.send(
                    f"⚠️ Could not assign role to {member.mention}: `{e}`",
                    allowed_mentions=allowed_mentions_users_only
                )
    sheet_append_row(guild, member, player_id, source)
    try:
        emb = discord.Embed(description=DM_OK, color=COLOR_OK)
        emb.set_author(name=f"{BRAND} Verify")
        emb.add_field(name="Player ID", value=f"`{player_id}`", inline=True)
        await member.send(embed=emb)
    except:
        pass

# ── Panel (View + Button) & Modal & Confirm View ────────────────────────────
class VerifyPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label=(VERIFY_BUTTON_LABEL or "Verify"),
        style=discord.ButtonStyle.success,
        custom_id="verify:start"
    )
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        
        member = interaction.user
        # already verified?
        vrole = interaction.guild.get_role(VERIFIED_ROLE_ID)
        if vrole and vrole in member.roles:
            return await interaction.response.send_message(
                MSG_ALREADY_VERIFIED.format(mention=member.mention, cm=cm_contact()),
                ephemeral=True
            )
        await interaction.response.send_modal(VerifyModal())

class VerifyModal(discord.ui.Modal, title=MODAL_TITLE):
    player_id_input: discord.ui.TextInput = discord.ui.TextInput(
        label=MODAL_FIELD_LABEL,
        placeholder="e.g. 123456789",
        style=discord.TextStyle.short,
        required=True,
        max_length=32,
    )

    async def on_submit(self, interaction: discord.Interaction):
        raw = str(self.player_id_input.value).strip()
        digits = "".join(ch for ch in raw if ch.isascii() and ch.isdigit())
        typed = len(digits)

        # validation messages
        if typed == 0:
            return await interaction.response.send_message(
                MSG_NON_DIGIT.format(mention=interaction.user.mention), ephemeral=True
            )
        if typed < ID_LENGTH:
            return await interaction.response.send_message(
                MSG_TOO_SHORT.format(mention=interaction.user.mention, typed=typed, need=ID_LENGTH), ephemeral=True
            )
        if typed > ID_LENGTH:
            return await interaction.response.send_message(
                MSG_TOO_LONG.format(mention=interaction.user.mention, typed=typed, need=ID_LENGTH), ephemeral=True
            )
        if not EXACT_ASCII_DIGITS.fullmatch(digits):
            return await interaction.response.send_message(
                MSG_NON_DIGIT.format(mention=interaction.user.mention), ephemeral=True
            )

        # show confirm view (ephemeral)
        view = ConfirmView(player_id=digits)
        emb = discord.Embed(
            title="Confirm your Player ID",
            description=f"**{digits}**\n\nClick **{CONFIRM_LABEL}** to finish, or **{CANCEL_LABEL}** to abort.",
            color=COLOR_WARN
        )
        await interaction.response.send_message(embed=emb, view=view, ephemeral=True)

class ConfirmView(discord.ui.View):
    def __init__(self, player_id: str):
        super().__init__(timeout=60)
        self.player_id = player_id

    @discord.ui.button(label=CONFIRM_LABEL, style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        guild  = interaction.guild
        # already verified?
        vrole = guild.get_role(VERIFIED_ROLE_ID)
        if vrole and vrole in member.roles:
            return await interaction.response.edit_message(
                content=MSG_ALREADY_VERIFIED.format(mention=member.mention, cm=cm_contact()),
                embed=None, view=None
            )
        await apply_success(guild, member, self.player_id, source="panel")
        await interaction.response.edit_message(content="✅ Verified!", embed=None, view=None)

    @discord.ui.button(label=CANCEL_LABEL, style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❎ Cancelled.", embed=None, view=None)

# ── Events ───────────────────────────────────────────────────────────────────
@client.event
async def on_ready():
    # persistent button
    client.add_view(VerifyPanelView())
    await tree.sync()
    print(f"✅ Login successful: {client.user} (ID_LENGTH={ID_LENGTH}, AUTO_REGISTER={AUTO_REGISTER})")

@client.event
async def on_message(message: discord.Message):
    # 1) Block DMs; redirect users
    if not message.guild and not message.author.bot:
        try:
            await message.channel.send(DM_BLOCK)
        except:
            pass
        return

    # 2) Optional: legacy auto-register flow (by message) if enabled
    if not AUTO_REGISTER:
        return
    if message.author.bot or message.channel.id != REGISTER_CHANNEL_ID:
        return

    try:  # privacy: delete user message
        await message.delete()
    except:
        pass

    guild = message.guild
    member = message.author
    vrole = guild.get_role(VERIFIED_ROLE_ID)

    if vrole and vrole in member.roles:
        await send_temp(message.channel, MSG_ALREADY_VERIFIED.format(
            mention=member.mention, cm=cm_contact()
        ))
        log_ch = guild.get_channel(LOG_CHANNEL_ID)
        if log_ch:
            await log_ch.send(
                f"⛔ Update attempt blocked for {member.mention}. Typed `{message.content.strip()}`",
                allowed_mentions=allowed_mentions_users_only
            )
        return

    digits = "".join(ch for ch in message.content if ch.isascii() and ch.isdigit())
    typed = len(digits)
    if typed == 0:
        return await send_temp(message.channel, MSG_NON_DIGIT.format(mention=member.mention))
    if typed < ID_LENGTH:
        return await send_temp(message.channel, MSG_TOO_SHORT.format(mention=member.mention, typed=typed, need=ID_LENGTH))
    if typed > ID_LENGTH:
        return await send_temp(message.channel, MSG_TOO_LONG.format(mention=member.mention, typed=typed, need=ID_LENGTH))
    if not EXACT_ASCII_DIGITS.fullmatch(digits):
        return await send_temp(message.channel, MSG_NON_DIGIT.format(mention=member.mention))

    await apply_success(guild, member, digits, source="auto")

# ── Slash Commands (mod-only) ────────────────────────────────────────────────
@tree.command(name="setup_panel", description="Post the Verify panel (mods only).")
async def setup_panel_cmd(interaction: discord.Interaction, channel: discord.TextChannel = None):
    if not is_mod(interaction.user):
        return await interaction.response.send_message("You don’t have permission.", ephemeral=True)
    target = channel or interaction.channel
    emb = discord.Embed(title=WELCOME_TITLE, description=WELCOME_DESC, color=COLOR_WARN)
    emb.set_author(name=f"{BRAND} Verify")
    try:
        await target.send(embed=emb, view=VerifyPanelView())
        await interaction.response.send_message("Panel posted.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Failed: `{e}`", ephemeral=True)

@tree.command(name="verify", description="Manually verify a user with a Player ID (mods only).")
async def verify_cmd(interaction: discord.Interaction, user: discord.Member, player_id: str):
    if not is_mod(interaction.user):
        return await interaction.response.send_message("You don’t have permission.", ephemeral=True)
    digits = "".join(ch for ch in player_id if ch.isascii() and ch.isdigit())
    if not digits or not ONLY_ASCII_DIGITS.fullmatch(digits):
        return await interaction.response.send_message(
            f"Only digits are allowed. Example: `{'9'*ID_LENGTH}`", ephemeral=True
        )
    if len(digits) != ID_LENGTH:
        return await interaction.response.send_message(
            f"ID must be exactly **{ID_LENGTH}** digits. You sent **{len(digits)}**.", ephemeral=True
        )
    vrole = interaction.guild.get_role(VERIFIED_ROLE_ID)
    if vrole and vrole in user.roles:
        return await interaction.response.send_message(f"{user.mention} is already verified.", ephemeral=True)
    await apply_success(interaction.guild, user, digits, source="manual")
    await interaction.response.send_message(f"✅ Verified {user.mention} with ID `{digits}`.", ephemeral=True)

@tree.command(name="unverify", description="Remove the Verified role (mods only).")
async def unverify_cmd(interaction: discord.Interaction, user: discord.Member):
    if not is_mod(interaction.user):
        return await interaction.response.send_message("You don’t have permission.", ephemeral=True)
    vrole = interaction.guild.get_role(VERIFIED_ROLE_ID)
    if not vrole or vrole not in user.roles:
        return await interaction.response.send_message(f"{user.mention} is not verified.", ephemeral=True)
    try:
        await user.remove_roles(vrole, reason="Manual unverify")
    except Exception as e:
        return await interaction.response.send_message(f"Failed: `{e}`", ephemeral=True)
    log_ch = interaction.guild.get_channel(LOG_CHANNEL_ID)
    if log_ch:
        await log_ch.send(f"🗑️ Unverified {user.mention}.", allowed_mentions=allowed_mentions_users_only)
    await interaction.response.send_message(f"Done. Removed Verified from {user.mention}.", ephemeral=True)

client.run(TOKEN)
