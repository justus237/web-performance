import time
import re
import sys
import sqlite3
from datetime import datetime
import hashlib
import uuid
import os

dnsproxy_dir = "/home/ubuntu/dnsproxy/"

db = sqlite3.connect("dns-metrics.db")
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
    server_msm_timestamp = sys.argv[4]
except IndexError:
    print(
        'Input params incomplete, ./dnsproxy protocol upstream_resolver_server dnsproxyPID'
    )
    sys.exit(1)




    
def create_lookups_table():
    cursor.execute(
        """
            CREATE TABLE IF NOT EXISTS lookups (
                msm_id string,
                domain string,
                elapsed numeric,
                status string,
                answer string
            );
            """
    )
    db.commit()

def create_dns_metrics_table():
    cursor.execute(
        """
            CREATE TABLE IF NOT EXISTS dns_metrics (
                msm_id string,
                metric string
            );
            """
    )
    db.commit()


def create_qlogs_table():
    cursor.execute(
        """
            CREATE TABLE IF NOT EXISTS qlogs (
                measurement_id string,
                qlog string
            );
            """
    )
    db.commit()

def create_msm_table():
    cursor.execute(
        """
            CREATE TABLE IF NOT EXISTS measurements (
                msm_id string,
                protocol string,
                resolver string,
                timestamp datetime,
                response string,
                server_msm_timestamp string,
                cache_warming integer
            );
            """
    )
    db.commit()

def insert_msm(msm_id, protocol, resolver, timestamp, response, server_msm_timestamp, cache_warming):
    cursor.execute(
        """
    INSERT INTO measurements VALUES (?,?,?,?,?,?,?);
    """,
        (msm_id, protocol, resolver,timestamp, response, server_msm_timestamp, cache_warming),
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

def insert_dns_metric(msm_id, metric):
    cursor.execute(
        """
    INSERT INTO dns_metrics VALUES (?,?);
    """,
        (msm_id,metric),
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
            elif "metrics:" in line:
                insert_dns_metric(uid, line)
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
    # necessary so that cache warming lookups dont get written
    # remove the log after parsing it
    with open("dnsproxy.log", "w") as logs:
        logs.write("")


create_msm_table()
create_lookups_table()
create_qlogs_table()
create_dns_metrics_table()

def run_dig(cw):
    timestamp = datetime.now()
    dns_response = os.system("dig @127.0.0.2 test.com")
    # generate unique ID for the overall measurement
    sha = hashlib.md5()
    sha_input = ('' + protocol + server + timestamp.strftime("%y-%m-%d-%H:%M:%S"))
    sha.update(sha_input.encode())
    uid = str(uuid.UUID(sha.hexdigest()))
    insert_msm(uid, protocol, server, timestamp, dns_response, server_msm_timestamp, cw)
    if protocol == "quic":
        insert_qlogs(uid)
    insert_lookups(uid)
    if proxyPID != 0 and cw == True:
        os.system("sudo kill -SIGUSR1 %d" % proxyPID)
        time.sleep(0.5)
    
run_dig(True)
run_dig(False)

db.close()
