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

# 채널별 정리 설정 (채널ID: 정리주기(분))
CHANNEL_CLEAN_SETTINGS = {
    COMMAND_CHANNEL_ID: 60,
    GOOGLE_SEARCH_CHANNEL_ID: 60
}
clean_tasks = {}

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
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -threads 1',  # CPU 스레드 제한 추가
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

# --- 채널 정리 태스크 생성 함수 ---
def create_clean_task(channel_id):
    @tasks.loop(minutes=CHANNEL_CLEAN_SETTINGS[channel_id])
    async def task():
        channel = bot.get_channel(channel_id)
        if channel:
            try:
                deleted = await channel.purge(limit=100, check=lambda m: not m.pinned)
                print(f"#{channel.name} 채널에서 {len(deleted)}개의 메시지 삭제")
            except Exception as e:
                print(f"채널 정리 오류: {e}")
    return task

# --- 봇 시작 시 ---
@bot.event
async def on_ready():
    print(f'{bot.user.name} 로그인 완료')
    
    # 채널별 정리 태스크 시작
    for channel_id in CHANNEL_CLEAN_SETTINGS:
        task = create_clean_task(channel_id)
        task.start()
        clean_tasks[channel_id] = task

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
        
        try:
            source_audio = discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS)
            source = discord.PCMVolumeTransformer(source_audio, volume=0.5)
            ctx.voice_client.play(source,
                                  after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop))
            ctx.voice_client.source = source
            await ctx.send(f"🎵 재생 중: **{title}**")
            is_playing = True
        except Exception as e:
            print(f"재생 실패: {e}")
            # 오류 발생 시 2초 후 재시도
            await asyncio.sleep(2)
            await play_next(ctx)
    else:
        if ctx.voice_client:
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

        # 비동기 스레드에서 블로킹 작업 실행
        def download_info():
            with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
                return ydl.extract_info(
                    query if "youtube.com" in query or "youtu.be" in query else f"ytsearch:{query}",
                    download=False
                )
        
        raw_info = await asyncio.to_thread(download_info)
        info = raw_info['entries'][0] if 'entries' in raw_info else raw_info

        # 메모리 절약을 위한 최소 데이터 저장
        song_data = {
            'url': info['url'],
            'title': info['title'],
            'duration': info.get('duration', 0)
        }

        if pos is not None and 0 <= pos <= len(music_queue):
            music_queue.insert(pos, song_data)
            await ctx.send(f"✅ **{song_data['title']}** 을(를) 대기열 {pos}번째에 추가했습니다.")
        else:
            music_queue.append(song_data)
            await ctx.send(f"✅ **{song_data['title']}** 을(를) 대기열에 추가했습니다.")

        # 재생 중이 아닐 때만 즉시 재생
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
@bot.command(name='정리주기')
@commands.check(check_command_channel)
@commands.has_permissions(manage_messages=True)
async def set_clean_interval(ctx, channel: discord.TextChannel, minutes: int):
    if not 1 <= minutes <= 1440:
        await ctx.send("❌ 1~1440 분 사이로 입력해주세요.")
        return
    
    if channel.id not in CHANNEL_CLEAN_SETTINGS:
        await ctx.send("❌ 정리 가능한 채널이 아닙니다.")
        return
    
    # 기존 태스크 중지
    if channel.id in clean_tasks:
        clean_tasks[channel.id].cancel()
    
    # 새 설정 적용
    CHANNEL_CLEAN_SETTINGS[channel.id] = minutes
    
    # 새 태스크 시작
    task = create_clean_task(channel.id)
    task.start()
    clean_tasks[channel.id] = task
    
    await ctx.send(f"✅ #{channel.name} 채널의 자동 청소 주기를 {minutes}분으로 변경했습니다.")

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
        # 검색 요청
        response = requests.get(
            "https://gall.dcinside.com/mgallery/board/lists",
            params={
                "id": "mapleland",
                "s_type": "search_subject_memo",
                "s_keyword": query
            },
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Referer": "https://gall.dcinside.com/"
            }
        )
        
        # HTML 파싱
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 게시글 목록 선택
        posts = soup.select('tbody > tr')
        
        if not posts:
            await ctx.send("❌ 검색 결과가 없습니다.")
            return

        # 상위 5개 결과 추출
        msg = "**🧾 디시 검색 결과 (최신 5개):**\n"
        count = 0
        
        for post in posts:
            if count >= 5:
                break
                
            # 공지사항 건너뛰기
            if 'notice' in post.get('class', []):
                continue
                
            # 제목 추출
            title_tag = post.select_one('.gall_tit a')
            if not title_tag:
                continue
                
            title = title_tag.text.strip()
            link = title_tag.get('href', '')
            
            # 링크 형식 보정
            if link and not link.startswith('http'):
                link = f"https://gall.dcinside.com{link}"
            
            # 번호 추출 (공지사항 필터링)
            num_tag = post.select_one('.gall_num')
            if num_tag and num_tag.text.strip().isdigit():
                msg += f"• [{title}]({link})\n"
                count += 1

        await ctx.send(msg if count > 0 else "❌ 검색 결과가 없습니다.")
        
    except Exception as e:
        await ctx.send(f"❌ 오류 발생: {str(e)}")

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
    elif isinstance(error, commands.ChannelNotFound):
        await ctx.send("❌ 채널을 찾을 수 없습니다.")
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
        "!정리주기 [채널] [분]  🧹 자동 청소 설정\n"
        "!구글 [검색어]         🔎 구글 검색\n"
        "!디시 [검색어]         🧾 디시 갤러리 검색\n"
        "```\n"
        f"**채널별 명령어 사용처:**\n"
        f"- 음악 명령어: <#{COMMAND_CHANNEL_ID}>\n"
        f"- 검색 명령어: <#{GOOGLE_SEARCH_CHANNEL_ID}>"
    )

# --- 봇 실행 ---
bot.run(DISCORD_TOKEN)
