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
measurement_elements = (
    "id",
    "protocol",
    "server",
    "domain",
    "vantagePoint",
    "timestamp",
    "time",
    "event_type",
    "buffer_perc",
    "curr_play_time",
    "video_dur",
    "current_quality",
    "available_qualities",
    "bandwidth_kbps",
    "buffer_health_seconds",
    "codecs",
    "dims_and_frames",
    "resolution",
    "network_activity_bytes",
    "cacheWarming",
    "error",
)


iframe_api_elements = {
    "event_type": "string",
    "buffer_perc": "float",
    "curr_play_time": "float",
    "video_dur": "float",
    "current_quality": "string",
    "available_qualities": "string",
}
nerd_stats_elements = {
    "bandwidth_kbps": "string",
    "buffer_health_seconds": "string",
    "codecs": "string",
    "dims_and_frames": "string",
    "resolution": "string",
    "network_activity_bytes": "string",
}

# create db
db = sqlite3.connect("web-performance.db")
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
    res_list = ['auto', 'tiny', 'small', 'medium', 'large', 'hd720', 'hd1080', 'highres', 'hd1440', 'hd2160']
    if suggested_quality not in res_list:
        print('suggested resolution should be one of these: '+str(res_list))
        sys.exit(1)
    start_seconds = int(sys.argv[9])
    play_duration_seconds = int(sys.argv[10])
    pages = sys.argv[11:]
    print(pages)
except IndexError:
    print(
        'Input params incomplete, always required: \nprotocol, \nserver, \ndnsproxyPID (set to 0 if not using dnsproxy), \nbrowser (ignored, always chrome), \nvantage point, \niframe width, iframe height, \nsuggested video quality (e.g. "auto"), \nstart video at X seconds, \nplay Y seconds of video (negative for full playback), \nvideo IDs to play'
    )
    sys.exit(1)

# fwidth=640, fheight=360, suggested_quality="default", start_seconds=0, play_duration_seconds=0, video_id="YE7VzlLtp-4"


browser = "chrome"
# Chrome options
chrome_options = chromeOptions()
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument('--headless')
chrome_options.add_argument("--disable-dev-shm-usage")
# chrome_options.add_argument('--media-cache-size=2147483647') -> does not affect how much youtube pre-buffers
# disable cross origin stuff that chrome imposes on us -- https://stackoverflow.com/questions/35432749/disable-web-security-in-chrome-48
# iframes are super locked down and these don't actually do anything for accessin iframe specific things -- https://stackoverflow.com/questions/25098021/securityerror-blocked-a-frame-with-origin-from-accessing-a-cross-origin-frame
# chrome_options.add_argument("--disable-site-isolation-trials")
# chrome_options.add_argument("--user-data-dir=/tmp/temporary-chrome-profile-dir")
# chrome_options.add_argument("--disable-features=IsolateOrigins,site-per-process")
# chrome_options.add_argument("--disable-web-security")
# chrome_options.add_argument("--allow-file-access-from-files")
# avoid having to start the video muted due to chrome autoplay policies
chrome_options.add_argument("--autoplay-policy=no-user-gesture-required")


def timing_interceptor(request, response):  # A response interceptor takes two args
    if "googlevideo.com/videoplayback" in request.url:
        # if request.url == 'https://server.com/some/path':
        response.headers['Timing-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Origin'] = '*'


def create_driver():
    if browser == "chrome":
        return webdriver.Chrome(
            # , seleniumwire_options={"enable_har": True}
            options=chrome_options
        )
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
        driver.get(f"https://{page}")
        return driver.execute_script(script)
    except selenium.common.exceptions.WebDriverException as e:
        return {"error": str(e)}


