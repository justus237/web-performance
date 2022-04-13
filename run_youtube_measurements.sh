#!/bin/bash

if [[ $EUID -ne 0 ]]; then
    echo "$0 is not running as root. Try using sudo."
    exit 2
fi
SECONDS=0
#if [[ $EUID -ne 0 ]]; then
#    sudo "$0" "$@"
#    exit $?
#fi
echo "starting measurement process..."
date

# get vantage point info
vp=$(curl -s http://169.254.169.254/latest/meta-data/public-hostname | cut -d . -f2)
# increase UDP receive buffer size
sysctl -w net.core.rmem_max=25000000
# stop systemd-resolved and edit resolv.conf
systemctl stop systemd-resolved
systemctl disable systemd-resolved
echo "nameserver 127.0.0.2" | tee /etc/resolv.conf
# disable ipv6
sysctl -w net.ipv6.conf.all.disable_ipv6=1
sysctl -w net.ipv6.conf.default.disable_ipv6=1
sysctl -w net.ipv6.conf.lo.disable_ipv6=1

declare -a protocols=("tls" "https" "quic" "tcp" "udp")

#declare -a framesizes=("1280 720" "1920 1080" "2560 1440" "3840 2160")
#4k-capable: ("aqz-KE-bpKQ" "lqiN98z6Dak" "RJnKaAtBPhA")
declare -a videos=("aqz-KE-bpKQ" "lqiN98z6Dak")

while read upstream; do
	qport=$(echo ${upstream} | cut -d: -f2)
  	upstream=$(echo ${upstream} | cut -d: -f1)
  	# skip server if it is unreachable
	ping -c 1 ${upstream} 2>&1 >/dev/null ;
	ping_code=$?
	if [ $ping_code = 0 ]
	then
		cd /home/ubuntu/dnsproxy
	
		https_upstream="${upstream}/dns-query"
		
		for video in "${videos[@]}"; do
			for p in "${protocols[@]}"
			do
				echo $p

				if [ $p = "udp" ]
				then
					resolver="${upstream}"
				elif [ $p = "https" ]
				then
					resolver="${p}://${https_upstream}"
				elif [ $p = "quic" ]
				then
					if [ $qport = "8853" ]
					then
						resolver="quic://${upstream}:8853"
					else
						resolver="quic://${upstream}:784"
					fi
				else
					resolver="${p}://${upstream}"
				fi

			
				sleep 1
				echo "starting dnsproxy"
				./dnsproxy -u ${resolver} -v --insecure --ipv6-disabled -l "127.0.0.2" >& /home/ubuntu/web-performance-youtube/dnsproxy.log &
				dnsproxyPID=$!
		
				# measurements
				sleep 1
				echo "starting measurement 720p, auto, ${video} over ${p} on ${upstream}"
				cd /home/ubuntu/web-performance-youtube
				#python3 run_measurements.py $p $upstream $dnsproxyPID chrome $vp
				python3 youtube_measurement.py $p $upstream $dnsproxyPID chrome $vp 1280 720 auto 0 5 $video}

				sleep 1
				echo "killing dnsproxy"
				kill -SIGTERM $dnsproxyPID
				rm dnsproxy.log
				cd /home/ubuntu/dnsproxy
			done
		done
	else
		echo "${upstream} not reachable"
	fi
done < /home/ubuntu/web-performance-youtube/servers.txt

# restart systemd-resolved
systemctl enable systemd-resolved
systemctl start systemd-resolved

date
# https://unix.stackexchange.com/a/340156
ELAPSED="Elapsed: $(($SECONDS / 3600))hrs $((($SECONDS / 60) % 60))min $(($SECONDS % 60))sec"
echo $ELAPSED
