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
from urllib import parse

dnsproxy_dir = "/home/ubuntu/dnsproxy/"


pages = ["aqz-KE-bpKQ"]


# performance elements to extract
measurement_elements_iframe_api = (
    "time",
    "event_type",
    "buffer_perc",
    "curr_play_time",
    "video_dur",
    "current_quality",
    "available_qualities",
    "msm_id"
)


iframe_api_elements = {
    "time": "float",
    "event_type": "string",
    "buffer_perc": "float",
    "curr_play_time": "float",
    "video_dur": "float",
    "current_quality": "string",
    "available_qualities": "string",
}


measurement_elements_nerd_stats = (
    "time",
    "curr_play_time",
    "bandwidth_kbps",
    "buffer_health_seconds",
    "codecs",
    "dims_and_frames",
    "resolution",
    "network_activity_bytes",
    "msm_id"
)

nerd_stats_elements = {
    "time": "float",
    'curr_play_time': "string",
    "bandwidth_kbps": "string",
    "buffer_health_seconds": "string",
    "codecs": "string",
    "dims_and_frames": "string",
    "resolution": "string",
    "network_activity_bytes": "string",
    "msm_id": "string"
}


measurement_elements_resouce_timing = (
    'connectEnd',
    'connectStart',
    'decodedBodySize',
    'domainLookupEnd',
    'domainLookupStart',
    'duration',
    'encodedBodySize',
    'entryType',
    'fetchStart',
    'initiatorType',
    'name',
    'nextHopProtocol',
    'requestStart',
    'responseEnd',
    'responseStart',
    'secureConnectionStart',
    'startTime',
    'transferSize',
    "msm_id"
)

resource_timing_elements = {
    'connectEnd': 'float',
    'connectStart': 'float',
    'decodedBodySize': 'int',
    'domainLookupEnd': 'float',
    'domainLookupStart': 'float',
    'duration': 'float',
    'encodedBodySize': 'int',
    'entryType': 'string',
    'fetchStart': 'float',
    'initiatorType': 'string',
    'name': 'string',
    'nextHopProtocol': 'string',
    #    'redirectEnd': 'int',
    #    'redirectStart': 'int',
    'requestStart': 'float',
    'responseEnd': 'float',
    'responseStart': 'float',
    'secureConnectionStart': 'float',
    #    'serverTiming': 'list',
    'startTime': 'float',
    'transferSize': 'int',
    #    'workerStart': 'int',
    #    'workerTiming': 'list'
    "msm_id": "string"
}

relevant_resource_timing_keys = ['connectEnd', 'connectStart',
                                 'decodedBodySize',
                                 'domainLookupEnd', 'domainLookupStart',
                                 'duration',
                                 'encodedBodySize',
                                 'entryType',
                                 'fetchStart',
                                 'initiatorType',
                                 'name',
                                 'nextHopProtocol',
                                 'requestStart', 'responseEnd', 'responseStart',
                                 'secureConnectionStart',
                                 'startTime',
                                 'transferSize']


# create db
db = sqlite3.connect("web-performance-youtube.db")
cursor = db.cursor()

# retrieve input params
try:
    protocol = sys.argv[1]
    protocols = ["tls", "https", "quic", "tcp", "udp"]
    if protocol not in protocols:
        print('protocol should be one of these: '+str(protocols))
        sys.exit(1)
    server = sys.argv[2]
    proxyPID = int(sys.argv[3])
    browser = sys.argv[4]
    vp_dict = {
        "compute-1": "US East",
        "ap-northeast-3": "Asia Pacific Northeast",
        "af-south-1": "Africa South",
        "eu-central-1": "Europe Central",
        "ap-southeast-2": "Asia Pacific Southeast",
        "us-west-1": "US West",
        "sa-east-1": "South America East",
    }
    vantage_point = vp_dict.get(sys.argv[5], "")
    width = int(sys.argv[6])
    height = int(sys.argv[7])
    suggested_quality = sys.argv[8]
    res_list = ['auto', 'tiny', 'small', 'medium', 'large',
                'hd720', 'hd1080', 'highres', 'hd1440', 'hd2160']
    if suggested_quality not in res_list:
        print('suggested resolution should be one of these: '+str(res_list))
        sys.exit(1)
    start_seconds = int(sys.argv[9])
    play_duration_seconds = int(sys.argv[10])
    pages = sys.argv[11:]