class video_element_has_duration_attribute(object):
    """An expectation for checking that a video element has a duration that is not NaN.

    locator - used to find the element
    returns the WebElement once it has the particular css class
    """

    def __call__(self, driver):
        # Finding the referenced element
        try:
            print(driver.execute_script(
                'return performance.getEntriesByType("resource").length;'))
            element = driver.find_element(By.TAG_NAME, "video")
            if element.get_attribute("duration") != "NaN":
                return element.get_attribute("duration")
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
    script_get_nerdstats = """
        var currentTime = new Date().getTime();
        iframe_player = document.getElementById("movie_player")
        return {"time":currentTime, "nerdstats":iframe_player.getStatsForNerds()};
        """
    script_get_nerdstats_buffer = 'return document.getElementById("movie_player").getStatsForNerds().buffer_health_seconds;'

    script_get_movie_player_playback_time = (
        'return document.getElementById("movie_player").getMediaReferenceTime();'
    )

    # 'video = document.getElementsByTagName("video")[0]; return video.duration;'
    script_get_video_duration = "return getVideoDuration()"
    script_get_video_ended = """
        video = document.getElementsByTagName("video")[0];
        return video.ended
    """

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

    # this only works on the main youtube page, no in iframes
    script_get_manifest = "return ytInitialPlayerResponse"

    # https://developer.mozilla.org/en-US/docs/Web/API/Resource_Timing_API/Using_the_Resource_Timing_API
    script_get_resource_timing_buffer_level = 'return performance.getEntriesByType("resource").length;'
    script_get_resource_timing = 'return performance.getEntriesByType("resource");'

    # document.getElementById("movie_player").getMediaReferenceTime() -> current playback time in seconds
    # getProgressState()['loaded'] - getProgressState()['current'] returns buffered amount
    # getAdState() -> might need this for more general video playback?

    nerdstats_log = []
    try:
        driver.set_page_load_timeout(30)
        driver.get("http://localhost:22222/youtube_iframe.html")
        while driver.execute_script("return document.readyState") != "complete":
            time.sleep(1)

        try:
            wait = WebDriverWait(driver, 10000)
            youtube_player_iframe = wait.until(
                EC.visibility_of_element_located((By.ID, "player"))
            )
            driver.execute_script(f"setPlayerSize({fwidth},{fheight});")
            driver.execute_script(
                f'setVideo("{video_id}",{start_seconds},"{suggested_quality}");'
            )
            time.sleep(1)
            yt_iframe_api_video_duration_sec = driver.execute_script(
                script_get_video_duration
            )
            # either start video here or later, either way we appear to be missing the initial buffer in the resource timing api
            driver.execute_script("startVideoAndLog()")
            # youtube_player_iframe = driver.find_element(By.ID, 'player')
            try:
                print("switching to yt iframe")
                driver.switch_to.frame(youtube_player_iframe)

                # TODO:look up whether the time resolution of date now and performance now are the same in chrome (they should be in firefox)
                resource_time_start_adjusted_timestamp = driver.execute_script(
                    'return Date.now()-performance.now();')
                resource_timings = [resource_time_start_adjusted_timestamp]
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
                ###driver.find_element(By.TAG_NAME, "video").get_attribute("src")

                tmp_timings = driver.execute_script(script_get_resource_timing)
                if len(tmp_timings) > last_len_resource_timings_buffer:
                    resource_timings.extend(tmp_timings)
                    print(
                        'timings api returned more resources after setting buffer size: '+str(len(tmp_timings)))
                    last_len_resource_timings_buffer = len(tmp_timings)
                # this wait also results in script_get_video_buffered running without crashing selenium
                # this also clears the resource timing buffer for some reason
                wait = WebDriverWait(driver, 3)
                video_duration_seconds = wait.until(
                    video_element_has_duration_attribute()
                )
                tmp_timings = driver.execute_script(script_get_resource_timing)
                if len(tmp_timings) > last_len_resource_timings_buffer:
                    resource_timings.extend(tmp_timings)
                    print(
                        'timings api returned more resources after waiting for video element to have a duration: '+str(len(tmp_timings)))
                    last_len_resource_timings_buffer = len(tmp_timings)
                if len(tmp_timings) < last_len_resource_timings_buffer:
                    print('buffer was reset')
                    buffer_was_reset = True
                if play_duration_seconds <= 0:
                    play_duration_seconds = int(
                        float(video_duration_seconds)) + 20
                while play_duration_seconds >= 0:
                    if buffer_was_reset == False:
                        tmp_timings = driver.execute_script(
                            script_get_resource_timing)
                        if len(tmp_timings) > last_len_resource_timings_buffer:
                            resource_timings.extend(tmp_timings)
                            print(
                                'timings api returned more resources inside logging loop: '+str(len(tmp_timings)))
                            last_len_resource_timings_buffer = len(tmp_timings)
                        if len(tmp_timings) < last_len_resource_timings_buffer:
                            print('buffer was reset')
                            buffer_was_reset = True
                    print("fetching nerdstats, estimated remaining seconds " +
                          str(play_duration_seconds))
                    nerdstats = driver.execute_script(script_get_nerdstats)
                    nerdstats["media_reference_time"] = driver.execute_script(
                        script_get_movie_player_playback_time
                    )
                    resource_timings_buffer = driver.execute_script(
                        script_get_resource_timing_buffer_level)
                    print(str(resource_timings_buffer) + " resources timed")
                    if resource_timings_buffer >= (resource_timings_buffer_limit - 50):
                        resource_timings_buffer_limit = resource_timings_buffer_limit + 100
                        driver.execute_script(
                            f'performance.setResourceTimingBufferSize({resource_timings_buffer_limit});')
                    ###nerdstats_log.append({"timestamp":time.time(),"nerd_stats": nerdstats})
                    nerdstats_log.append(nerdstats)
                    # print(driver.execute_script(script_get_nerdstats_buffer))
                    # print(driver.execute_script(script_get_video_buffered))
                    if driver.execute_script(script_get_video_ended):
                        break
                    play_duration_seconds = play_duration_seconds - 0.5
                    time.sleep(0.5)
                resource_timings.extend(
                    driver.execute_script(script_get_resource_timing))
                print(len(resource_timings))
                driver.switch_to.default_content()
                print("switched out of iframe")
                event_log = driver.execute_script("return getEventLog();")
                ###driver.execute_script('return window.eventLog')
                return (event_log, nerdstats_log, resource_timings)
            except selenium.common.exceptions.WebDriverException as e:
                print(
                    "failed switching selenium focus to youtube iframe or monitoring loop")
                return ([{"error": "failed switching selenium focus to youtube iframe or monitoring loop ### " + str(e)}],
                        [], [])
        except selenium.common.exceptions.WebDriverException as e:
            print("failed loading player")
            return ([{"error": "failed loading player ### " + str(e)}], [], [])
    except selenium.common.exceptions.WebDriverException as e:
        print("failed driver.get()")
        print(str(e))
        return ([{"error": "failed driver.get() ### " + str(e)}], [], [])


