from collections import defaultdict

import discord, random
from discord.ext import commands
from sqlalchemy import and_

import utils.Logs as logs
from utils.database.Database import SessionContext
from utils.database.model.users import Users

from enum import Enum


class VoiceType(Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    CAT = "BLACKCAT"

class TTS:

    def __init__(self, bot):
        self.bot = bot
        self.message_queue = defaultdict(list)
        self.is_cat = defaultdict(bool)
        self.file_path = "./data"

    def cleanup_tts(self, guild_id):
        if self.message_queue.get(guild_id):
            del self.message_queue[guild_id]

    async def read_message_coroutine(self, guild, voice_client):
        message = None
        try:
            message = self.message_queue[guild.id].pop(0)

            file = f"{guild.id}.mp3"
            result = self.synthesize_text(file, message)

            if type(result) is tuple and result[0] is False:
                embed = discord.Embed(
                    color=0xB22222, title="[ 🚨TTS 오류 ]",
                    description=f"아래의 오류가 발생했습니다.\n{result[1]}"
                )
                embed.set_footer(text=f"{self.bot.user.name}", icon_url=self.bot.user.display_avatar)
                await voice_client.channel.send(embed=embed)
                # self.delete_tts_channel.append(guild_id)
                return
            if result is True:
                voice_client.play(
                    discord.FFmpegPCMAudio(source=f"{self.file_path}/{file}"),
                    after=lambda x: __import__('os').remove(f"{self.file_path}/{file}")
                )
                # self.tts_channel[guild_id].timer = 0
        except Exception as e:
            await logs.send_log(bot=self.bot, log_text=f"{guild.name}에서 {message.content}를 재생 하는데 실패했습니다.\nError: {e}")

    @commands.command(name="남자", aliases=["남성", "남성TTS"])
    async def 남자TTS(self, ctx):
        if ctx.author.voice is None:
            return

        with SessionContext() as session:
            user = session.query(Users).filter(
                and_(Users.id == ctx.author.id, Users.guild_id == ctx.author.guild.id)).first()

            user.voice_type = VoiceType.MALE.value
            session.commit()
        await ctx.reply(f"TTS 목소리를 남성으로 변경합니다.", mention_author=False)

    @commands.command(name="여자", aliases=["여성", "여성TTS"])
    async def 여자TTS(self, ctx):
        if ctx.author.voice is None:
            return

        with SessionContext() as session:
            user = session.query(Users).filter(
                and_(Users.id == ctx.author.id, Users.guild_id == ctx.author.guild.id)).first()

            user.voice_type = VoiceType.FEMALE.value
            session.commit()
        await ctx.reply(f"TTS 목소리를 여성으로 변경합니다.", mention_author=False)

    @commands.command(name="흑이체")
    async def 흑이체(self, ctx):
        if ctx.author.voice is None:
            return

        is_active = False

        with SessionContext() as session:
            author_voice = session.query(Users).filter(
                and_(Users.id == ctx.author.id, Users.guild_id == ctx.author.guild.id)).first()
            if author_voice.voice_type.startswith(VoiceType.CAT.value):
                author_voice.voice_type = author_voice.voice_type[len(VoiceType.CAT.value):]
            else:
                prev_type = author_voice.voice_type
                author_voice.voice_type = f"{VoiceType.CAT.value}{prev_type}"
                is_active = True
            session.add(author_voice)
            session.commit()

        await ctx.reply(f"흑이체를 {'활성화' if is_active else '비활성화'}합니다.", mention_author=False)

    @staticmethod
    def cat_speech(text):
        sentences = text.split(" ")

        trans_text = []
        for sentence in sentences:
            l = len(sentence)
            res = ""
            if l == 1:
                res = "냥"
            else:
                # 애옹, 야옹
                l -= 1
                res += random.choice(["애", "야", "먀"])

                for _ in range(l - 1):
                    l -= 1
                    res += "오"

                res += "옹"
            trans_text.append(res)
        return " ".join(trans_text)

    def preprocess_text(self, effect, text):
        import re
        from emoji import core

        print(f"synthesize_text : {text}")

        # 1. 이모지를 먼저 제거합니다.
        text = core.replace_emoji(text, replace="")

        # 2. 남은 텍스트에서 디스코드 이모지 문자열 <:이모지:> 을 검사해서 제거합니다.
        pattern = r'<(.*?)>'
        matches = re.findall(pattern, text)
        if matches:
            for pat in matches:
                text = text.replace(f"<{pat}>", "")

        text = text.strip()

        # 모두 제거 후, 문자열이 공백이면 return 합니다.
        if text == "":
            return False

        # 흑이체 사용할 대상
        if effect is not None and effect == VoiceType.CAT.value:
            text = self.cat_speech(text)

        return text

    def synthesize_text(self, file, message):
        from google.cloud import texttospeech

        author = message.author
        user_info = None
        with SessionContext() as session:
            user_info = session.query(Users).filter(
                and_(Users.id == author.id, Users.guild_id == author.guild.id)).first()

        effect = None
        gender = "MALE"
        if user_info is not None:
            if user_info.voice_type.startswith(VoiceType.CAT.value):
                effect = VoiceType.CAT.value
                gender = user_info.voice_type[len(VoiceType.CAT.value):]
            else:
                gender = user_info.voice_type

        text = self.preprocess_text(effect, message.content)

        # text가 False이면 tts 취소하기
        if text is False:
            return False

        client = texttospeech.TextToSpeechClient()
        text_length = len(text)
        # 최대 길이를 200으로 지정 (지나치게 길어지면 에러 발생)
        max_length = 200

        # 문자열의 길이가 최대 길이보다 크면 return 합니다.
        if text_length > max_length: return False

        # 텍스트 변환
        input_text = texttospeech.SynthesisInput(text=text)
        gender_info = {
            "MALE": {
                "name": "ko-KR-Neural2-C",
                "ssml_gender": texttospeech.SsmlVoiceGender.MALE,
                "pitch": 1.2
            },
            "FEMALE": {
                "name": "ko-KR-Neural2-A",
                "ssml_gender": texttospeech.SsmlVoiceGender.FEMALE,
                "pitch": 2.0
            }
        }

        # 오디오 설정 (예제에서는 한국어, 남성C)
        voice = texttospeech.VoiceSelectionParams(
            language_code="ko-KR",
            name=gender_info[gender]["name"],
            ssml_gender=gender_info[gender]["ssml_gender"],
        )

        speed = 1.5
        text_speed = [(10, 1.1), (20, 1.2), (40, 1.4)]
        for le, sp in text_speed:
            if text_length <= le:
                speed = sp
                break

        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=speed,
            pitch=gender_info[gender]["pitch"]
        )

        try:
            response = client.synthesize_speech(
                request={"input": input_text, "voice": voice, "audio_config": audio_config}
            )
        except Exception as e:
            return False, e

        # audio 폴더 안에 output.mp3라는 이름으로 파일 생성
        with open(f"{self.file_path}/{file}", "wb") as out:
            out.write(response.audio_content)

        return True