except IndexError:
    print(
        'Input params incomplete, always required: \nprotocol, \nserver, \ndnsproxyPID (set to 0 if not using dnsproxy), \nbrowser (ignored, always chrome), \nvantage point (any string, cannot be empty), \niframe width, iframe height, \nsuggested video quality (e.g. "auto"), \nstart video at X seconds, \nplay Y seconds of video (negative for full playback), \nvideo IDs to play'
    )
    sys.exit(1)


browser = "chrome"
# Chrome options
# chrome_options = chromeOptions()
# chrome_options.add_argument("--no-sandbox")
# chrome_options.add_argument('--headless')
# chrome_options.add_argument("--disable-dev-shm-usage")
# # chrome_options.add_argument('--media-cache-size=2147483647') -> does not affect how much youtube pre-buffers
# # disable cross origin stuff that chrome imposes on us -- https://stackoverflow.com/questions/35432749/disable-web-security-in-chrome-48
# # iframes are super locked down and these don't actually do anything for accessin iframe specific things -- https://stackoverflow.com/questions/25098021/securityerror-blocked-a-frame-with-origin-from-accessing-a-cross-origin-frame
# # chrome_options.add_argument("--disable-site-isolation-trials")
# # chrome_options.add_argument("--user-data-dir=/tmp/temporary-chrome-profile-dir")
# # chrome_options.add_argument("--disable-features=IsolateOrigins,site-per-process")
# # chrome_options.add_argument("--disable-web-security")
# # chrome_options.add_argument("--allow-file-access-from-files")
# # avoid having to start the video muted due to chrome autoplay policies
# chrome_options.add_argument("--autoplay-policy=no-user-gesture-required")
# chrome_options.add_argument('--disable-http-cache')
# #doesnt work...
# #chrome_options.add_argument("--origin-to-force-quic-on=*.youtube.com:443 *.youtube.com:80 *.googlevideo.com:443 *.googlevideo.com:80")




def create_driver():
    if browser == "chrome":
        chrome_options = chromeOptions()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument('--headless')
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument(
            "--autoplay-policy=no-user-gesture-required")
        chrome_options.add_argument('--disable-http-cache')
        # force http/3 for the actual measurement
        # otherwise the initial requests will be http/1.1
        # could not get it working
        # if cacheWarming == 0:
        #     # comma separated list, doesnt accept wildcards, quotation marks required if more than one
        #     chrome_options.add_argument(
        #         '--origin-to-force-quic-on="'+google_video_url+'"')
        return webdriver.Chrome(options=chrome_options)