def perform_page_load(page, cache_warming=0):
    driver = create_driver()
    #driver.response_interceptor = timing_interceptor
    # driver.scopes = [
    #    '.*googlevideo.*'
    # ]
    # >>timestamp<< is the measurement itself, >>time<< is the time a callback/log event happened
    timestamp = datetime.now()
    # performance_metrics = get_page_performance_metrics(driver, page)
    # nerd_stats seems to be ~20 seconds ahead of event_log on my local machine, both log in 1s intervals so the delta should not be that large
    if cache_warming == 1:
        event_log, nerd_stats, resource_timings = load_youtube(
            driver, play_duration_seconds=3, video_id=page
        )
    else:
        event_log, nerd_stats, resource_timings = load_youtube(
            driver,
            fwidth=width,
            fheight=height,
            suggested_quality=suggested_quality,
            start_seconds=start_seconds,
            play_duration_seconds=play_duration_seconds,
            video_id=page,
        )
    driver.quit()

    resource_time_start_adjusted_timestamp = resource_timings.pop(0)
    # only look at resources that are actual video or audio requests
    resource_timings = [
        timing for timing in resource_timings if "googlevideo.com/videoplayback" in timing['name']]
    for timing in resource_timings:
        # (requestStart-responseEnd) + some delay (decoding?) = duration
        # decodedBodySize -> bytes fetched (range in name)
        # all times are in milliseconds
        # https://developer.mozilla.org/en-US/docs/Web/API/DOMHighResTimeStamp
        # translating to unix timestamp in ms removes precision sadly
        for time_key in ['connectEnd', 'connectStart', 'domainLookupEnd', 'domainLookupStart', 'fetchStart', 'requestStart', 'responseEnd', 'responseStart', 'secureConnectionStart', 'startTime', ]:
            timing[time_key] = timing[time_key] + \
                resource_time_start_adjusted_timestamp
        print(timing['name'])
        print(timing['nextHopProtocol'])
        print(timing['requestStart'])
        print(timing['responseEnd'])
        print(timing['duration'])
        print(timing['decodedBodySize'])
        url_params = dict(parse.parse_qs(parse.urlsplit(timing['name']).query))
        timing['itag'] = url_params['itag'][0]
        timing['rbuf'] = url_params['rbuf'][0]
        timing['range'] = url_params['range'][0]
    relevant_keys = ['connectEnd', 'connectStart',
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
                     'transferSize',
                     'itag',
                     'rbuf',
                     'range']
    # remove keys that are static or always empty
    resource_timings = [{k: v for k, v in timing_dict.items(
    ) if k in relevant_keys} for timing_dict in resource_timings]
    # remove duplicates, all items inside the dicts should be hashable
    resource_timings = [dict(t)
                        for t in {tuple(d.items()) for d in resource_timings}]

    # below code only works when using selenium wire
    # https://www.w3.org/TR/resource-timing-2/
    # If an HTML IFRAME element is included on the page, then only the resource requested by IFRAME src attribute is included as a PerformanceResourceTiming object in the Performance Timeline. Sub-resources requested by the IFRAME document will be included in the IFRAME document's Performance Timeline and not the parent document's Performance Timeline.
    # youtube seems to have an endpoint to get the manifest but they keep restricting access to it
    # -> https://stackoverflow.com/questions/67615278/get-video-info-youtube-endpoint-suddenly-returning-404-not-found
    # on the normal youtube website, ytInitialPlayerResponse is a variable that has all possible itags and their corresponding request URLs
    # however this does not for iframes

    # this does not save timings and the GET requests appear to be missing from the har file for some reason
    # if using selenium wire:
    # fetch http responses for bandwidth stuff
    # for request in driver.requests:
    #    if request.response:
    #        if "googlevideo.com/videoplayback" in request.url:
    #            print(dir(request.response))
    #            print(dir(request))
    #            print(request.url,
    #                request.params,
    #                request.response.status_code,
    #                request.response.headers['Content-Type'],
    #                request.response.headers['Content-Length'],
    #                request.response.date
    #             )
    # print(performance_metrics)
    # json_har = json.loads(driver.har)['log']['entries']
    # video_requests = []

    # for entry in json_har:
    #    if "googlevideo.com/videoplayback" in entry['request']['url']:
    #        print(json_har[len(json_har)-1].keys())
    #        print(json_har[len(json_har)-1]['request'])
    #        print(json_har[len(json_har)-1]['response'])
    #        print(json_har[len(json_har)-1]['timings'])

    if "error" not in event_log[0]:
        for event in parse_nerd_stats(nerd_stats):
            insert_performance(page, event, timestamp,
                               cache_warming=cache_warming)
        # add missing keys in their correct format (most basic types, other sqlite types are derived from this anyway)
        for event in event_log:
            for key in iframe_api_elements.keys():
                if key not in event.keys():
                    typelookup = iframe_api_elements[key]
                    if typelookup == "string":
                        event[key] = "-1"
                    if typelookup == "float":
                        event[key] = -1.0
                    if typelookup == "int":
                        event[key] = -1
            for key in nerd_stats_elements.keys():
                if key not in event.keys():
                    typelookup = nerd_stats_elements[key]
                    if typelookup == "string":
                        event[key] = "-1"
                    if typelookup == "float":
                        event[key] = -1.0
                    if typelookup == "int":
                        event[key] = -1
            event["available_qualities"] = str(event["available_qualities"])
            insert_performance(page, event, timestamp,
                               cache_warming=cache_warming)

    # insert page into database
    # if 'error' not in performance_metrics:
    #    insert_performance(page, performance_metrics, timestamp, cache_warming=cache_warming)
    else:
        insert_performance(
            page,
            {k: 0 for k in measurement_elements},
            timestamp,
            cache_warming=cache_warming,
            error=event_log[0]["error"],
        )
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
                "event_type": "nerd_stats",
                "buffer_perc": -1.0,
                "curr_play_time": item["media_reference_time"],
                "video_dur": -1.0,
                "current_quality": "",
                "available_qualities": "",
                "bandwidth_kbps": item["nerdstats"]["bandwidth_kbps"],
                "buffer_health_seconds": item["nerdstats"]["buffer_health_seconds"],
                "codecs": item["nerdstats"]["codecs"],
                "dims_and_frames": item["nerdstats"]["dims_and_frames"],
                "resolution": item["nerdstats"]["resolution"],
                "network_activity_bytes": item["nerdstats"]["network_activity_bytes"],
            }
        )
    return nerd_stats_log


