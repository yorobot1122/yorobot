import discord
from discord.ext import commands
import aiohttp
from bs4 import BeautifulSoup
import asyncio
import re
from urllib.parse import quote
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 봇 설정
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

class MapleDB:
    def __init__(self):
        self.base_url = "https://mapledb.kr"
        self.session = None
    
    async def init_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    async def close_session(self):
        if self.session:
            await self.session.close()
    
    async def search_item(self, item_name):
        """아이템 검색"""
        await self.init_session()
        search_url = f"{self.base_url}/search.php?q={quote(item_name)}&t=item"
        
        try:
            async with self.session.get(search_url) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    return self.parse_item_data(soup)
                return None
        except Exception as e:
            print(f"아이템 검색 오류: {e}")
            return None
    
    async def search_monster(self, monster_name):
        """몬스터 검색"""
        await self.init_session()
        search_url = f"{self.base_url}/search.php?q={quote(monster_name)}&t=mob"
        
        try:
            async with self.session.get(search_url) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    return self.parse_monster_data(soup)
                return None
        except Exception as e:
            print(f"몬스터 검색 오류: {e}")
            return None
    
    async def get_popular_items(self):
        """인기 아이템 목록"""
        await self.init_session()
        
        try:
            async with self.session.get(f"{self.base_url}/index.php") as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    return self.parse_popular_items(soup)
                return None
        except Exception as e:
            print(f"인기 아이템 조회 오류: {e}")
            return None
    
    async def get_popular_monsters(self):
        """인기 몬스터 목록"""
        await self.init_session()
        
        try:
            async with self.session.get(f"{self.base_url}/index.php") as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    return self.parse_popular_monsters(soup)
                return None
        except Exception as e:
            print(f"인기 몬스터 조회 오류: {e}")
            return None
    
    def parse_item_data(self, soup):
        """아이템 데이터 파싱"""
        items = []
        
        # 아이템 정보를 담고 있는 요소들을 찾아서 파싱
        item_elements = soup.find_all('div', class_='item-info') or soup.find_all('tr')
        
        for element in item_elements[:5]:  # 최대 5개까지
            try:
                text = element.get_text(strip=True)
                if text and len(text) > 10:
                    lines = text.split('\n')
                    if len(lines) >= 2:
                        name = lines[0].strip()
                        desc = lines[1].strip() if len(lines) > 1 else "설명 없음"
                        
                        # 추가 정보 파싱
                        stats = []
                        for line in lines[2:]:
                            if any(stat in line for stat in ['공격력', 'DEX', 'STR', 'INT', 'LUK', '성공률']):
                                stats.append(line.strip())
                        
                        items.append({
                            'name': name,
                            'description': desc,
                            'stats': stats[:3]  # 최대 3개 스탯
                        })
            except:
                continue
        
        return items if items else [{'name': '검색 결과 없음', 'description': '해당 아이템을 찾을 수 없습니다.', 'stats': []}]
    
    def parse_monster_data(self, soup):
        """몬스터 데이터 파싱"""
        monsters = []
        
        # 몬스터 정보를 담고 있는 요소들을 찾아서 파싱
        monster_elements = soup.find_all('div', class_='monster-info') or soup.find_all('tr')
        
        for element in monster_elements[:5]:  # 최대 5개까지
            try:
                text = element.get_text(strip=True)
                if 'LEVEL' in text and 'HP' in text:
                    lines = text.split('\n')
                    name = lines[0].strip() if lines else "Unknown"
                    
                    # 레벨, HP, MP 등 정보 추출
                    level = self.extract_stat(text, 'LEVEL')
                    hp = self.extract_stat(text, 'HP')
                    mp = self.extract_stat(text, 'MP')
                    accuracy = self.extract_stat(text, '필요 명중률')
                    
                    monsters.append({
                        'name': name,
                        'level': level,
                        'hp': hp,
                        'mp': mp,
                        'accuracy': accuracy
                    })
            except:
                continue
        
        return monsters if monsters else [{'name': '검색 결과 없음', 'level': '?', 'hp': '?', 'mp': '?', 'accuracy': '?'}]
    
    def parse_popular_items(self, soup):
        """인기 아이템 파싱"""
        items = []
        try:
            # "가장 많이 찾는 아이템" 섹션 찾기
            item_section = soup.find(string=re.compile("가장 많이 찾는 아이템"))
            if item_section:
                parent = item_section.parent
                while parent and not parent.find_all('a'):
                    parent = parent.parent
                
                if parent:
                    links = parent.find_all('a')[:8]  # 최대 8개
                    for link in links:
                        text = link.get_text(strip=True)
                        if text and len(text) > 3:
                            items.append(text.split('\n')[0].strip())
        except:
            pass
        
        return items if items else ["투구 민첩 주문서 60%", "귀 장식 민첩 주문서 60%", "투구 지력 주문서 60%"]
    
    def parse_popular_monsters(self, soup):
        """인기 몬스터 파싱"""
        monsters = []
        try:
            # "가장 많이 검색한 몬스터" 섹션 찾기
            monster_section = soup.find(string=re.compile("가장 많이 검색한 몬스터"))
            if monster_section:
                parent = monster_section.parent
                while parent and not parent.find_all('a'):
                    parent = parent.parent
                
                if parent:
                    links = parent.find_all('a')[:8]  # 최대 8개
                    for link in links:
                        text = link.get_text(strip=True)
                        if text and len(text) > 2:
                            monsters.append(text.split('\n')[0].strip())
        except:
            pass
        
        return monsters if monsters else ["마스터 크로노스", "월묘", "비급", "데스테니"]
    
    def extract_stat(self, text, stat_name):
        """텍스트에서 특정 스탯 추출"""
        try:
            pattern = f"{stat_name}\\s*(\\d+[,\\d]*)"
            match = re.search(pattern, text)
            return match.group(1) if match else "?"
        except:
            return "?"

