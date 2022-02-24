from cgitb import html
import re
import time
import selenium.common.exceptions

from selenium import webdriver
# -> enables looking at requests and could aid in figuring out buffer size in bytes instead of time
#from seleniumwire import webdriver

# selenium wire only changes web driver import
from selenium.webdriver.chrome.options import Options as chromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import sys
import sqlite3
from datetime import datetime
import hashlib
import uuid
import os
from urllib.parse import urlparse, parse_qs

dnsproxy_dir = "/home/ubuntu/dnsproxy/"


pages = ["aqz-KE-bpKQ"]



relevant_resource_timing_keys = ['name', 'nextHopProtocol']




browser = "chrome"
google_video_url = ""


def create_driver(cacheWarming=0, google_video_url="googlevideo.com"):
    if browser == "chrome":
        chrome_options = chromeOptions()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument('--headless')
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--autoplay-policy=no-user-gesture-required")
        chrome_options.add_argument('--disable-http-cache')
        if cacheWarming == 0:
            print(google_video_url)
            #comma separated list, doesnt accept wildcards
            chrome_options.add_argument('--origin-to-force-quic-on='+google_video_url)
        return webdriver.Chrome(options=chrome_options)


#By default, WebDriverWait calls the ExpectedCondition every 500 milliseconds until it returns success.
class video_element_has_duration_attribute(object):
    """An expectation for checking that a video element has a duration that is not NaN.

    locator - used to find the element
    returns the WebElement once it has the particular css class
    """

    def __call__(self, driver):
        # Finding the referenced element
        resources = []
        try:
            resources.extend(driver.execute_script(
                'return performance.getEntriesByType("resource");'))
            element = driver.find_element(By.TAG_NAME, "video")
            if element.get_attribute("duration") != "NaN":
                return element.get_attribute("duration"), resources
            else:
                return False
        except Exception as e:
            return False


def load_youtube(
    driver,
    fwidth=640,
    fheight=360,
    suggested_quality="auto",
    start_seconds=0,
    play_duration_seconds=30,
    video_id="aqz-KE-bpKQ",
):
    script_get_video_ended = 'return arguments[0].ended;'

    # https://developer.mozilla.org/en-US/docs/Web/API/Resource_Timing_API/Using_the_Resource_Timing_API
    script_get_resource_timing_buffer_level = 'return performance.getEntriesByType("resource").length;'
    script_get_resource_timing = 'return performance.getEntriesByType("resource");'

    try:
        driver.set_page_load_timeout(15)
        driver.get("http://localhost:22222/youtube_iframe.html")
        while driver.execute_script("return document.readyState;") != "complete":
            time.sleep(1)

        try:
            wait = WebDriverWait(driver, 15)
            youtube_player_iframe = wait.until(
                EC.visibility_of_element_located((By.ID, "player"))
            )
            time.sleep(1)
            driver.execute_script(f"setPlayerSize({fwidth},{fheight});")
            driver.execute_script(
                f'setVideo("{video_id}",{start_seconds},"{suggested_quality}");'
            )
            time.sleep(0.5)
            # either start video here or later, either way we appear to be missing the initial buffer in the resource timing api
            driver.execute_script("startVideoAndLog()")
            # youtube_player_iframe = driver.find_element(By.ID, 'player')
            try:
                print("switching to yt iframe")
                driver.switch_to.frame(youtube_player_iframe)


                resource_timings = []
                resource_timings.extend(
                    driver.execute_script(script_get_resource_timing))
                last_len_resource_timings_buffer = len(resource_timings)-1
                buffer_was_reset = False

                resource_timings_buffer_limit = 300
                driver.execute_script(
                    f'performance.setResourceTimingBufferSize({resource_timings_buffer_limit});')

                tmp_timings = driver.execute_script(script_get_resource_timing)
                if len(tmp_timings) > last_len_resource_timings_buffer:
                    resource_timings.extend(tmp_timings)
                    last_len_resource_timings_buffer = len(tmp_timings)
                    print(
                        'timings api returned more resources after setting buffer size: '+str(len(tmp_timings)))
                    
                # this wait also results in script_get_video_buffered running without crashing selenium
                # this also clears the resource timing buffer for some reason
                wait = WebDriverWait(driver, 3)
                video_duration_seconds, resources_from_waiting_for_video = wait.until(
                    video_element_has_duration_attribute()
                )
                tmp_timings = driver.execute_script(script_get_resource_timing)
                if len(tmp_timings) > last_len_resource_timings_buffer:
                    resource_timings.extend(tmp_timings)
                    last_len_resource_timings_buffer = len(tmp_timings)
                    print(
                        'timings api returned more resources after setting buffer size: '+str(len(tmp_timings)))
                    
                if len(tmp_timings) < last_len_resource_timings_buffer:
                    buffer_was_reset = True
                    print('buffer was reset')
                if play_duration_seconds <= 0:
                    play_duration_seconds = int(
                        float(video_duration_seconds)) + 20

                # get movie player element in selenium to pass into execute script calls
                nerd_stats_movie_player = driver.find_element(By.ID, "movie_player")
                html_video_player = driver.find_element(By.TAG_NAME, "video")

                #logging loop until the measurement is finished
                while play_duration_seconds >= 1:
                    if buffer_was_reset == False:
                        tmp_timings = driver.execute_script(
                            script_get_resource_timing)
                        if len(tmp_timings) > last_len_resource_timings_buffer:
                            resource_timings.extend(tmp_timings)
                            last_len_resource_timings_buffer = len(tmp_timings)
                            print(
                                'timings api returned more resources inside logging loop: '+str(len(tmp_timings)))
                            
                        if len(tmp_timings) < last_len_resource_timings_buffer:
                            buffer_was_reset = True
                            print('buffer was reset')

                    resource_timings_buffer = driver.execute_script(
                        script_get_resource_timing_buffer_level)

                    if resource_timings_buffer >= (resource_timings_buffer_limit - 50):
                        resource_timings_buffer_limit = resource_timings_buffer_limit + 100
                        driver.execute_script(
                            f'performance.setResourceTimingBufferSize({resource_timings_buffer_limit});')

                    if driver.execute_script(script_get_video_ended, html_video_player):
                        break
                    play_duration_seconds = play_duration_seconds - 0.5
                    time.sleep(0.5)
                resource_timings.extend(
                    driver.execute_script(script_get_resource_timing))
                resource_timings.extend(resources_from_waiting_for_video)
                

                driver.switch_to.default_content()
                print("switched out of iframe")

                return resource_timings
            except selenium.common.exceptions.WebDriverException as e:
                print(
                    "failed switching selenium focus to youtube iframe or monitoring loop")
                print(str(e))
                return [{"error": "failed switching selenium focus to youtube iframe or monitoring loop ### " + str(e)}]
        except selenium.common.exceptions.WebDriverException as e:
            print("failed loading player")
            return [{"error": "failed loading player ### " + str(e)}]
    except selenium.common.exceptions.WebDriverException as e:
        print("failed driver.get()")
        return [{"error": "failed driver.get() ### " + str(e)}]