# By default, WebDriverWait calls the ExpectedCondition every 500 milliseconds until it returns success.
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
    play_duration_seconds=0,
    video_id="YE7VzlLtp-4",
):
    # https://stackoverflow.com/a/58068828
    script_get_nerdstats = 'return {"time": (performance.now() + performance.timeOrigin), "media_reference_time": arguments[0].getMediaReferenceTime(), "nerdstats": arguments[0].getStatsForNerds()};'

    # 'video = document.getElementsByTagName("video")[0]; return video.duration;'
    script_get_video_duration = "return getVideoDuration();"
    script_get_video_ended = 'return arguments[0].ended;'

    script_get_video_buffered_wrong = 'video = document.getElementsByTagName("video")[0]; return video.buffered.end(0) - video.buffered.start(0);'
    # https://github.com/lsinfo3/yomo-docker/blob/master/files/pluginAsJSFormated.js
    script_get_video_buffered = """
        video = document.getElementsByTagName("video")[0];
        var currentTime = video.currentTime;
		var buffLen = video.buffered.length;
		var availablePlaybackTime = video.buffered.end(buffLen-1);
		var bufferedTime = availablePlaybackTime - currentTime;
        return bufferedTime;
    """

    # this only works on the main youtube page, not in iframes
    script_get_manifest = "return ytInitialPlayerResponse"

    # https://developer.mozilla.org/en-US/docs/Web/API/Resource_Timing_API/Using_the_Resource_Timing_API
    script_get_resource_timing_buffer_level = 'return performance.getEntriesByType("resource").length;'
    script_get_resource_timing = 'return performance.getEntriesByType("resource");'

    # https://w3c.github.io/navigation-timing/
    web_perf_script = 'return performance.getEntriesByType("navigation")[0]["loadEventEnd"];'
    # https://developer.mozilla.org/en-US/docs/Web/API/Navigation_timing_API#examples
    # less accurate in chrome due to absolute timestamps
    page_load_script = """const perfData = window.performance.timing; return perfData.loadEventEnd - perfData.navigationStart;"""

    # document.getElementById("movie_player").getMediaReferenceTime() -> current playback time in seconds
    # getProgressState()['loaded'] - getProgressState()['current'] returns buffered amount
    # getAdState() -> might need this for more general video playback?

    nerdstats_log = []
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
            page_load_time = driver.execute_script(web_perf_script)
            # yt_iframe_api_video_duration_sec = driver.execute_script(
            #    script_get_video_duration
            # )
            # either start video here or later, either way we appear to be missing the initial buffer in the resource timing api
            driver.execute_script("startVideoAndLog()")
            # youtube_player_iframe = driver.find_element(By.ID, 'player')
            try:
                print("switching to yt iframe")
                driver.switch_to.frame(youtube_player_iframe)

                # https://www.w3.org/TR/hr-time-2/
                resource_time_start_adjusted_timestamp = driver.execute_script(
                    'return performance.timeOrigin;')
                resource_timings = []  # [resource_time_start_adjusted_timestamp]
                resource_timings.extend(
                    driver.execute_script(script_get_resource_timing))
                last_len_resource_timings_buffer = len(resource_timings)-1
                buffer_was_reset = False

                resource_timings_buffer_limit = 300
                driver.execute_script(
                    f'performance.setResourceTimingBufferSize({resource_timings_buffer_limit});')
                # print(driver.execute_script(script_get_resource_timing))
                # driver.switch_to.frame('player')
                # driver.switch_to.default_content()
                # driver.find_element(By.TAG_NAME, "video").get_attribute("src")

                tmp_timings = driver.execute_script(script_get_resource_timing)
                if len(tmp_timings) > last_len_resource_timings_buffer:
                    resource_timings.extend(tmp_timings)
                    # print(
                    #    'timings api returned more resources after setting buffer size: '+str(len(tmp_timings)))
                    last_len_resource_timings_buffer = len(tmp_timings)
                # this wait also results in script_get_video_buffered running without crashing selenium
                # this also clears the resource timing buffer for some reason
                wait = WebDriverWait(driver, 3)
                video_duration_seconds, resources_from_waiting_for_video = wait.until(
                    video_element_has_duration_attribute()
                )
                tmp_timings = driver.execute_script(script_get_resource_timing)
                if len(tmp_timings) > last_len_resource_timings_buffer:
                    resource_timings.extend(tmp_timings)
                    # print(
                    #    'timings api returned more resources after waiting for video element to have a duration: '+str(len(tmp_timings)))
                    last_len_resource_timings_buffer = len(tmp_timings)
                if len(tmp_timings) < last_len_resource_timings_buffer:
                    #print('buffer was reset')
                    buffer_was_reset = True
                if play_duration_seconds <= 0:
                    play_duration_seconds = int(
                        float(video_duration_seconds)) + 20

                # get movie player element in selenium to pass into execute script calls
                nerd_stats_movie_player = driver.find_element(
                    By.ID, "movie_player")
                html_video_player = driver.find_element(By.TAG_NAME, "video")

                # logging loop until the measurement is finished
                while play_duration_seconds >= 1:
                    if buffer_was_reset == False:
                        tmp_timings = driver.execute_script(
                            script_get_resource_timing)
                        if len(tmp_timings) > last_len_resource_timings_buffer:
                            resource_timings.extend(tmp_timings)
                            # print(
                            #    'timings api returned more resources inside logging loop: '+str(len(tmp_timings)))
                            last_len_resource_timings_buffer = len(tmp_timings)
                        if len(tmp_timings) < last_len_resource_timings_buffer:
                            #print('buffer was reset')
                            buffer_was_reset = True
                    # print("fetching nerdstats, estimated remaining seconds " +
                    #      str(play_duration_seconds))
                    nerdstats = driver.execute_script(
                        script_get_nerdstats, nerd_stats_movie_player)

                    resource_timings_buffer = driver.execute_script(
                        script_get_resource_timing_buffer_level)
                    #print(str(resource_timings_buffer) + " resources timed")
                    if resource_timings_buffer >= (resource_timings_buffer_limit - 50):
                        resource_timings_buffer_limit = resource_timings_buffer_limit + 100
                        driver.execute_script(
                            f'performance.setResourceTimingBufferSize({resource_timings_buffer_limit});')
                    ###nerdstats_log.append({"timestamp":time.time(),"nerd_stats": nerdstats})
                    nerdstats_log.append(nerdstats)
                    # print(driver.execute_script(script_get_nerdstats_buffer))
                    # print(driver.execute_script(script_get_video_buffered))
                    if driver.execute_script(script_get_video_ended, html_video_player):
                        break
                    play_duration_seconds = play_duration_seconds - 0.5
                    time.sleep(0.5)
                resource_timings.extend(
                    driver.execute_script(script_get_resource_timing))
                resource_timings.extend(resources_from_waiting_for_video)

                time_sync_py = time.time_ns()
                time_sync_js = driver.execute_script(
                    "return performance.now() + performance.timeOrigin;")
                driver.switch_to.default_content()
                print("switched out of iframe")
                event_log = driver.execute_script("return getEventLog();")
                ###driver.execute_script('return window.eventLog')
                return (event_log, nerdstats_log, resource_timings, time_sync_py, time_sync_js, resource_time_start_adjusted_timestamp, page_load_time)
            except selenium.common.exceptions.WebDriverException as e:
                print(
                    "failed switching selenium focus to youtube iframe or monitoring loop")
                print(str(e))
                driver.get_screenshot_as_file(
                    protocol+'-'+server+'-'+video_id+'-'+vantage_point+'-'+datetime.now().strftime("%y-%m-%d-%H:%M:%S")+'.png')
                return ([{"error": "failed switching selenium focus to youtube iframe or monitoring loop ### " + str(e)}],
                        [], [], -1, -1, -1, -1)
        except selenium.common.exceptions.WebDriverException as e:
            print("failed loading player")
            driver.get_screenshot_as_file(protocol+'-'+server+'-'+video_id+'-' +
                                          vantage_point+'-'+datetime.now().strftime("%y-%m-%d-%H:%M:%S")+'.png')
            return ([{"error": "failed loading player ### " + str(e)}], [], [], -1, -1, -1, -1)
    except selenium.common.exceptions.WebDriverException as e:
        print("failed driver.get()")
        print(str(e))
        return ([{"error": "failed driver.get() ### " + str(e)}], [], [], -1, -1, -1, -1)

