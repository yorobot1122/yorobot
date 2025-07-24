from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import pickle
import yaml
import time
import os

# 설정 파일 로드
with open("config.yaml") as f:
    config = yaml.safe_load(f)

# Chrome 옵션 설정 (헤드리스 모드)
options = Options()
options.add_argument("--headless=new")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument(f"user-agent={config['user_agent']}")

# 드라이버 설정
driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options
)

try:
    # YouTube 로그인 페이지 접속
    driver.get("https://accounts.google.com/ServiceLogin?service=youtube")
    
    # 수동 로그인 대기 (SSH로 접속해 1회만 로그인)
    print("="*50)
    print("브라우저에서 수동 로그인 필요!")
    print(f"현재 세션 URL: {driver.current_url}")
    print("="*50)
    
    # 5분간 대기 (이 시간 내에 SSH로 VNC 접속해 수동 로그인)
    time.sleep(300)
    
    # 쿠키 저장
    cookies = driver.get_cookies()
    with open(config['cookie_path'], "wb") as f:
        pickle.dump(cookies, f)
    
    print(f"[성공] 쿠키 갱신 완료! 저장 위치: {config['cookie_path']}")

except Exception as e:
    print(f"[에러] 갱신 실패: {str(e)}")
finally:
    driver.quit()