def create_measurements_table():
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS measurements (
            id string,
            protocol string,
            server string,
            domain string,
            vantagePoint string,
            timestamp datetime,
            time datetime,
            event_type string,
            buffer_perc real,
            curr_play_time real,
            video_dur real,
            current_quality string,
            available_qualities string,
            bandwidth_kbps string,
            buffer_health_seconds string,
            codecs string,
            dims_and_frames string,
            resolution string,
            network_activity_bytes string,
            cacheWarming integer,
            error string,
            PRIMARY KEY (id)
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
                FOREIGN KEY (measurement_id) REFERENCES measurements(id)
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
                FOREIGN KEY (measurement_id) REFERENCES measurements(id)
            );
            """
    )
    db.commit()


def insert_performance(page, performance, timestamp, cache_warming=0, error=""):
    performance["protocol"] = protocol
    performance["server"] = server
    performance["domain"] = page
    performance["timestamp"] = timestamp
    performance["cacheWarming"] = cache_warming
    performance["error"] = error
    performance["vantagePoint"] = vantage_point
    # generate unique ID
    sha = hashlib.md5()
    if performance["event_type"] == 0:
        performance["event_type"] = "selenium_error"
    sha_input = (
        ""
        + protocol
        + server
        + page
        + str(cache_warming)
        + vantage_point
        + str(performance["time"])
        + performance["event_type"]
    )
    sha.update(sha_input.encode())
    uid = uuid.UUID(sha.hexdigest())
    performance["id"] = str(uid)

    # insert into database
    cursor.execute(
        f"""
    INSERT INTO measurements VALUES ({(len(measurement_elements) - 1) * '?,'}?);
    """,
        tuple([performance[m_e] for m_e in measurement_elements]),
    )
    db.commit()

    if protocol == "quic":
        insert_qlogs(str(uid))
    # insert all domain lookups into second table
    if error == "" and proxyPID != 0:
        insert_lookups(str(uid))


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
                if "tranco-list.eu." not in line:
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
