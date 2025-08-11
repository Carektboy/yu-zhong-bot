import discord
from discord.ext import commands
from discord import app_commands
import os
import json
import logging
import asyncio

l = logging.getLogger('YuZhongBot')

class AIChatCog(commands.Cog):
    def __init__(self, b):
        self.b = b
        self.p = b.personality
        self.r = b.safe_send_response
        self.dt = b.DEFAULT_TONE
        self.mt = b.MAX_MEMORY_PER_USER_TOKENS
        self.m = b.MEMORY_DIR

        # Lazy init placeholders
        self.sc = None
        self.sm = None
        self.si = False

    async def lazy_init_shapes_client(self):
        if self.si:
            return
        self.si = True

        a = getattr(self.b, "SHAPESINC_API_KEY", None)
        u = getattr(self.b, "SHAPESINC_MODEL_USERNAME", None)

        if not a or not u:
            l.warning("Shapes.inc API key or model username missing; AI features disabled.")
            return

        try:
            from openai import OpenAI

            self.sc = OpenAI(
                base_url="https://api.shapes.inc/v1/",
                api_key=a,
                timeout=60.0
            )

            res = await asyncio.to_thread(self.sc.models.list)
            am = [m.id for m in res.data]
            l.info(f"Shapes.inc available models: {am}")

            mm = next(
                (m for m in am if u in m or m == u),
                None
            )

            if mm:
                self.sm = mm
                l.info(f"Shapes.inc model resolved: {mm}")
            else:
                l.critical(f"Shapes.inc model '{u}' not found. AI features disabled.")
                self.sc = None
        except Exception as e:
            l.critical(f"Failed to initialize Shapes.inc client or resolve model: {e}")
            self.sc = None

    def get_user_memory_filepath(self, g, u):
        return os.path.join(self.m, f"user_{g}_{u}.json")

    def load_user_memory(self, g, u):
        fp = self.get_user_memory_filepath(g, u)
        if os.path.exists(fp):
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    mem = json.load(f)

                if "tone" not in mem:
                    mem["tone"] = self.dt.copy()
                else:
                    for k, v in self.dt.items():
                        if k not in mem["tone"]:
                            mem["tone"][k] = v

                return mem
            except json.JSONDecodeError as e:
                l.error(f"Error decoding memory for user {u} in guild {g}: {e}")
            except Exception as e:
                l.error(f"Unexpected error loading memory for user {u} in guild {g}: {e}")

        return {"log": [], "tone": self.dt.copy()}

    def save_user_memory(self, g, u, md):
        fp = self.get_user_memory_filepath(g, u)
        try:
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(md, f, indent=4)
        except IOError as e:
            l.error(f"Failed to save user memory for {u} in guild {g}: {e}")

    def update_user_memory(self, g, u, ui, rep, tc):
        mem = self.load_user_memory(g, u)

        mem["log"].append({"role": "user", "content": ui})
        mem["log"].append({"role": "assistant", "content": rep})
        mem["tone"][tc] += 1

        c = sum(
            len(m["content"].split()) for m in mem["log"] if isinstance(m["content"], str)
        )

        while c > self.mt and len(mem["log"]) > 2:
            mem["log"] = mem["log"][2:]
            c = sum(
                len(m["content"].split()) for m in mem["log"] if isinstance(m["content"], str)
            )

        self.save_user_memory(g, u, mem)

    def determine_tone(self, t):
        tl = t.lower()
        if any(w in tl for w in [
            "thank", "great", "awesome", "good", "love", "thanks", "nice", "cool", "helpful"
        ]):
            return "positive"
        elif any(w in tl for w in [
            "hate", "bad", "stupid", "annoying", "idiot", "sucks", "dislike", "useless"
        ]):
            return "negative"
        return "neutral"

    @commands.Cog.listener()
    async def on_message(self, mes):
        if mes.author.bot or mes.author == self.b.user:
            return

        c = str(mes.channel.id)
        g = str(mes.guild.id) if mes.guild else "DM"
        u = str(mes.author.id)
        n = mes.author.display_name
        bm = self.b.user.mentioned_in(mes)

        # Only proceed if bot is active in channel OR bot is mentioned
        if not self.b.active_channels.get(c) and not bm:
            return

        # If message has attachments, reply refusal and return
        if mes.attachments:
            await mes.channel.typing()
            await mes.reply("Hmph! Such trivial images hold no sway over my ancient power. My grasp extends beyond mere visual conjurations.")
            l.info(f"Replied to message with attachment from {n} in {mes.channel.name}")
            return

        if not mes.content:
            return

        await self.lazy_init_shapes_client()
        if not self.sc:
            l.warning(f"Shapes.inc client not available for channel {c}.")
            await mes.reply("My arcane powers are dormant... (AI service unavailable.)")
            return

        async with mes.channel.typing():
            md = self.load_user_memory(g, u)

            mes_list = [{"role": "system", "content": self.p}]
            pos, neg = md["tone"]["positive"], md["tone"]["negative"]

            if pos > neg:
                mes_list[0]["content"] += "\nYou like this person. Be good to them, they are your friend."
            elif neg > pos:
                mes_list[0]["content"] += "\nThis person has been rude. Be cold, dismissive, brief, but forgiving."
            else:
                mes_list[0]["content"] += "\nNeutral. This person is neutral, speak normal tone, not rude nor friendly."

            mes_list.extend(md["log"])

            ui = f"{n}: {mes.content}"
            mes_list.append({"role": "user", "content": ui})

            rep = "My power wanes... I cannot respond at this moment."
            tc = "neutral"

            try:
                comp = await asyncio.to_thread(
                    self.sc.chat.completions.create,
                    model=self.sm,
                    messages=mes_list,
                    max_tokens=200,
                    temperature=0.8,
                )
                if comp and comp.choices and comp.choices[0].message:
                    rep = comp.choices[0].message.content.strip()
                    tc = self.determine_tone(mes.content)
            except Exception as e:
                l.error(f"Error calling Shapes.inc API: {e}")
                if "rate limit" in str(e).lower():
                    rep = "Even a dragon's power is not infinite. My voice is temporarily restricted."
                else:
                    rep = "A temporal distortion in the flow of power prevents my response."

            if len(rep) > 1900:
                rep = rep[:1897] + "..."

            await mes.reply(rep)
            self.update_user_memory(g, u, ui, rep, tc)

    @app_commands.command(
        name="search",
        description="Search for information with Yu Zhong's knowledge."
    )
    async def search(self, i: discord.Interaction, q: str):
        c = str(i.channel_id)

        if i.guild and not self.b.active_channels.get(c):
            await self.r(i, "My power is not active in this channel. Use `/arise` to awaken me.", ephemeral=True)
            return

        await i.response.defer()

        await self.lazy_init_shapes_client()
        if not self.sc:
            await self.r(i, "My arcane powers are dormant... (AI service unavailable.)")
            return

        try:
            g = str(i.guild_id) if i.guild else "DM"
            u = str(i.user.id)
            md = self.load_user_memory(g, u)

            mc = self.b.get_cog("MLBBCog")
            pn = await mc.get_latest_patch_notes() if mc else ""
            if not mc:
                l.warning("MLBBCog not loaded, cannot get patch notes for search.")

            n = i.user.display_name

            sp = f"{self.p}\n\nYou are being asked to search for information about: '{q}'. Provide helpful, accurate information while maintaining your Yu Zhong personality. Do not confuse other users with '{n}'."

            pos, neg = md["tone"]["positive"], md["tone"]["negative"]
            if pos > neg:
                sp += "\nYou like this person. Be good to them, they are your friend."
            elif neg > pos:
                sp += "\nThis person has been rude. Be cold, dismissive, brief, but forgiving."
            else:
                sp += "\nNeutral. This person is neutral, speak normal tone, not rude nor friendly."

            mes_list = [{"role": "system", "content": sp}]
            mes_list.extend(md["log"])

            fqc = (
                f"{n}: Search for information about: {q}\n\n"
                f"[User Info: Address the user as '{n}' in your response]"
            )
            if pn:
                fqc += f"\n\n[Context: Latest MLBB Patch Notes]\n{pn}"

            mes_list.append({"role": "user", "content": fqc})

            rep = "My power wanes... I cannot fulfill this search at the moment."
            tc = "neutral"

            try:
                comp = await asyncio.to_thread(
                    self.sc.chat.completions.create,
                    model=self.sm,
                    messages=mes_list,
                    max_tokens=400,
                    temperature=0.7,
                )
                if comp and comp.choices and comp.choices[0].message:
                    rep = comp.choices[0].message.content.strip()
                    tc = self.determine_tone(q)
            except Exception as e:
                l.error(f"Error calling Shapes.inc API for search: {e}")
                if "rate limit" in str(e).lower():
                    rep = "Even a dragon's power is not infinite. My knowledge is temporarily restricted."
                else:
                    rep = "A temporal distortion in the flow of power prevents my search."

            if len(rep) > 1900:
                rep = rep[:1897] + "..."

            await self.r(i, rep)
            self.update_user_memory(g, u, fqc, rep, tc)

        except Exception as e:
            l.error(f"Unexpected error in search command: {e}")
            await self.r(i, "A ripple in the void has interrupted my search.")


async def setup(b):
    await b.add_cog(AIChatCog(b))
