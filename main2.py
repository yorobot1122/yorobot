# --- 기본 모듈 ---
import os
import asyncio
from threading import Thread
from collections import deque

# --- 외부 라이브러리 ---
from flask import Flask
from dotenv import load_dotenv
import discord
from discord.ext import commands, tasks
import yt_dlp
from serpapi import GoogleSearch
import requests
from bs4 import BeautifulSoup

# --- .env 환경 변수 로딩 ---
load_dotenv()
DISCORD_TOKEN = os.getenv('TOKEN')
SERP_API_KEY = os.getenv('API')

# --- Flask KeepAlive 서버 ---
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot is running!"
def run_flask():
    app.run(host='0.0.0.0', port=8080)
Thread(target=run_flask).start()

# --- 봇 설정 ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- 환경 설정 값 ---
COMMAND_CHANNEL_ID = 1391779448839208960
MUSIC_VOICE_CHANNEL_ID = 1391779601906274344
GOOGLE_SEARCH_CHANNEL_ID = 1391814034772197437
DELETE_INTERVAL_MINUTES = 60
clean_task = None

# --- YTDL / FFMPEG 옵션 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FFMPEG_PATH = os.path.join(BASE_DIR, "bin", "ffmpeg")

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'default_search': 'auto',
    'quiet': True,
    'cookiefile': 'cookies.txt',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

# --- 전역 상태 ---
music_queue = deque()
repeat = False
is_playing = False

# --- 채널 체크 함수 ---
def check_command_channel(ctx):
    return ctx.channel.id == COMMAND_CHANNEL_ID
def check_google_channel(ctx):
    return ctx.channel.id == GOOGLE_SEARCH_CHANNEL_ID

# --- 봇 시작 시 ---
@bot.event
async def on_ready():
    global clean_task
    print(f'{bot.user.name} 로그인 완료')
    if clean_task is None:
        clean_task = clean_channel.start()

# --- 음악 재생 ---
async def play_next(ctx):
    global is_playing

    if repeat and ctx.voice_client and ctx.voice_client.source:
        ctx.voice_client.play(ctx.voice_client.source,
                              after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop))
        return

    if music_queue:
        info = music_queue.popleft()
        url = info['url']
        title = info['title']

        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name=title))
        
        source_audio = discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS)
        source = discord.PCMVolumeTransformer(source_audio, volume=0.5)
        ctx.voice_client.play(source,
                              after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop))
        ctx.voice_client.source = source
        await ctx.send(f"🎵 재생 중: **{title}**")
        is_playing = True
    else:
        await ctx.voice_client.disconnect()
        is_playing = False

# --- 명령어: !노래 ---
@bot.command(name='노래')
@commands.check(check_command_channel)
async def play(ctx, *, arg: str):
    global is_playing
    if not ctx.voice_client:
        channel = bot.get_channel(MUSIC_VOICE_CHANNEL_ID)
        if channel:
            await channel.connect()
        else:
            await ctx.send("음성 채널을 찾을 수 없습니다.")
            return

    try:
        parts = arg.strip().split()
        pos = int(parts[0]) if parts[0].isdigit() else None
        query = " ".join(parts[1:]) if pos is not None else arg

        await ctx.send(f"🔍 '{query}' 검색 중...")

        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
            info = ydl.extract_info(query if "youtube.com" in query or "youtu.be" in query else f"ytsearch:{query}", download=False)
            info = info['entries'][0] if 'entries' in info else info

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

# --- 기타 음악 명령어 ---
@bot.command(name='목록')
@commands.check(check_command_channel)
async def show_queue(ctx):
    await ctx.send("🎧 현재 대기열이 비어 있습니다." if not music_queue else "**🎶 현재 대기열:**\n" + "\n".join([f"{i}. {item['title']}" for i, item in enumerate(music_queue)]))

@bot.command(name='삭제')
@commands.check(check_command_channel)
async def delete_track(ctx, index: int):
    try:
        removed = music_queue[index]
        del music_queue[index]
        await ctx.send(f"🗑️ **{removed['title']}** 삭제 완료.")
    except IndexError:
        await ctx.send("❌ 해당 번호의 곡이 대기열에 없습니다.")

@bot.command(name='초기화')
@commands.check(check_command_channel)
async def clear_queue(ctx):
    music_queue.clear()
    await ctx.send("🧹 대기열을 초기화했습니다.")

@bot.command(name='반복')
@commands.check(check_command_channel)
async def toggle_repeat(ctx):
    global repeat
    repeat = not repeat
    await ctx.send(f"🔁 반복 재생이 {'ON' if repeat else 'OFF'} 상태로 설정되었습니다.")

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

@bot.command(name='볼륨')
@commands.check(check_command_channel)
async def volume(ctx, vol: int):
    if 0 <= vol <= 100 and ctx.voice_client and ctx.voice_client.source and isinstance(ctx.voice_client.source, discord.PCMVolumeTransformer):
        ctx.voice_client.source.volume = vol / 100
        await ctx.send(f"🔊 볼륨을 {vol}%로 설정했습니다.")
    else:
        await ctx.send("❌ 0에서 100 사이 값을 입력하거나 재생 중일 때만 조절 가능합니다.")

