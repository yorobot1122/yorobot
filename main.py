from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

import os
import discord
from discord.ext import commands
import asyncio
import yt_dlp
from discord.ext import tasks
from collections import deque
from serpapi import GoogleSearch
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
from dotenv import load_dotenv

load_dotenv()
DISCORD_TOKEN = os.getenv('TOKEN')
SERP_API_KEY = os.getenv('API')

# --- 봇 기본 설정 ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)
SERP_API_KEY = 'API'

# --- 설정값 ---
COMMAND_CHANNEL_ID = 1391779448839208960
MUSIC_VOICE_CHANNEL_ID = 1391779601906274344
GOOGLE_SEARCH_CHANNEL_ID = 1391814034772197437
DELETE_INTERVAL_MINUTES = 60
clean_task = None

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'default_search': 'auto',
    'quiet': True,
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FFMPEG_PATH = os.path.join(BASE_DIR, "bin", "ffmpeg")

FFMPEG_OPTIONS = {
    'before_options':
    '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
    'executable': FFMPEG_PATH
}

# --- 전역 상태 변수 ---
music_queue = deque()
repeat = False
is_playing = False


def check_command_channel(ctx):
    return ctx.channel.id == COMMAND_CHANNEL_ID


def check_google_channel(ctx):
    return ctx.channel.id == GOOGLE_SEARCH_CHANNEL_ID

Thread(target=run_flask).start()

@bot.event
async def on_ready():
    print(f'{bot.user.name} 로그인 완료')
    global clean_task
    if clean_task is None:
        clean_task = clean_channel.start()


# --- 재생 함수 ---
async def play_next(ctx):
    global is_playing

    if repeat and ctx.voice_client and ctx.voice_client.source:
        source = ctx.voice_client.source
        ctx.voice_client.play(source,
                              after=lambda e: asyncio.run_coroutine_threadsafe(
                                  play_next(ctx), bot.loop))
        return

    if music_queue:
        info = music_queue.popleft()
        url = info['url']
        title = info['title']

        source_audio = discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS)
        source = discord.PCMVolumeTransformer(source_audio, volume=0.5)
        ctx.voice_client.play(source,
                              after=lambda e: asyncio.run_coroutine_threadsafe(
                                  play_next(ctx), bot.loop))
        ctx.voice_client.source = source
        await ctx.send(f"🎵 재생 중: **{title}**")
        await ctx.send(f"재생 URL: {info['url']}")
        is_playing = True
    else:
        await ctx.voice_client.disconnect()
        is_playing = False


# --- !노래 [순번] 제목 or 유튜브 URL ---
@bot.command(name='노래')
@commands.check(check_command_channel)
async def play(ctx, *, arg: str):
    global is_playing
    await ctx.send(f"작업 디렉터리: {os.getcwd()}")
    await ctx.send(f"ffmpeg 절대 경로: {FFMPEG_PATH}")
    if not ctx.voice_client:
        channel = bot.get_channel(MUSIC_VOICE_CHANNEL_ID)
        if channel:
            await channel.connect()
        else:
            await ctx.send("음성 채널을 찾을 수 없습니다.")
            return

    try:
        parts = arg.strip().split()
        if parts[0].isdigit():
            pos = int(parts[0])
            query = " ".join(parts[1:])
        else:
            pos = None
            query = arg

        await ctx.send(f"🔍 '{query}' 검색 중...")

        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
            if "youtube.com/watch" in query or "youtu.be/" in query:
                info = ydl.extract_info(query, download=False)
            else:
                info = ydl.extract_info(f"ytsearch:{query}", download=False)
                if 'entries' in info:
                    info = info['entries'][0]

        if pos is not None and 0 <= pos <= len(music_queue):
            music_queue.insert(pos, info)
            await ctx.send(f"✅ **{info['title']}** 을(를) 대기열 {pos}번째에 추가했습니다.")
        else:
            music_queue.append(info)
            await ctx.send(f"✅ **{info['title']}** 을(를) 대기열에 추가했습니다.")

        if not is_playing:
            is_playing = True
            await play_next(ctx)

    except Exception as e:
        await ctx.send(f"❌ 오류 발생: {e}")


