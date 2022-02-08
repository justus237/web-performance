from cgitb import html
import re
import time
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
import hashlib
import uuid
import os
##from seleniumwire import webdriver -> enabled looking at requests and could aid in figuring out buffer size in bytes instead of time

dnsproxy_dir = "/home/ubuntu/dnsproxy/"


pages = ["https://www.youtube.com/watch?v=aqz-KE-bpKQ"]


# performance elements to extract
measurement_elements = (
    'id', 'protocol', 'server', 'domain', 'vantagePoint', 'timestamp', 'connectEnd', 'connectStart', 'domComplete',
    'domContentLoadedEventEnd', 'domContentLoadedEventStart', 'domInteractive', 'domainLookupEnd', 'domainLookupStart',
    'duration', 'encodedBodySize', 'decodedBodySize', 'transferSize', 'fetchStart', 'loadEventEnd', 'loadEventStart',
    'requestStart', 'responseEnd', 'responseStart', 'secureConnectionStart', 'startTime', 'firstPaint',
    'firstContentfulPaint', 'nextHopProtocol', 'cacheWarming', 'error')

# create db
#db = sqlite3.connect('web-performance.db')
#cursor = db.cursor()
'''
# retrieve input params
try:
    protocol = sys.argv[1]
    server = sys.argv[2]
    proxyPID = int(sys.argv[3])
except IndexError:
    print("Input params incomplete (protocol, server, dnsproxyPID) - set dnsproxyPID to 0 if you don't use dnsproxy")
    sys.exit(1)

if len(sys.argv) > 4:
    browser = sys.argv[4]
else:
    browser = 'firefox'

if len(sys.argv) > 5:
    vp_dict = {'compute-1': 'US East', 'ap-northeast-3': 'Asia Pacific Northeast', 'af-south-1': 'Africa South',
               'eu-central-1': 'Europe Central', 'ap-southeast-2': 'Asia Pacific Southeast', 'us-west-1': 'US West',
               'sa-east-1': 'South America East'}
    vantage_point = vp_dict.get(sys.argv[5], '')
else:
    vantage_point = ''
'''
browser = 'chrome'
# Chrome options
chrome_options = chromeOptions()
chrome_options.add_argument('--no-sandbox')
#chrome_options.add_argument('--headless')
chrome_options.add_argument('--disable-dev-shm-usage')
#chrome_options.add_argument('--media-cache-size=2147483647') -> does not affect how much youtube pre-buffers
chrome_options.add_argument('--disable-web-security')
chrome_options.add_argument('--allow-file-access-from-files')
#avoid having to start the video muted due to chrome autoplay policies
chrome_options.add_argument('--autoplay-policy=no-user-gesture-required') 



def create_driver():
    if browser == 'chrome':
        return webdriver.Chrome(options=chrome_options)
    else:
        return webdriver.Firefox(options=firefox_options)


def get_page_performance_metrics(driver, page):
    script = """
            // Get performance and paint entries
            var perfEntries = performance.getEntriesByType("navigation");
            var paintEntries = performance.getEntriesByType("paint");
    
            var entry = perfEntries[0];
            var fpEntry = paintEntries[0];
            var fcpEntry = paintEntries[1];
    
            // Get the JSON and first paint + first contentful paint
            var resultJson = entry.toJSON();
            resultJson.firstPaint = 0;
            resultJson.firstContentfulPaint = 0;
            try {
                for (var i=0; i<paintEntries.length; i++) {
                    var pJson = paintEntries[i].toJSON();
                    if (pJson.name == 'first-paint') {
                        resultJson.firstPaint = pJson.startTime;
                    } else if (pJson.name == 'first-contentful-paint') {
                        resultJson.firstContentfulPaint = pJson.startTime;
                    }
                }
            } catch(e) {}
            
            return resultJson;
            """
    try:
        driver.set_page_load_timeout(30)
        driver.get(f'https://{page}')
        return driver.execute_script(script)
    except selenium.common.exceptions.WebDriverException as e:
        return {'error': str(e)}