@bot.command(name='스킵')
@commands.check(check_command_channel)
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭️ 다음 곡으로 넘어갑니다.")
    else:
        await ctx.send("재생 중인 곡이 없습니다.")

# --- 정리 주기 설정 ---
@tasks.loop(minutes=DELETE_INTERVAL_MINUTES)
async def clean_channel():
    channel = bot.get_channel(COMMAND_CHANNEL_ID)
    if channel:
        deleted = await channel.purge(limit=100, check=lambda m: not m.pinned)
        print(f"{len(deleted)}개의 메시지를 삭제했습니다.")

@bot.command(name='정리주기')
@commands.check(check_command_channel)
@commands.has_permissions(manage_messages=True)
async def set_clean_interval(ctx, minutes: int):
    global clean_task, DELETE_INTERVAL_MINUTES
    if not 1 <= minutes <= 1440:
        await ctx.send("❌ 1~1440 분 사이로 입력해주세요.")
        return
    DELETE_INTERVAL_MINUTES = minutes
    if clean_channel.is_running():
        clean_channel.change_interval(minutes=DELETE_INTERVAL_MINUTES)
    else:
        clean_task = clean_channel.start()
    await ctx.send(f"✅ 채널 자동 청소 주기를 {DELETE_INTERVAL_MINUTES}분으로 변경했습니다.")

# --- 구글 / 디시 검색 ---
@bot.command(name="구글")
@commands.check(check_google_channel)
async def google_search(ctx, *, query):
    await ctx.send(f"🔍 구글에서 '{query}' 검색 중...")
    try:
        search = GoogleSearch({
            "engine": "google",
            "q": query,
            "api_key": SERP_API_KEY,
            "num": 5
        }).get_dict()

        if "organic_results" not in search:
            await ctx.send("❌ 검색 결과가 없습니다.")
            return

        msg = "**🔗 검색 결과:**\n" + "\n".join([f"• [{r.get('title', '제목 없음')}]({r.get('link', '')})" for r in search["organic_results"][:5]])
        await ctx.send(msg)
    except Exception as e:
        await ctx.send(f"❌ 오류 발생: {e}")

@bot.command(name="디시")
@commands.check(check_google_channel)
async def dc_search(ctx, *, query):
    await ctx.send(f"🔍 디시인사이드 메이플랜드 갤러리에서 '{query}' 검색 중...")
    try:
        response = requests.get(
            "https://gall.dcinside.com/mgallery/board/lists",
            params={"id": "mapleland", "s_type": "search_subject_memo", "s_keyword": query},
            headers={"User-Agent": "Mozilla/5.0"}
        )
        soup = BeautifulSoup(response.text, "html.parser")
        results = soup.select("tr.ub-content")
        if not results:
            await ctx.send("❌ 검색 결과가 없습니다.")
            return

        msg = "**🧾 디시 검색 결과:**\n"
        count = 0
        for row in results:
            tag = row.select_one("a.icon_pic_n") or row.select_one("a.icon_txt_n")
            if tag:
                title, href = tag.text.strip(), tag['href']
                msg += f"• [{title}](https://gall.dcinside.com{href})\n"
                count += 1
            if count >= 3:
                break
        await ctx.send(msg)
    except Exception as e:
        await ctx.send(f"❌ 오류 발생: {e}")

# --- 에러 핸들링 (통합) ---
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        if ctx.command.name in ["구글", "디시"]:
            await ctx.send(f"❗이 명령어는 <#{GOOGLE_SEARCH_CHANNEL_ID}> 채널에서만 사용할 수 있습니다.")
        else:
            await ctx.send(f"❗이 명령어는 <#{COMMAND_CHANNEL_ID}> 채널에서만 사용할 수 있습니다.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ 권한이 부족합니다.")
    else:
        raise error

# --- 도움말 ---
@bot.command(name='명령어', help='사용 가능한 명령어들을 모두 보여줍니다.')
@commands.check(check_command_channel)
async def show_commands(ctx):
    await ctx.send(
        "**📜 명령어 목록:**\n"
        "```\n"
        "!노래 [제목/URL]       ▶️ 재생 대기열 추가\n"
        "!노래 [순번] [제목]     ▶️ 지정 위치 추가\n"
        "!목록                 📃 대기열 목록\n"
        "!삭제 [번호]           🗑️ 항목 삭제\n"
        "!초기화                🧹 대기열 비우기\n"
        "!반복                 🔁 반복 ON/OFF\n"
        "!정지                 ⏹️ 정지 및 퇴장\n"
        "!일시정지              ⏸️ 일시정지/재개\n"
        "!볼륨 [0~100]          🔊 볼륨 설정\n"
        "!스킵                 ⏭️ 다음 곡으로\n"
        "!정리주기 [분]         🧹 자동 청소 설정\n"
        "!구글 [검색어]         🔎 구글 검색\n"
        "!디시 [검색어]         🧾 디시 갤러리 검색\n"
        "```"
    )

# --- 봇 실행 ---
bot.run(DISCORD_TOKEN)