def load_youtube_empty_iframe_cachewarming(driver):
    web_perf_script = 'return performance.getEntriesByType("navigation")[0]["loadEventEnd"];'
    try:
        driver.set_page_load_timeout(15)
        driver.get("http://localhost:22222/youtube_iframe.html")
        while driver.execute_script("return document.readyState;") != "complete":
            time.sleep(1)
        try:
            wait = WebDriverWait(driver, 15)
            wait.until(
                EC.visibility_of_element_located((By.ID, "player"))
            )
            time.sleep(1)
            page_load_time = driver.execute_script(web_perf_script)
            return [{"successful_cache_warming": "cache warming successful ###"}], page_load_time
        except selenium.common.exceptions.WebDriverException as e:
            print("failed loading player")
            driver.get_screenshot_as_file('cache-warmup-failed-'+protocol+'-'+server+'-'+'-' +
                                          vantage_point+'-'+datetime.now().strftime("%y-%m-%d-%H:%M:%S")+'.png')
            return [{"error": "failed loading player for cache warming ### " + str(e)}]
    except selenium.common.exceptions.WebDriverException as e:
        print("failed driver.get()")
        return [{"error": "failed driver.get() for cache warming ### " + str(e)}]


def perform_page_load(page, cache_warming=0):
    driver = create_driver()
    # >>timestamp<< is the measurement itself, >>time<< is the time a callback/log event happened
    timestamp = datetime.now()
    # performance_metrics = get_page_performance_metrics(driver, page)
    # nerd_stats seems to be ~20 seconds ahead of event_log on my local machine, both log in 1s intervals so the delta should not be that large
    if cache_warming == 1:
        event_log, page_load_time = load_youtube_empty_iframe_cachewarming(driver)
        time_sync_py = -1
        time_sync_js = -1
        resource_time_origin = -1
    else:
        event_log, nerd_stats, resource_timings, time_sync_py, time_sync_js, resource_time_origin, page_load_time = load_youtube(
            driver,
            fwidth=width,
            fheight=height,
            suggested_quality=suggested_quality,
            start_seconds=start_seconds,
            play_duration_seconds=play_duration_seconds,
            video_id=page,
        )
    #if "error" in event_log[0]:
    #    driver.get_screenshot_as_file('msm-failed-'+protocol+'-'+server+'-'+page+'-'+str(
    #        cache_warming)+'-'+vantage_point+'-'+timestamp.strftime("%y-%m-%d-%H:%M:%S")+'.png')
    driver.quit()

    # generate unique ID for the overall measurement
    sha = hashlib.md5()
    sha_input = ('' + protocol + server + page + str(cache_warming) +
                 vantage_point + timestamp.strftime("%y-%m-%d-%H:%M:%S"))
    sha.update(sha_input.encode())
    uid = uuid.UUID(sha.hexdigest())
    if protocol == "quic":
        insert_qlogs(str(uid))
    # insert all domain lookups into second table (originally only if there are no errors, changed it to always do it)
    if proxyPID != 0:
        insert_lookups(str(uid))

    # insert into overall measurements table that also tries to track time drift between python and javascript
    error = ""
    if "error" in event_log[0]:
        error = event_log[0]["error"]

    insert_measurement(str(uid), time_sync_py, time_sync_js,
                       resource_time_origin, page, timestamp, error, cache_warming, page_load_time)

    if "successful_cache_warming" in event_log[0]:
        print("cache warming successful")

    if "error" not in event_log[0] and "successful_cache_warming" not in event_log[0]:
        print("actual measurement successful")
        # youtube iframe api event log
        # add missing keys in their correct format (most basic types, other sqlite types are derived from this anyway)
        for event in event_log:
            for key in iframe_api_elements.keys():
                if key not in event.keys():
                    # fix missing items because not every log event contains all the columns (for now)
                    typelookup = iframe_api_elements[key]
                    if typelookup == "string":
                        event[key] = "-1"
                    if typelookup == "float":
                        event[key] = -1.0
                    if typelookup == "int":
                        event[key] = -1
            event["available_qualities"] = str(event["available_qualities"])
            insert_event(event, str(uid))

        # nerd stats logging
        for item in parse_nerd_stats(nerd_stats):
            insert_nerdstats(item, str(uid))

        for item in parse_resource_timings(resource_timings):
            insert_resources(item, str(uid))



    # send restart signal to dnsProxy after loading the page
    if proxyPID != 0:
        os.system("sudo kill -SIGUSR1 %d" % proxyPID)
        time.sleep(0.5)