def load_youtube(driver, fwidth=640, fheight=360, suggested_quality="default", video_id="YE7VzlLtp-4", start_seconds=0):
    script_get_nerdstats = """
        var currentTime = new Date().getTime();
        var iframe_player = document.getElementById("movie_player")
        return {"time":currentTime, "nerdstats":iframe_player.getStatsForNerds()};
        """

    script_get_video_duration = 'return getVideoDuration()'#'video = document.getElementsByTagName("video")[0]; return video.duration;'
    script_get_video_ended = """
        var video = document.getElementsByTagName("video")[0];
        return video.ended
    """
    script_get_video_buffered = """
        var video = document.getElementsByTagName("video")[0];
        var bufferedTime = video.buffered.end(0) - video.buffered.start(0);
        return bufferedTime;
    """
    #https://github.com/lsinfo3/yomo-docker/blob/master/files/pluginAsJSFormated.js
    script_get_video_buffered_alt = """
        var video = document.getElementsByTagName("video")[0];
        var currentTime = video.currentTime;
		var buffLen = video.buffered.length;
		var availablePlaybackTime = video.buffered.end(buffLen-1);
		var bufferedTime = availablePlaybackTime - currentTime;
        return bufferedTime;
    """

    nerdstatslog = []
    try:
        #driver.set_page_load_timeout(30)
        #driver.get(f'https://{page}')
        #driver.get("file:///Users/justus/web-performance/youtube_iframe.html")
        driver.get("http://localhost:22222/youtube_iframe.html")
        while driver.execute_script('return document.readyState') != 'complete':
            time.sleep(1)


        try:
            wait = WebDriverWait(driver, 10000)
            youtube_player_iframe = wait.until(EC.visibility_of_element_located((By.ID, 'player')))
            driver.execute_script(f'setPlayerSize({fwidth},{fheight});')
            driver.execute_script(f'setVideo("{video_id}",{start_seconds},"{suggested_quality}");')
            time.sleep(1)
            video_duration_sec = driver.execute_script(script_get_video_duration)
            print(video_duration_sec)
            driver.execute_script('startVideoAndLog()')
            #youtube_player_iframe = driver.find_element_by_id('player')
            print('switching to yt iframe')
            driver.switch_to.frame(youtube_player_iframe)
            #driver.switch_to.frame('player')
            #driver.switch_to.default_content()
            #html5video = driver.find_element(By.TAG_NAME, "video")
            #print(driver.find_element_by_tag_name("video").get_attribute("src"))
            while True:
                print('fetching nerdstats')
                nerdstatslog.append(driver.execute_script(script_get_nerdstats))
                #print(driver.execute_script(script_get_video_buffered))
                #print(driver.execute_script(script_get_video_buffered_alt))
                if driver.execute_script(script_get_video_ended):
                    print(nerdstatslog)
                    return None
                time.sleep(1)
        except selenium.common.exceptions.WebDriverException as e:
            #driver.quit()
            print('failed inner try')
            print(str(e))
            return {'error': str(e)}

        
        #driver.find
        #driver.execute_cdp_cmd('player = document.getElementsByTagName("video")[0];')
        #return driver.execute_script(script)
        return None
    except selenium.common.exceptions.WebDriverException as e:
        #driver.quit()
        print('failed outer try')
        print(str(e))
        return {'error': str(e)}

def perform_page_load(page, cache_warming=0):
    #keep browser open for local testing
    global driver;
    driver = create_driver()
    timestamp = datetime.now()
    #performance_metrics = get_page_performance_metrics(driver, page)
    performance_metrics = load_youtube(driver)
    #print(performance_metrics)
    driver.switch_to.default_content()
    print('switched out of iframe')
    print(driver.execute_script("return getEventLog();"))
    driver.quit()
    #driver.execute_script('return window.eventLog')

    #driver.quit()
    ## insert page into database
    #if 'error' not in performance_metrics:
    #    insert_performance(page, performance_metrics, timestamp, cache_warming=cache_warming)
    #else:
    #    insert_performance(page, {k: 0 for k in measurement_elements}, timestamp, cache_warming=cache_warming,
    #                       error=performance_metrics['error'])
    # send restart signal to dnsProxy after loading the page
    #if proxyPID != 0:
    #    os.system("sudo kill -SIGUSR1 %d" % proxyPID)
    #    time.sleep(0.5)


def create_measurements_table():
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS measurements (
            id string,
            protocol string,
            server string,
            domain string,
            vantagePoint string,
            timestamp datetime,
            connectEnd integer,
            connectStart integer,
            domComplete integer,
            domContentLoadedEventEnd integer,
            domContentLoadedEventStart integer,
            domInteractive integer,
            domainLookupEnd integer,
            domainLookupStart integer,
            duration integer,
            encodedBodySize integer,
            decodedBodySize integer,
            transferSize integer,
            fetchStart integer,
            loadEventEnd integer,
            loadEventStart integer,
            requestStart integer,
            responseEnd integer,
            responseStart integer,
            secureConnectionStart integer,
            startTime integer,
            firstPaint integer,
            firstContentfulPaint integer,
            nextHopProtocol string,
            cacheWarming integer,
            error string,
            PRIMARY KEY (id)
        );
        """)
    db.commit()


def create_lookups_table():
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS lookups (
                measurement_id string,
                domain string,
                elapsed numeric,
                status string,
                answer string,
                FOREIGN KEY (measurement_id) REFERENCES measurements(id)
            );
            """)
    db.commit()