# MapleDB 인스턴스 생성
maple_db = MapleDB()

@bot.event
async def on_ready():
    print(f'{bot.user} 봇이 준비되었습니다!')
    await maple_db.init_session()

@bot.event
async def on_close():
    await maple_db.close_session()

@bot.command(name='아이템', aliases=['item'])
async def search_item(ctx, *, item_name):
    """아이템 검색 명령어"""
    await ctx.send("🔍 아이템을 검색하고 있습니다...")
    
    # 검색 실행
    items = await maple_db.search_item(item_name)
    
    if not items:
        embed = discord.Embed(
            title="❌ 검색 실패",
            description="아이템 검색 중 오류가 발생했습니다.",
            color=0xff4444
        )
        await ctx.send(embed=embed)
        return
    
    # 첫 번째 아이템 정보 표시
    item = items[0]
    embed = discord.Embed(
        title=f"🎒 {item['name']}",
        description=item['description'],
        color=0x4CAF50
    )
    
    if item['stats']:
        stats_text = '\n'.join([f"• {stat}" for stat in item['stats']])
        embed.add_field(name="📊 스탯 정보", value=stats_text, inline=False)
    
    embed.set_footer(text="메이플랜드 DB | mapledb.kr")
    
    # 추가 결과가 있으면 표시
    if len(items) > 1:
        other_items = [f"• {item['name']}" for item in items[1:4]]
        embed.add_field(
            name="🔗 관련 아이템", 
            value='\n'.join(other_items), 
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='몬스터', aliases=['monster', 'mob'])
async def search_monster(ctx, *, monster_name):
    """몬스터 검색 명령어"""
    await ctx.send("🔍 몬스터를 검색하고 있습니다...")
    
    # 검색 실행
    monsters = await maple_db.search_monster(monster_name)
    
    if not monsters:
        embed = discord.Embed(
            title="❌ 검색 실패",
            description="몬스터 검색 중 오류가 발생했습니다.",
            color=0xff4444
        )
        await ctx.send(embed=embed)
        return
    
    # 첫 번째 몬스터 정보 표시
    monster = monsters[0]
    embed = discord.Embed(
        title=f"👹 {monster['name']}",
        color=0xFF9800
    )
    
    embed.add_field(name="🏷️ 레벨", value=monster['level'], inline=True)
    embed.add_field(name="❤️ HP", value=monster['hp'], inline=True)
    embed.add_field(name="💙 MP", value=monster['mp'], inline=True)
    embed.add_field(name="🎯 필요 명중률", value=monster['accuracy'], inline=False)
    
    embed.set_footer(text="메이플랜드 DB | mapledb.kr")
    
    # 추가 결과가 있으면 표시
    if len(monsters) > 1:
        other_monsters = [f"• {monster['name']} (Lv.{monster['level']})" for monster in monsters[1:3]]
        embed.add_field(
            name="🔗 관련 몬스터", 
            value='\n'.join(other_monsters), 
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='인기아이템', aliases=['popular_items', 'hot_items'])
async def popular_items(ctx):
    """인기 아이템 목록"""
    await ctx.send("📈 인기 아이템을 조회하고 있습니다...")
    
    items = await maple_db.get_popular_items()
    
    if not items:
        embed = discord.Embed(
            title="❌ 조회 실패",
            description="인기 아이템 조회 중 오류가 발생했습니다.",
            color=0xff4444
        )
        await ctx.send(embed=embed)
        return
    
    embed = discord.Embed(
        title="🔥 인기 아이템 TOP",
        description="가장 많이 검색되는 아이템들입니다",
        color=0xE91E63
    )
    
    # 아이템들을 번호와 함께 표시
    items_text = []
    for i, item in enumerate(items[:8], 1):
        emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}️⃣"
        items_text.append(f"{emoji} {item}")
    
    embed.add_field(
        name="📊 순위", 
        value='\n'.join(items_text), 
        inline=False
    )
    
    embed.set_footer(text="메이플랜드 DB | mapledb.kr")
    await ctx.send(embed=embed)