def parse_nerd_stats(nerd_stats):
    nerd_stats_log = []
    for item in nerd_stats:
        nerd_stats_log.append(
            {
                "time": item["time"],
                "curr_play_time": str(item["media_reference_time"]),
                "bandwidth_kbps": item["nerdstats"]["bandwidth_kbps"],
                "buffer_health_seconds": item["nerdstats"]["buffer_health_seconds"],
                "codecs": item["nerdstats"]["codecs"],
                "dims_and_frames": item["nerdstats"]["dims_and_frames"],
                "resolution": item["nerdstats"]["resolution"],
                "network_activity_bytes": item["nerdstats"]["network_activity_bytes"],
            }
        )
    return nerd_stats_log


def parse_resource_timings(resource_timings):
    #resource_time_start_adjusted_timestamp = resource_timings.pop(0)
    # only look at resources that are actual video or audio requests
    resource_timings = [
        timing for timing in resource_timings if "googlevideo.com/videoplayback" in timing['name']]
    # for timing in resource_timings:
    #    # (requestStart-responseEnd) + some delay (decoding?) = duration
    #    # decodedBodySize -> bytes fetched (range in name)
    #    # all times are in milliseconds
    #    # https://developer.mozilla.org/en-US/docs/Web/API/DOMHighResTimeStamp
    #    # translating to unix timestamp in ms removes precision sadly
    #    for time_key in ['connectEnd', 'connectStart', 'domainLookupEnd', 'domainLookupStart', 'fetchStart', 'requestStart', 'responseEnd', 'responseStart', 'secureConnectionStart', 'startTime', ]:
    #        timing[time_key] = timing[time_key] + \
    #            resource_time_start_adjusted_timestamp
    # remove keys that are static or always empty
    resource_timings = [{k: v for k, v in timing_dict.items(
    ) if k in relevant_resource_timing_keys} for timing_dict in resource_timings]
    # remove duplicates, all items inside the dicts should be hashable
    return [dict(t) for t in {tuple(d.items()) for d in resource_timings}]