def create_qlogs_table():
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS qlogs (
                measurement_id string,
                qlog string,
                FOREIGN KEY (measurement_id) REFERENCES measurements(id)
            );
            """)
    db.commit()


def insert_performance(page, performance, timestamp, cache_warming=0, error=''):
    performance['protocol'] = protocol
    performance['server'] = server
    performance['domain'] = page
    performance['timestamp'] = timestamp
    performance['cacheWarming'] = cache_warming
    performance['error'] = error
    performance['vantagePoint'] = vantage_point
    # generate unique ID
    sha = hashlib.md5()
    sha_input = ('' + protocol + server + page + str(cache_warming) + vantage_point + timestamp.strftime("%H:%d"))
    sha.update(sha_input.encode())
    uid = uuid.UUID(sha.hexdigest())
    performance['id'] = str(uid)

    # insert into database
    cursor.execute(f"""
    INSERT INTO measurements VALUES ({(len(measurement_elements) - 1) * '?,'}?);
    """, tuple([performance[m_e] for m_e in measurement_elements]))
    db.commit()

    if protocol == 'quic':
        insert_qlogs(str(uid))
    # insert all domain lookups into second table
    if error == '' and proxyPID != 0:
        insert_lookups(str(uid))


def insert_qlogs(uid):
    with open(f"{dnsproxy_dir}qlogs.txt", "r") as qlogs:
        log = qlogs.read()
        cursor.execute("""
            INSERT INTO qlogs VALUES (?,?);
            """, (uid, log))
        db.commit()
    # remove the qlogs after dumping it into the db
    with open(f"{dnsproxy_dir}qlogs.txt", "w") as qlogs:
        qlogs.write('')


def insert_lookup(uid, domain, elapsed, status, answer):
    cursor.execute("""
    INSERT INTO lookups VALUES (?,?,?,?,?);
    """, (uid, domain, elapsed, status, answer))
    db.commit()


def insert_lookups(uid):
    with open("dnsproxy.log", "r") as logs:
        lines = logs.readlines()
        currently_parsing = ''
        domain = ''
        elapsed = 0.0
        status = ''
        answer = ''

        for line in lines:
            # upon success
            if 'successfully finished exchange' in line:
                if 'tranco-list.eu.' not in line:
                    currently_parsing = 'success'
                    domain = re.search('exchange of ;(.*)IN', line).group(1).rstrip()
                    elapsed = re.search('Elapsed (.*)ms', line)
                    factor = 1.0
                    if elapsed is None:
                        elapsed = re.search('Elapsed (.*)µs', line)
                        factor = 1.0 / 1000.0
                    if elapsed is None:
                        elapsed = re.search('Elapsed (.*)s', line)
                        factor = 1000.0
                    elapsed = float(elapsed.group(1)) * factor
            # upon failure
            elif 'failed to exchange' in line:
                currently_parsing = 'failure'
                domain = re.search('failed to exchange ;(.*)IN', line).group(1).rstrip()
                answer = re.search('Cause: (.*)', line).group(1).rstrip()
                elapsed = re.search('in (.*)ms\\.', line)
                factor = 1.0
                if elapsed is None:
                    elapsed = re.search('in (.*)µs\\.', line)
                    factor = 1.0 / 1000.0
                if elapsed is None:
                    elapsed = re.search('in (.*)s\\.', line)
                    factor = 1000.0
                elapsed = float(elapsed.group(1)) * factor
            elif currently_parsing == '':
                pass
            elif ', status: ' in line:
                status = re.search(', status: (.*),', line).group(1)
                # if failure the parsing stops here, else we wait for the answer section
                if currently_parsing == 'failure':
                    insert_lookup(uid, domain, elapsed, status, answer)
                    currently_parsing = ''
            elif ';; ANSWER SECTION:' in line:
                currently_parsing = 'answer'
                answer = ''
            elif currently_parsing == 'answer':
                # in this case we finished parsing the answer section
                if line.rstrip() == '':
                    insert_lookup(uid, domain, elapsed, status, answer)
                    currently_parsing = ''
                else:
                    answer += ','.join(line.split())
                    answer += '|'
    # remove the log after parsing it
    with open("dnsproxy.log", "w") as logs:
        logs.write('')



#create_measurements_table()
#create_lookups_table()
#create_qlogs_table()
for p in pages:
    ## cache warming
    #print(f'{p}: cache warming')
    #perform_page_load(p, 1)
    # performance measurement
    print(f'{p}: measuring')
    perform_page_load(p)

#db.close()