# --- !목록 ---
@bot.command(name='목록')
@commands.check(check_command_channel)
async def show_queue(ctx):
    if not music_queue:
        await ctx.send("🎧 현재 대기열이 비어 있습니다.")
    else:
        msg = "**🎶 현재 대기열:**\n"
        for i, item in enumerate(music_queue):
            msg += f"{i}. {item['title']}\n"
        await ctx.send(msg)


# --- !삭제 n ---
@bot.command(name='삭제')
@commands.check(check_command_channel)
async def delete_track(ctx, index: int):
    try:
        removed = music_queue[index]
        del music_queue[index]
        await ctx.send(f"🗑️ **{removed['title']}** 삭제 완료.")
    except IndexError:
        await ctx.send("❌ 해당 번호의 곡이 대기열에 없습니다.")


# --- !초기화 ---
@bot.command(name='초기화')
@commands.check(check_command_channel)
async def clear_queue(ctx):
    music_queue.clear()
    await ctx.send("🧹 대기열을 초기화했습니다.")


# --- !반복 ---
@bot.command(name='반복')
@commands.check(check_command_channel)
async def toggle_repeat(ctx):
    global repeat
    repeat = not repeat
    await ctx.send(f"🔁 반복 재생이 {'ON' if repeat else 'OFF'} 상태로 설정되었습니다.")


# --- !정지 ---
@bot.command(name='정지')
@commands.check(check_command_channel)
async def stop(ctx):
    global is_playing
    if ctx.voice_client:
        ctx.voice_client.stop()
        await ctx.voice_client.disconnect()
    music_queue.clear()
    is_playing = False
    await ctx.send("⏹️ 재생을 정지하고 음성 채널에서 나갔습니다.")


# --- !일시정지 ---
@bot.command(name='일시정지')
@commands.check(check_command_channel)
async def pause(ctx):
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await ctx.send("⏸️ 일시정지 되었습니다.")
    elif vc and vc.is_paused():
        vc.resume()
        await ctx.send("▶️ 다시 재생합니다.")
    else:
        await ctx.send("현재 재생 중인 곡이 없습니다.")


# --- !볼륨 [0~100] ---
@bot.command(name='볼륨')
@commands.check(check_command_channel)
async def volume(ctx, vol: int):
    if not 0 <= vol <= 100:
        await ctx.send("0에서 100 사이의 값을 입력해주세요.")
        return
    if ctx.voice_client and ctx.voice_client.source and isinstance(
            ctx.voice_client.source, discord.PCMVolumeTransformer):
        ctx.voice_client.source.volume = vol / 100
        await ctx.send(f"🔊 볼륨을 {vol}%로 설정했습니다.")
    else:
        await ctx.send("볼륨을 조절할 수 없습니다.")


# --- !skip ---
@bot.command(name='스킵')
@commands.check(check_command_channel)
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭️ 다음 곡으로 넘어갑니다.")
    else:
        await ctx.send("재생 중인 곡이 없습니다.")


@tasks.loop(minutes=DELETE_INTERVAL_MINUTES)
async def clean_channel():
    channel = bot.get_channel(1391779448839208960)
    if channel is None:
        print(f"채널 ID {1391779448839208960}를 찾을 수 없습니다.")
        return

    def is_not_pinned(msg):
        return not msg.pinned

    try:
        deleted = await channel.purge(limit=100, check=is_not_pinned)
        print(f"{len(deleted)}개의 메시지를 삭제했습니다.")
    except Exception as e:
        print(f"메시지 삭제 중 오류 발생: {e}")


@bot.command(name='정리주기')
@commands.check(check_command_channel)
async def set_clean_interval(ctx, minutes: int):
    global clean_task, DELETE_INTERVAL_MINUTES

    if minutes < 1 or minutes > 1440:
        await ctx.send("❌ 1분 이상 1440분(24시간) 이하의 값을 입력해주세요.")
        return

    DELETE_INTERVAL_MINUTES = minutes

    if clean_task is not None:
        if clean_channel.is_running():
            clean_task.cancel()
            await asyncio.sleep(1)  # 작업 완전 종료 대기

    # change_interval() 대신
    clean_channel.change_interval(minutes=DELETE_INTERVAL_MINUTES)

    clean_task = clean_channel.start()

    await ctx.send(f"✅ 채널 자동 청소 주기를 {DELETE_INTERVAL_MINUTES}분으로 변경했습니다.")


# --- 에러 핸들링 ---
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send(f"❗이 명령어는 <#{COMMAND_CHANNEL_ID}> 채널에서만 사용할 수 있습니다.")
    else:
        raise error


