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
					protocol_filter_str="udp port 53"
				elif [ $p = "https" ]
				then
					resolver="${p}://${https_upstream}"
					protocol_filter_str="tcp port 443"
				elif [ $p = "quic" ]
				then
					#protocol_filter_str = "udp port 784 or udp port 8853 or udp port 853"
					if [ $qport = "8853" ]
					then
						resolver="quic://${upstream}:8853"
						protocol_filter_str="udp port 8853"
					elif [ $qport = "853" ]
					then
						resolver="quic://${upstream}:853"
						protocol_filter_str="udp port 853"
					else
						resolver="quic://${upstream}:784"
						protocol_filter_str="udp port 784"
					fi
				elif [ $p = "tls" ]
				then
					protocol_filter_str="tcp port 853"
					resolver="${p}://${upstream}"
				elif [ $p = "tcp" ]
				then
					protocol_filter_str="tcp port 53"
					resolver="${p}://${upstream}"
				else
					resolver="${p}://${upstream}"
					protocol_filter_str=""
				fi

				echo "tcpdump filter: host ${upstream} and ${protocol_filter_str}"

				timestamp="`date "+%Y-%m-%d_%H_%M_%S"`"
				echo "starting tcpdump"
				#start tcpdump and sleep for 5s because apparently it needs to initialize
				tcpdump -U -i any -w /home/ubuntu/web-performance-youtube/packet_captures/${upstream}_${p}_${video}_${timestamp}.pcap "host ${upstream} and ${protocol_filter_str}"&
				sleep 5
				#sleep 1
				echo "starting dnsproxy"
				./dnsproxy -u ${resolver} -v --insecure --ipv6-disabled -l "127.0.0.2" >& /home/ubuntu/web-performance-youtube/dnsproxy.log &
				dnsproxyPID=$!
		
				# measurements
				sleep 1
				echo "starting measurement 720p, auto, ${video} over ${p} on ${resolver}"
				cd /home/ubuntu/web-performance-youtube
				
				python3 youtube_measurement_with_capture.py $p $upstream $dnsproxyPID chrome $vp 1280 720 auto 0 5 $video

				sleep 1
				echo "killing dnsproxy and tcpdump"
				kill -SIGTERM $dnsproxyPID
				rm dnsproxy.log
				kill -SIGINT $(ps -e | pgrep tcpdump)
				sleep 5
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