def perform_page_load(cache_warming=0):
    print(google_video_url)
    driver = create_driver(cache_warming, google_video_url)
    # >>timestamp<< is the measurement itself, >>time<< is the time a callback/log event happened
    # performance_metrics = get_page_performance_metrics(driver, page)
    # nerd_stats seems to be ~20 seconds ahead of event_log on my local machine, both log in 1s intervals so the delta should not be that large
    if cache_warming == 1:
        resource_timings = load_youtube(driver, play_duration_seconds=5)
    else:
        resource_timings = load_youtube(driver, play_duration_seconds=10)
    driver.quit()
    if "error" not in resource_timings[0]:
        return parse_resource_timings(resource_timings)
    return "error"





def parse_resource_timings(resource_timings):
    #resource_time_start_adjusted_timestamp = resource_timings.pop(0)
    # only look at resources that are actual video or audio requests
    resource_timings = [timing for timing in resource_timings if "googlevideo.com/videoplayback" in timing['name']]
    # remove keys that are static or always empty
    resource_timings = [{k: v for k, v in timing_dict.items(
    ) if k in relevant_resource_timing_keys} for timing_dict in resource_timings]
    # remove duplicates, all items inside the dicts should be hashable
    [dict(t) for t in {tuple(d.items()) for d in resource_timings}]
    print(set([item['nextHopProtocol'] for item in resource_timings]))
    netlocs = []
    netlocs_h3 =[]
    netlocs_h1 = []
    for item in resource_timings:
        if item['nextHopProtocol'] == 'http/1.1':
            parse_res = urlparse(item['name'])
            opts = parse_qs(parse_res.query)
            if opts['range'][0][0] == '0':
                print('first request')
            else:
                print(opts['range'][0])
            print(parse_res.netloc + " " + ''.join(opts['itag']) + " " + ''.join(str(opts['range'])) + " " + ''.join(str(opts['rbuf'])))
            netlocs_h1.append(parse_res.netloc)
        else:
            parse_res = urlparse(item['name'])
            opts = parse_qs(parse_res.query)
            if opts['range'][0][0] == '0':
                print(parse_res.netloc + " " + ''.join(opts['itag']) + " " + ''.join(str(opts['range'])) + " " + ''.join(str(opts['rbuf'])))
            netlocs_h3.append(parse_res.netloc)
    netlocs_h1 = list(set(netlocs))
    netlocs_h3 = list(set(netlocs_h3))
    if len(netlocs_h1) > 1:
        print(netlocs_h1)
    if len(netlocs_h3) > 1:
        print(netlocs_h3)
    print('---')
    print(':443, '.join(netlocs)+':443')
    print(':443, '.join(netlocs_h3)+':443')
    netlocs = list(set(netlocs_h1+netlocs_h3))
    return ':443, '.join(netlocs)+':443'
    return netlocs[0] if len(netlocs) > 0 else netlocs_h3[0]



# cache warming
print("cache warming")
google_video_url = perform_page_load(1)
# performance measurement
print("measuring")
perform_page_load()