@bot.command(name='명령어', help='사용 가능한 명령어들을 모두 보여줍니다.')
@commands.check(check_command_channel)
async def show_commands(ctx):
    msg = ("**📜 사용 가능한 명령어 목록:**\n"
           "```\n"
           "!노래 [제목 또는 유튜브 URL]         ▶️ 노래를 대기열에 추가합니다\n"
           "!노래 [순번] [제목]                 ▶️ 지정 위치에 추가합니다 (ex: !노래 0 아이유)\n"
           "!목록                              📃 현재 대기열을 보여줍니다\n"
           "!삭제 [번호]                       🗑️ 대기열의 해당 곡을 삭제합니다\n"
           "!초기화                            🧹 대기열을 모두 초기화합니다\n"
           "!반복                              🔁 현재 곡 반복 재생을 ON/OFF 합니다\n"
           "!정지                              ⏹️ 재생을 완전히 정지하고 봇을 퇴장시킵니다\n"
           "!일시정지                           ⏸️ 일시정지 또는 다시 재생합니다\n"
           "!볼륨 [0~100]                      🔊 볼륨을 설정합니다 (예: !볼륨 50)\n"
           "!스킵                             ⏭️ 다음 곡으로 건너뜁니다\n"
           "!명령어                            📜 이 명령어 목록을 출력합니다\n"
           "!정리주기                          🧹 정리주기를 설정합니다(권한있는유저만가능)"
           "```")
    await ctx.send(msg)


@bot.command(name="구글")
@commands.check(check_google_channel)
async def google_search(ctx, *, query):
    await ctx.send(f"🔍 구글에서 '{query}' 검색 중...")

    params = {
        "engine": "google",
        "q": query,
        "api_key": SERP_API_KEY,
        "num": 5
    }

    try:
        search = GoogleSearch(params)
        results = search.get_dict()

        if "organic_results" not in results or len(
                results["organic_results"]) == 0:
            await ctx.send("❌ 검색 결과가 없습니다.")
            return

        msg = "**🔗 검색 결과:**\n"
        for result in results["organic_results"][:5]:
            title = result.get("title", "제목 없음")
            link = result.get("link", "")
            msg += f"• [{title}]({link})\n"

        await ctx.send(msg)

    except Exception as e:
        await ctx.send(f"❌ 오류 발생: {e}")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        if ctx.command.name == "구글":
            await ctx.send(
                f"❗이 명령어는 <#{1391814034772197437}> 채널에서만 사용할 수 있습니다.")
        else:
            await ctx.send(
                f"❗이 명령어는 <#{GOOGLE_SEARCH_CHANNEL_ID}> 채널에서만 사용할 수 있습니다.")
    else:
        raise error


@bot.command(name="디시")
@commands.check(check_google_channel)
async def dc_search(ctx, *, query):
    await ctx.send(f"🔍 디시인사이드 메이플랜드 갤러리에서 '{query}' 검색 중...")

    base_url = "https://gall.dcinside.com/mgallery/board/lists"
    params = {
        "id": "mapleland",
        "s_type": "search_subject_memo",
        "s_keyword": query
    }

    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(base_url, params=params, headers=headers)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        results = soup.select("tr.ub-content")

        if not results:
            await ctx.send("❌ 검색 결과가 없습니다.")
            return

        msg = "**🧾 디시인사이드 검색 결과:**\n"
        count = 0

        for row in results:
            title_tag = row.select_one("a.icon_pic_n")
            if not title_tag:
                title_tag = row.select_one("a.icon_txt_n")

            if title_tag:
                title = title_tag.text.strip()
                href = title_tag['href']
                link = f"https://gall.dcinside.com{href}"
                msg += f"• [{title}]({link})\n"
                count += 1

            if count >= 3:
                break

        await ctx.send(msg)

    except Exception as e:
        await ctx.send(f"❌ 오류 발생: {e}")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        if ctx.command.name == "디시":
            await ctx.send(
                f"❗이 명령어는 <#{1391814034772197437}> 채널에서만 사용할 수 있습니다.")
        else:
            await ctx.send(
                f"❗이 명령어는 <#{GOOGLE_SEARCH_CHANNEL_ID}> 채널에서만 사용할 수 있습니다.")
    else:
        raise error


# --- 봇 실행 ---
bot.run(DISCORD_TOKEN)
