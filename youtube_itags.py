import selenium.common.exceptions
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as chromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import sys
import sqlite3
from datetime import datetime
from urllib import parse
import time

def create_driver():
    chrome_options = chromeOptions()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument('--headless')
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--autoplay-policy=no-user-gesture-required")
    return webdriver.Chrome(options=chrome_options)

pages = ["aqz-KE-bpKQ", "lqiN98z6Dak", "RJnKaAtBPhA"]

def run_driver(page):
    driver = create_driver()
    time_now = time.time()
    driver.set_page_load_timeout(30)
    driver.get("https://www.youtube.com/watch?v="+page)
    while driver.execute_script("return document.readyState;") != "complete":
        time.sleep(1)
    wait = WebDriverWait(driver, 10000)
    youtube_player = wait.until(EC.visibility_of_element_located((By.ID, "player")))
    time.sleep(1)
    print(driver.execute_script("return ytInitialData;").keys())
    driver.quit()

for page in pages:
    run_driver(page)