def create_iframe_api_table():
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS iframe_api (
            time double,
            event_type string,
            buffer_perc double,
            curr_play_time double,
            video_dur double,
            current_quality string,
            available_qualities string,
            msm_id string,
            FOREIGN KEY (msm_id) REFERENCES measurements(msm_id)
        );
        """
    )
    db.commit()


def create_nerd_stats_table():
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS nerd_stats (
            time double,
            curr_play_time string,
            bandwidth_kbps string,
            buffer_health_seconds string,
            codecs string,
            dims_and_frames string,
            resolution string,
            network_activity_bytes string,
            msm_id string,
            FOREIGN KEY (msm_id) REFERENCES measurements(msm_id)
        );
        """
    )
    db.commit()


def create_page_resources_table():
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS page_resources (
            connectEnd double,
            connectStart double,
            decodedBodySize integer,
            domainLookupEnd double,
            domainLookupStart double,
            duration float,
            encodedBodySize integer, 
            entryType string,
            fetchStart double,
            initiatorType string,
            name string,
            nextHopProtocol string,
            requestStart double,
            responseEnd double,
            responseStart double,
            secureConnectionStart double,
            startTime double,
            transferSize integer,
            msm_id string,
            FOREIGN KEY (msm_id) REFERENCES measurements(msm_id)
        );
        """
    )
    db.commit()


def create_lookups_table():
    cursor.execute(
        """
            CREATE TABLE IF NOT EXISTS lookups (
                measurement_id string,
                domain string,
                elapsed numeric,
                status string,
                answer string,
                FOREIGN KEY (measurement_id) REFERENCES measurements(msm_id)
            );
            """
    )
    db.commit()


def create_qlogs_table():
    cursor.execute(
        """
            CREATE TABLE IF NOT EXISTS qlogs (
                measurement_id string,
                qlog string,
                FOREIGN KEY (measurement_id) REFERENCES measurements(msm_id)
            );
            """
    )
    db.commit()


def create_measurements_table():
    cursor.execute(
        """
            CREATE TABLE IF NOT EXISTS measurements (
                msm_id string,
                py_time datetime,
                js_time datetime,
                resource_time_origin datetime,
                protocol string,
                server string,
                domain string,
                vantagePoint string,
                timestamp datetime,
                suggested_quality string,
                player_width integer,
                player_height integer,
                start_time integer,
                play_time integer,
                video_ids string,
                cacheWarming integer,
                page_load_time double,
                error string,
                PRIMARY KEY (msm_id)
            );
            """
    )
    db.commit()


def insert_measurement(msm_id, py_time, js_time, resource_time_origin, page, timestamp, error, cache_warming, page_load_time):
    cursor.execute("INSERT INTO measurements VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);", (msm_id, py_time, js_time,
                   resource_time_origin, protocol, server, page, vantage_point, timestamp, suggested_quality, width, height, start_seconds, play_duration_seconds, ", ".join(pages), cache_warming, page_load_time, error))
    db.commit()


def insert_event(performance, msm_id):
    performance["msm_id"] = msm_id

    # insert into database
    cursor.execute(
        f"""
    INSERT INTO iframe_api VALUES ({(len(measurement_elements_iframe_api) - 1) * '?,'}?);
    """,
        tuple([performance[m_e] for m_e in measurement_elements_iframe_api]),
    )
    db.commit()


def insert_nerdstats(performance, msm_id):
    performance["msm_id"] = msm_id

    # insert into database
    cursor.execute(
        f"""
    INSERT INTO nerd_stats VALUES ({(len(measurement_elements_nerd_stats) - 1) * '?,'}?);
    """,
        tuple([performance[m_e] for m_e in measurement_elements_nerd_stats]),
    )
    db.commit()


def insert_resources(performance, msm_id):
    performance["msm_id"] = msm_id

    # insert into database
    cursor.execute(
        f"""
    INSERT INTO page_resources VALUES ({(len(measurement_elements_resouce_timing) - 1) * '?,'}?);
    """,
        tuple([performance[m_e]
              for m_e in measurement_elements_resouce_timing]),
    )
    db.commit()


def insert_qlogs(uid):
    with open(f"{dnsproxy_dir}qlogs.txt", "r") as qlogs:
        log = qlogs.read()
        cursor.execute(
            """
            INSERT INTO qlogs VALUES (?,?);
            """,
            (uid, log),
        )
        db.commit()
    # remove the qlogs after dumping it into the db
    with open(f"{dnsproxy_dir}qlogs.txt", "w") as qlogs:
        qlogs.write("")


def insert_lookup(uid, domain, elapsed, status, answer):
    cursor.execute(
        """
    INSERT INTO lookups VALUES (?,?,?,?,?);
    """,
        (uid, domain, elapsed, status, answer),
    )
    db.commit()


def insert_lookups(uid):
    with open("dnsproxy.log", "r") as logs:
        lines = logs.readlines()
        currently_parsing = ""
        domain = ""
        elapsed = 0.0
        status = ""
        answer = ""

        for line in lines:
            # upon success
            if "successfully finished exchange" in line:
                currently_parsing = "success"
                domain = re.search("exchange of ;(.*)IN",
                                    line).group(1).rstrip()
                elapsed = re.search("Elapsed (.*)ms", line)
                factor = 1.0
                if elapsed is None:
                    elapsed = re.search("Elapsed (.*)µs", line)
                    factor = 1.0 / 1000.0
                if elapsed is None:
                    elapsed = re.search("Elapsed (.*)s", line)
                    factor = 1000.0
                elapsed = float(elapsed.group(1)) * factor
            # upon failure
            elif "failed to exchange" in line:
                currently_parsing = "failure"
                domain = re.search(
                    "failed to exchange ;(.*)IN", line).group(1).rstrip()
                answer = re.search("Cause: (.*)", line).group(1).rstrip()
                elapsed = re.search("in (.*)ms\\.", line)
                factor = 1.0
                if elapsed is None:
                    elapsed = re.search("in (.*)µs\\.", line)
                    factor = 1.0 / 1000.0
                if elapsed is None:
                    elapsed = re.search("in (.*)s\\.", line)
                    factor = 1000.0
                elapsed = float(elapsed.group(1)) * factor
            elif currently_parsing == "":
                pass
            elif ", status: " in line:
                status = re.search(", status: (.*),", line).group(1)
                # if failure the parsing stops here, else we wait for the answer section
                if currently_parsing == "failure":
                    insert_lookup(uid, domain, elapsed, status, answer)
                    currently_parsing = ""
            elif ";; ANSWER SECTION:" in line:
                currently_parsing = "answer"
                answer = ""
            elif currently_parsing == "answer":
                # in this case we finished parsing the answer section
                if line.rstrip() == "":
                    insert_lookup(uid, domain, elapsed, status, answer)
                    currently_parsing = ""
                else:
                    answer += ",".join(line.split())
                    answer += "|"
    # remove the log after parsing it
    with open("dnsproxy.log", "w") as logs:
        logs.write("")


create_measurements_table()
create_iframe_api_table()
create_nerd_stats_table()
create_page_resources_table()
create_lookups_table()
create_qlogs_table()
for p in pages:
    # cache warming
    print(f"{p}: cache warming")
    perform_page_load(p, 1)
    # performance measurement
    print(f"{p}: measuring")
    perform_page_load(p)

db.close()