@bot.command(name='인기몬스터', aliases=['popular_monsters', 'hot_monsters'])
async def popular_monsters(ctx):
    """인기 몬스터 목록"""
    await ctx.send("📈 인기 몬스터를 조회하고 있습니다...")
    
    monsters = await maple_db.get_popular_monsters()
    
    if not monsters:
        embed = discord.Embed(
            title="❌ 조회 실패",
            description="인기 몬스터 조회 중 오류가 발생했습니다.",
            color=0xff4444
        )
        await ctx.send(embed=embed)
        return
    
    embed = discord.Embed(
        title="👹 인기 몬스터 TOP",
        description="가장 많이 검색되는 몬스터들입니다",
        color=0x9C27B0
    )
    
    # 몬스터들을 번호와 함께 표시
    monsters_text = []
    for i, monster in enumerate(monsters[:8], 1):
        emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}️⃣"
        monsters_text.append(f"{emoji} {monster}")
    
    embed.add_field(
        name="📊 순위", 
        value='\n'.join(monsters_text), 
        inline=False
    )
    
    embed.set_footer(text="메이플랜드 DB | mapledb.kr")
    await ctx.send(embed=embed)

@bot.command(name='도움말', aliases=['help_kr', 'commands'])
async def help_command(ctx):
    """봇 사용법 안내"""
    embed = discord.Embed(
        title="🤖 메이플랜드 봇 사용법",
        description="메이플랜드 데이터베이스 정보를 조회할 수 있습니다",
        color=0x2196F3
    )
    
    commands_info = [
        "**!아이템 [아이템명]** - 아이템 정보 검색",
        "**!몬스터 [몬스터명]** - 몬스터 정보 검색", 
        "**!인기아이템** - 인기 아이템 TOP 목록",
        "**!인기몬스터** - 인기 몬스터 TOP 목록",
        "**!도움말** - 이 도움말 표시"
    ]
    
    embed.add_field(
        name="📋 명령어 목록",
        value='\n'.join(commands_info),
        inline=False
    )
    
    embed.add_field(
        name="💡 사용 예시",
        value="```\n!아이템 투구 민첩 주문서\n!몬스터 마스터 크로노스\n!인기아이템\n```",
        inline=False
    )
    
    embed.set_footer(text="Data from mapledb.kr | Made with ❤️")
    await ctx.send(embed=embed)

# 에러 핸들링
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(
            title="❌ 명령어 오류",
            description="검색할 이름을 입력해주세요!\n예: `!아이템 투구 민첩 주문서`",
            color=0xff4444
        )
        await ctx.send(embed=embed)
    elif isinstance(error, commands.CommandNotFound):
        embed = discord.Embed(
            title="❓ 알 수 없는 명령어",
            description="`!도움말`을 입력해서 사용 가능한 명령어를 확인하세요!",
            color=0xFFC107
        )
        await ctx.send(embed=embed)
    else:
        print(f"예상치 못한 오류: {error}")

# 봇 실행
if __name__ == "__main__":
    # .env 파일에서 봇 토큰 가져오기
    TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    
    if not TOKEN:
        print("❌ .env 파일에서 DISCORD_BOT_TOKEN을 찾을 수 없습니다.")
        print("💡 .env 파일에 다음과 같이 추가해주세요:")
        print("DISCORD_BOT_TOKEN=your_bot_token_here")
        exit(1)
    
    try:
        print("🤖 봇을 시작합니다...")
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ 봇 토큰이 잘못되었습니다. .env 파일의 DISCORD_BOT_TOKEN을 확인해주세요.")
    except Exception as e:
        print(f"❌ 봇 실행 중 오류: {e}")
