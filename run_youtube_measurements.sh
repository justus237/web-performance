#!/bin/bash

if [[ $EUID -ne 0 ]]; then
    echo "$0 is not running as root. Try using sudo."
    exit 2
fi

#if [[ $EUID -ne 0 ]]; then
#    sudo "$0" "$@"
#    exit $?
#fi
echo "starting measurement process..."
date

# get vantage point info
vp="none"
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

declare -a protocols=("udp")#"tls" "https" "quic" "tcp" "udp")
declare -a framesizes=("256 144","426 240","640 360","854 480","1280 720","1920 1080","2560 1440","3840 2160")
declare -a qualities=("auto", "tiny", "small", "medium", "large", "hd720", "hd1080", "highres", "hd1440", "hd2160")
declare -a videos=("aqz-KE-bpKQ","lqiN98z6Dak","RJnKaAtBPhA")

while read upstream; do
  # skip server if it is unreachable
	ping -c 1 ${upstream} 2>&1 >/dev/null ;
	ping_code=$?
	if [ $ping_code = 0 ]
	then
		cd /home/ubuntu/dnsproxy
	
		https_upstream="${upstream}/dns-query"
		
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
				resolver="quic://${upstream}:784"
			else
				resolver="${p}://${upstream}"
			fi

			for framesize in "${framesizes[@]}"; do
				for quality in "${qualities[@]}"; do

					sleep 1
					echo "starting dnsproxy"
					./dnsproxy -u ${resolver} -v --insecure --ipv6-disabled -l "127.0.0.2" >& /home/ubuntu/web-performance/dnsproxy.log &
					dnsproxyPID=$!
			
					# measurements
					sleep 1
					echo "starting measurement ${framesize},${quality},${videos[@]}"
					cd /home/ubuntu/web-performance
					#python3 run_measurements.py $p $upstream $dnsproxyPID chrome $vp
					python3 youtube_measurement.py $p $upstream $dnsproxyPID chrome $vp $framesize $quality 0 30 ${videos[@]}
			
					sleep 1
					echo "killing dnsproxy"
					kill -SIGTERM $dnsproxyPID
					rm dnsproxy.log
					cd /home/ubuntu/dnsproxy
				done
			done
		done
	else
		echo "${upstream} not reachable"
	fi
done < /home/ubuntu/web-performance/servers.txt

# restart systemd-resolved
systemctl enable systemd-resolved
systemctl start systemd-resolved

date
echo "FIN"
